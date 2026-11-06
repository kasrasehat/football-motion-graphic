from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from dateutil.parser import parse as parse_date

from .extract import embedded_json, extract_page, soup_of, walk_json
from .matching import mentions
from .transport import HOSTS, NEWS_HOSTS


def article_from_html(html: str, url: str) -> dict | None:
    soup = soup_of(html)
    structured = next(
        (
            x
            for x in walk_json(embedded_json(html))
            if any(t in str(x.get("@type", "")) for t in ("NewsArticle", "Article", "BlogPosting"))
        ),
        {},
    )
    article = soup.select_one("article, [itemprop='articleBody'], .article__content, .newsDetail")
    if not structured and article is None:
        return None
    meta = lambda name: soup.select_one(f'meta[property="{name}"], meta[name="{name}"]')
    title = structured.get("headline") or (soup.h1.get_text(" ", strip=True) if soup.h1 else None)
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    published = structured.get("datePublished")
    if not published:
        tag = meta("article:published_time") or soup.select_one("time[datetime]")
        published = tag.get("content") or tag.get("datetime") if tag else None
    body = structured.get("articleBody") or (article.get_text("\n", strip=True) if article else "")
    if not body:
        return None
    author = structured.get("author")
    if not author and meta("author"):
        author = meta("author").get("content")
    canonical = soup.select_one('link[rel="canonical"]')
    return {
        "title": title,
        "body": body,
        "published_at": published,
        "author": author,
        "canonical_url": urljoin(url, canonical["href"]) if canonical and canonical.get("href") else url,
        "structured": structured,
    }


def news_relation(article: dict, query) -> str | None:
    text = f"{article.get('title', '')} {article.get('body', '')}"
    a = mentions(text, [query.opponent_a, *query.aliases_a])
    b = mentions(text, [query.opponent_b, *query.aliases_b])
    if not (a or b):
        return None
    stamp = article.get("published_at")
    if stamp:
        try:
            dt = parse_date(stamp)
            if dt.tzinfo:
                dt = dt.astimezone(ZoneInfo(query.timezone))
            else:
                article["publication_timezone_unknown"] = True
            if abs((dt.date() - query.date).days) > query.news_days:
                return None
        except (ValueError, TypeError, OverflowError):
            article["publication_time_unverified"] = True
    else:
        article["publication_time_unverified"] = True
    return "both_teams_mentioned" if a and b else "team_context"


async def collect_news(collector):
    query, report = collector.query, collector.report
    hosts = HOSTS[collector.name] | NEWS_HOSTS
    queue, seen, hashes = [], set(), set()
    collected = len(report.data["news"])
    names = [query.opponent_a, query.opponent_b, *query.aliases_a, *query.aliases_b]

    def enqueue_links(doc):
        for link in extract_page(doc.text, doc.url)["links"]:
            url, text = link["url"], link["text"]
            if urlsplit(url).hostname not in hosts:
                continue
            if not re.search(r"news|article|preview|report|vesti|story", url, re.IGNORECASE):
                continue
            relevance = mentions(text + " " + url.replace("-", " "), names)
            path = urlsplit(url).path.rstrip("/")
            is_index = path in ("/news", "/news/football", "/rs/vesti/sport")
            if relevance or is_index:
                queue.append((0 if relevance else 1, url))

    for doc in list(collector.documents.values()):
        if "html" in doc.evidence.content_type:
            enqueue_links(doc)
    if collector.name == "sofascore":
        queue.append((1, "https://www.sofascore.com/news"))
    indexes = 0
    while queue and collected < query.max_news and collector.pages < query.max_pages_per_source:
        queue.sort(key=lambda x: x[0])
        _, url = queue.pop(0)
        p = urlsplit(url)
        url = urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))
        if url in seen:
            continue
        seen.add(url)
        doc = await collector.maybe_get(url)
        if doc is None:
            continue
        article = article_from_html(doc.text, doc.url)
        if article:
            relation = news_relation(article, query)
            digest = hashlib.sha256(article["body"].encode()).hexdigest()
            if relation and digest not in hashes:
                hashes.add(digest)
                report.add("news", article, doc.url, relation=relation)
                collected += 1
        elif indexes < 3:
            indexes += 1
            enqueue_links(doc)
    report.warnings.append(
        "News scope: relevant links on discovered source pages and up to three linked news indexes, within the requested date window. Undated articles are marked unverified; external unlinked news is not searched."
    )
