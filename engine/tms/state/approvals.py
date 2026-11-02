"""Signing: human approvals + integrity seals on every state record.

Approvals bind to the stage's *binding hashes* (produced artifacts AND inputs, see machine.binding), so changing
anything a stage was approved on voids the approval. Only two paths create an approval:
  * via="prompt-hook" — the UserPromptSubmit hook, when the USER's whole message is `approve <word>`;
  * via="tty"         — `tms approve <word>` in the user's own interactive terminal (typed-back code).
via="test" exists only for offline tests and is accepted only on dry_run projects. There is no approving CLI flag.

Every state record (events, QA records, decisions, approvals) carries an HMAC "seal" made with a key stored outside
the workspace, so `tms audit` detects records that were hand-written or edited instead of produced by the CLI.
Tamper-evident, not a security boundary against a determined adversary with shell access.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

from tms import jsonio
from tms.state.project import Project, ProjectError, next_id

VIAS = ("prompt-hook", "tty", "test")


def default_key_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "TacticMotionStudio"


def key_dir() -> Path:
    override = os.environ.get("TMS_KEY_DIR", "").strip()
    return Path(override) if override else default_key_dir()


def _key() -> bytes:
    d = key_dir()
    f = d / "approval.key"
    if not f.is_file():
        d.mkdir(parents=True, exist_ok=True)
        f.write_text(secrets.token_hex(32), encoding="utf-8")
    return bytes.fromhex(f.read_text(encoding="utf-8").strip())


def key_id() -> str:
    return hashlib.sha256(_key()).hexdigest()[:12]


def _mac(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "hmac"}
    return hmac.new(_key(), jsonio.canonical(body), hashlib.sha256).hexdigest()


def seal(record: dict) -> dict:
    out = dict(record)
    out.pop("hmac", None)
    out["hmac"] = _mac(out)
    return out


def seal_ok(record: dict) -> bool:
    return isinstance(record.get("hmac"), str) and hmac.compare_digest(record["hmac"], _mac(record))


def sign(project: Project, stage: str, word: str, binding: dict, via: str, session_id: str) -> dict:
    if via not in VIAS:
        raise ProjectError(f"invalid approval channel {via!r}")
    if via == "test" and not project.dry_run:
        raise ProjectError("test approvals are only valid on dry_run projects")
    records = project.records("approvals")
    rec = {"id": next_id(records, "A-"), "ts": jsonio.now_iso(), "project_id": project.id, "stage": stage,
           "word": word, "hashes": dict(sorted(binding.items())), "via": via, "session_id": session_id or "-",
           "nonce": secrets.token_hex(16), "key_id": key_id()}
    rec = seal(rec)
    jsonio.append_jsonl(project.record_file("approvals"), rec)
    return rec


def verify(project: Project, rec: dict) -> str | None:
    """None if valid, else why not."""
    if rec.get("project_id") != project.id:
        return "approval belongs to another project"
    if rec.get("via") not in VIAS:
        return "unknown channel"
    if rec.get("via") == "test" and not project.dry_run:
        return "test approval on a non-dry-run project"
    if rec.get("key_id") != key_id():
        return "signed with a different key"
    if not seal_ok(rec):
        return "bad signature (record edited?)"
    return None


def valid_for(project: Project, stage: str, binding: dict) -> dict | None:
    """Latest valid approval for `stage` whose bound hashes equal `binding` exactly."""
    want = dict(sorted(binding.items()))
    for rec in reversed(project.records("approvals")):
        if rec.get("stage") == stage and rec.get("hashes") == want and verify(project, rec) is None:
            return rec
    return None
