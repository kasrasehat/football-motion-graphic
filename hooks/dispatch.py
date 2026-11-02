"""Single hook entry point for Claude Code (.claude/settings.json) and Codex (.codex/hooks.json).

Usage: <venv python> hooks/dispatch.py {pre-tool-use|post-tool-use|stop|user-prompt-submit|session-start}
Reads the harness JSON payload on stdin. Logic lives in engine/tms/harness/hooks.py (unit-tested).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from tms.harness.hooks import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
