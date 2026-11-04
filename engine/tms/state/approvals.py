"""Signing: human approvals + integrity seals on every state record.

Approvals bind to the stage's *binding hashes* (produced artifacts AND inputs, see machine.binding), so changing
anything a stage was approved on voids the approval. Only two paths create an approval:
  * via="prompt-hook" — the UserPromptSubmit hook, when the USER's whole message is `approve <word>`;
  * via="tty"         — `tms approve <word>` in the user's own interactive terminal (typed-back code).
via="test" exists only for offline tests and is accepted only on dry_run projects. There is no approving CLI flag.

Every state record (events, QA records, decisions, approvals) carries an HMAC "seal" made with a key stored outside
the workspace, so `tms audit` detects records that were hand-written or edited instead of produced by the CLI.
Tamper-evident, not a security boundary against a determined adversary with shell access.

Key location: under the user's home, NOT under %LOCALAPPDATA%. Processes started by the packaged desktop app get a
private overlay over AppData (same path string, different file), so a key there splits into one key per view. Home is
the same place in every view. Layout of key_dir():
    approval.key        signs new records (created on first write, atomically)
    trusted/<id>.key    verify-only keys brought in by the user with `tms key migrate`
A record is valid if a key in that ring verifies it. Nothing else is ever trusted automatically: a key found at an old
location counts only until the user migrates, and reading never creates a key.
"""
from __future__ import annotations

import glob
import hashlib
import hmac
import os
import secrets
from pathlib import Path

from tms import jsonio
from tms.state.project import Project, ProjectError, next_id

VIAS = ("prompt-hook", "tty", "test")
APP_DIR = "TacticMotionStudio"
KEY_NAME = "approval.key"


def default_key_dir() -> Path:
    return Path.home() / f".{APP_DIR}"


def _override() -> str:
    return os.environ.get("TMS_KEY_DIR", "").strip()


def key_dir() -> Path:
    return Path(_override()) if _override() else default_key_dir()


def _old_key_here() -> Path:
    """Where this process's view would find a key written by a version before the move to home."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_DIR / KEY_NAME


def old_key_files() -> list[Path]:
    """Every old key reachable from here, including the desktop app's physical overlay under Packages. Paths only:
    this does not open them. An explicit TMS_KEY_DIR means an isolated key space, so nothing is discovered."""
    if _override():
        return []
    hits = [_old_key_here()]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        hits += map(Path, sorted(glob.glob(glob.escape(local) + f"/Packages/*/LocalCache/Local/{APP_DIR}/{KEY_NAME}")))
    return [p for p in hits if p.is_file()]


def _read_key(f: Path) -> bytes:
    try:
        return bytes.fromhex(f.read_text(encoding="utf-8").strip())
    except ValueError as e:
        raise ProjectError(f"approval key file {f} is not valid; do not edit it") from e


def _kid(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:12]


def _create_exclusive(f: Path, text: str) -> None:
    """Atomic and first-writer-wins: concurrent sessions must never end up with different keys, or see a partial file."""
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".{f.name}.{secrets.token_hex(4)}.tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
        os.link(tmp, f)
    except FileExistsError:
        pass
    finally:
        tmp.unlink(missing_ok=True)


def _signing_file() -> Path | None:
    f = key_dir() / KEY_NAME
    if f.is_file():
        return f
    if not _override() and _old_key_here().is_file():  # not migrated yet: behave as before the move
        return _old_key_here()
    return None


def _signing_key() -> bytes:
    f = _signing_file()
    if f is not None:
        return _read_key(f)
    if not _override() and old_key_files():
        raise ProjectError("approval key not migrated: this view sees no key, but an old one exists. The user must run "
                           "`tms key migrate` in their own terminal.")
    target = key_dir() / KEY_NAME
    _create_exclusive(target, secrets.token_hex(32))
    return _read_key(target)


def _ring() -> dict[str, bytes]:
    """Every key this process trusts, by id. Read-only: never creates anything."""
    files = [f for f in [_signing_file()] if f] + sorted((key_dir() / "trusted").glob("*.key"))
    return {_kid(k): k for k in map(_read_key, files)}


def key_id() -> str:
    return _kid(_signing_key())


def migration_pending() -> bool:
    return not _override() and not (key_dir() / KEY_NAME).is_file() and bool(old_key_files())


def key_status() -> dict:
    """Ids and locations only, never key material; agents may run this, so old keys are listed without being opened."""
    signing = _signing_file()
    return {"key_dir": str(key_dir()), "signing": _kid(_read_key(signing)) if signing else None,
            "signing_file": str(signing) if signing else None,
            "trusted": sorted(p.stem for p in (key_dir() / "trusted").glob("*.key")),
            "old_keys_found": [str(p) for p in old_key_files()],
            "migration_pending": migration_pending()}


def key_id_of(f: Path) -> str:
    return _kid(_read_key(f))


def migrate_keys() -> dict:
    """Bring every old key in as verify-only, then start one signing key at the shared location. Safe to re-run."""
    imported = []
    for f in old_key_files():
        kid = _kid(_read_key(f))
        dest = key_dir() / "trusted" / f"{kid}.key"
        if not dest.is_file():
            _create_exclusive(dest, f.read_text(encoding="utf-8").strip())
            imported.append(kid)
    target = key_dir() / KEY_NAME
    if not target.is_file():  # last: until this exists, other processes keep using their old key, now also trusted
        _create_exclusive(target, secrets.token_hex(32))
    return {"key_dir": str(key_dir()), "imported": imported, "signing_key_id": _kid(_read_key(target))}


def _mac(record: dict, key: bytes) -> str:
    body = {k: v for k, v in record.items() if k != "hmac"}
    return hmac.new(key, jsonio.canonical(body), hashlib.sha256).hexdigest()


def seal(record: dict) -> dict:
    out = dict(record)
    out.pop("hmac", None)
    out["hmac"] = _mac(out, _signing_key())
    return out


def _seal_ok_with(record: dict, key: bytes) -> bool:
    return isinstance(record.get("hmac"), str) and hmac.compare_digest(record["hmac"], _mac(record, key))


def seal_ok(record: dict) -> bool:
    return any(_seal_ok_with(record, k) for k in _ring().values())


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
    key = _ring().get(rec.get("key_id"))
    if key is None:
        return (f"signed with unknown key {rec.get('key_id')}: not counted. If the user made this approval from another "
                "environment, they run `tms key migrate` in their own terminal; if that key is gone, they approve again")
    if not _seal_ok_with(rec, key):
        return "bad signature (record edited?)"
    return None


def valid_for(project: Project, stage: str, binding: dict) -> dict | None:
    """Latest valid approval for `stage` whose bound hashes equal `binding` exactly."""
    want = dict(sorted(binding.items()))
    for rec in reversed(project.records("approvals")):
        if rec.get("stage") == stage and rec.get("hashes") == want and verify(project, rec) is None:
            return rec
    return None
