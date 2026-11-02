@AGENTS.md

## Claude Code specifics
- Subagents: use the Agent tool with `subagent_type` set to the agent name (e.g. `tactics-critic`). Launch independent
  reviewers in one message so they run in parallel. They return JSON; you write the files.
- Entry skills: `/tactic-video <tactic text | topic> [--dry-run]` and `/match-preview "<home> vs <away> <when>" [--dry-run]`.
- Hooks (`.claude/settings.json`) run `hooks/dispatch.py`: they deny protected writes/reads, validate artifacts after
  each write, record the user's `approve <word>` messages, and run the fast tests before you stop after code edits.
  A denied tool call means the policy said no — fix the approach, do not retry the same call.
