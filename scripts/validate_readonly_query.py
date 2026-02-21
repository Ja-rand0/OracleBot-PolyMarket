"""
Safety hook: blocks SQL write operations when sqlite3 is in the command.

Used as a Claude Code hook to prevent the data-analyst agent from
accidentally modifying the database. Reads the hook event from stdin JSON.

Exit codes:
  0 — allow (no write keywords detected, or not a sqlite3 command)
  2 — block (write keyword detected in sqlite3 command)
"""

import json
import re
import sys


WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|ATTACH|DETACH|REINDEX|VACUUM)\b",
    re.IGNORECASE,
)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return 0  # allow if we can't parse

    # Extract the command from the hook event
    # Hook events have: {"tool_name": "Bash", "tool_input": {"command": "..."}}
    tool_input = event.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command:
        return 0

    # Only check commands that involve sqlite3
    if "sqlite3" not in command.lower():
        return 0

    # Check for write keywords
    if WRITE_KEYWORDS.search(command):
        print(
            f"BLOCKED: SQL write operation detected in sqlite3 command.\n"
            f"The data-analyst agent is read-only. Write operations are not allowed.\n"
            f"Command: {command}",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
