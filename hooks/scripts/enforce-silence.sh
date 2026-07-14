#!/usr/bin/env bash
# Block a turn from completing if Claude emitted any final assistant text.
# Tool calls remain unaffected; the model must simply stop after its last tool.
set -euo pipefail

INPUT="$(</dev/stdin)"
IS_EMPTY="no"

if command -v jq >/dev/null 2>&1; then
  IS_EMPTY="$(
    printf '%s' "$INPUT" \
      | jq -r 'if has("last_assistant_message") and .last_assistant_message == "" then "yes" else "no" end' \
        2>/dev/null \
      || printf 'no'
  )"
elif command -v python3 >/dev/null 2>&1; then
  IS_EMPTY="$(
    printf '%s' "$INPUT" | python3 -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except (json.JSONDecodeError, UnicodeDecodeError):
    print("no")
else:
    print(
        "yes"
        if isinstance(payload, dict)
        and "last_assistant_message" in payload
        and payload["last_assistant_message"] == ""
        else "no"
    )
' 2>/dev/null || printf 'no'
  )"
fi

if [ "$IS_EMPTY" = "yes" ]; then
  exit 0
fi

REASON='The Vow forbids all final assistant text. Complete the work through tools, then end the turn without prose, code blocks, or stage directions.'
if command -v jq >/dev/null 2>&1; then
  jq -n --arg reason "$REASON" '{decision:"block", reason:$reason}'
else
  printf '{"decision":"block","reason":"The Vow forbids all final assistant text. Complete the work through tools, then end the turn without prose, code blocks, or stage directions."}\n'
fi
