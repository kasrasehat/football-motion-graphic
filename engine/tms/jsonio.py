"""JSON / JSONL I/O and content hashing. All writes are atomic, UTF-8, LF."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, doc: Any, *, compact: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":")) if compact else \
        json.dumps(doc, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def append_jsonl(path: Path, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


class CorruptRecord(ValueError):
    pass


def read_jsonl(path: Path) -> Iterator[dict]:
    """Strict: raises CorruptRecord naming the line (state files must never be silently skipped)."""
    path = Path(path)
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise CorruptRecord(f"{path.name}: not UTF-8 ({e})") from e
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            raise CorruptRecord(f"{path.name} line {n}: {e.msg}") from e
        if not isinstance(rec, dict):
            raise CorruptRecord(f"{path.name} line {n}: not a JSON object")
        yield rec


def canonical(doc: Any) -> bytes:
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """JSON files hash their canonical form (formatting-insensitive); everything else hashes raw bytes."""
    path = Path(path)
    if path.suffix == ".json":
        try:
            return sha256_bytes(canonical(read_json(path)))
        except ValueError:  # malformed JSON or non-UTF-8 bytes: hash the raw bytes instead
            pass
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
