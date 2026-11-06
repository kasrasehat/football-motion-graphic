"""Optional normal Chromium rendering. No stealth plugins or challenge bypasses."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from urllib.parse import urlsplit

from .models import Evidence
from .transport import DATA_HOSTS, HOSTS, Document, Fetcher, FetchError, validate_url


class Renderer:
    def __init__(self, fetcher: Fetcher, timezone: str = "UTC"):
        self.fetcher, self.timezone = fetcher, timezone
        self.runtime = self.browser = self.context = None

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.runtime:
            await self.runtime.stop()

    async def start(self):
        if self.context:
            return
        from playwright.async_api import async_playwright

        self.runtime = await async_playwright().start()
        try:
            self.browser = await self.runtime.chromium.launch(headless=True)
            self.context = await self.browser.new_context(
                timezone_id=self.timezone, locale="en-US", service_workers="block"
            )
        except Exception as exc:
            raise FetchError(
                "browser", "Chromium unavailable; run: python -m playwright install chromium"
            ) from exc

    async def render(self, url: str) -> tuple[Document, list[dict]]:
        url = validate_url(url, self.fetcher.hosts)
        await self.fetcher.policy(url)
        await self.start()
        page = await self.context.new_page()
        page.set_default_timeout(12000)
        payloads, tasks = [], set()
        pending = set()
        last_activity = time.monotonic()
        main_hosts = HOSTS[self.fetcher.source] | DATA_HOSTS[self.fetcher.source]

        async def route(request_route):
            request = request_route.request
            host = urlsplit(request.url).hostname
            if any(part in urlsplit(request.url).path for part in ("/banners", "/box-over-content/")):
                return await request_route.abort()
            # Rendering may load public scripts/styles from CDNs. Only source data
            # requests are captured; advertising, telemetry and writes are blocked.
            if request.method not in {"GET", "HEAD", "OPTIONS"} or request.resource_type in {
                "image",
                "media",
                "font",
            }:
                return await request_route.abort()
            if request.is_navigation_request() or request.resource_type in {"xhr", "fetch"}:
                if host not in main_hosts:
                    if host and any(
                        word in host for word in ("flashscore", "livesport", "soccerway", "sofascore")
                    ):
                        self.fetcher.evidence.append(
                            Evidence(
                                url=request.url, error="Data host is outside the configured browser allowlist"
                            )
                        )
                    return await request_route.abort()
                try:
                    await self.fetcher.policy(request.url)
                    await self.fetcher.throttle(request.url)
                except FetchError as exc:
                    self.fetcher.evidence.append(
                        Evidence(url=request.url, error=exc.reason, status_code=exc.status)
                    )
                    return await request_route.abort()
            await request_route.continue_()

        async def capture(response):
            if urlsplit(response.url).hostname not in main_hosts:
                return
            if response.request.resource_type not in {"xhr", "fetch"}:
                return
            if response.request.method != "GET":
                return
            if any(part in urlsplit(response.url).path for part in ("/banners", "/box-over-content/")):
                return
            content_type = response.headers.get("content-type", "")
            try:
                body = await asyncio.wait_for(response.body(), timeout=10)
                if len(body) > self.fetcher.max_bytes:
                    self.fetcher.evidence.append(
                        Evidence(url=response.url, error="Browser response exceeded size limit")
                    )
                    return
                doc = self.fetcher.save(response.url, body, response.status, content_type)
                if response.ok:
                    try:
                        value = json.loads(doc.text)
                    except ValueError:
                        value = {"text": doc.text}
                    payloads.append({"url": response.url, "value": value})
            except Exception as exc:
                logging.getLogger(__name__).debug("Response capture failed", exc_info=True)
                self.fetcher.evidence.append(
                    Evidence(url=response.url, error=f"Capture failed: {type(exc).__name__}")
                )

        def on_response(response):
            task = asyncio.create_task(capture(response))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

        def on_request(request):
            nonlocal last_activity
            if urlsplit(request.url).hostname in main_hosts and request.resource_type in {"xhr", "fetch"}:
                pending.add(request)
                last_activity = time.monotonic()

        def on_finished(request):
            nonlocal last_activity
            if request in pending:
                pending.discard(request)
                last_activity = time.monotonic()

        await page.route("**/*", route)
        page.on("response", on_response)
        page.on("request", on_request)
        page.on("requestfinished", on_finished)
        page.on("requestfailed", on_finished)
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=40000)
            if response is not None and response.status >= 400:
                raise FetchError(url, f"Browser HTTP {response.status}", response.status)
            # Sports pages keep live connections open, so networkidle is inappropriate.
            await page.wait_for_timeout(3500)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if not pending and time.monotonic() - last_activity >= 1:
                    break
                await page.wait_for_timeout(250)
            if pending:
                self.fetcher.evidence.append(
                    Evidence(
                        url=url, error="Some browser data requests did not finish before the render deadline"
                    )
                )
            html = await page.content()
            title = (await page.title()).lower()
            if any(x in title for x in ("just a moment", "access denied")):
                raise FetchError(url, "Access challenge", 403)
            if tasks:
                await asyncio.gather(*list(tasks), return_exceptions=True)
            doc = self.fetcher.save(page.url, html.encode(), 200, "text/html; rendered=true")
            return doc, payloads
        except FetchError:
            raise
        except Exception as exc:
            raise FetchError(url, f"Browser failed: {type(exc).__name__}: {str(exc)[:180]}") from exc
        finally:
            if tasks:
                await asyncio.gather(*list(tasks), return_exceptions=True)
            await page.close()
