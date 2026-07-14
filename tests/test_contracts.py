"""Regression contracts for the landing page and vow-enforcement hooks."""

from __future__ import annotations

import json
import os
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SILENCE_HOOK = ROOT / "hooks" / "scripts" / "enforce-silence.sh"
REINJECT_HOOK = ROOT / "hooks" / "scripts" / "reinject-vow.sh"


def run_hook(path: Path, payload: dict[str, object], *, without_jq: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if without_jq:
        env["PATH"] = "/usr/bin:/bin"
    return subprocess.run(
        ["/bin/bash", str(path)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


class EditModeOriginContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_postmessage_never_uses_wildcard_target(self) -> None:
        self.assertNotIn("postMessage({ type:'__edit_mode_set_keys', edits:{ [key]: val } }, '*')", self.html)
        self.assertNotIn("postMessage({ type:'__edit_mode_available' }, '*')", self.html)
        self.assertNotIn("postMessage({ type:'__edit_mode_dismissed' }, '*')", self.html)
        self.assertIsNone(re.search(r"postMessage\([^;\n]+,\s*['\"]\*['\"]\)", self.html))

    def test_outbound_protocol_uses_same_origin_helper(self) -> None:
        self.assertIn("const EDIT_MODE_ORIGIN = window.location.origin;", self.html)
        self.assertIn("window.parent.postMessage(payload, EDIT_MODE_ORIGIN)", self.html)

    def test_inbound_protocol_checks_parent_source_and_origin(self) -> None:
        self.assertIn(
            "if (e.source !== window.parent || e.origin !== EDIT_MODE_ORIGIN) return;",
            self.html,
        )


class SilenceHookContract(unittest.TestCase):
    def test_empty_final_message_allows_stop(self) -> None:
        result = run_hook(SILENCE_HOOK, {"last_assistant_message": ""})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_any_final_text_blocks_stop(self) -> None:
        result = run_hook(SILENCE_HOOK, {"last_assistant_message": "[bows]"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_whitespace_only_final_text_blocks_stop(self) -> None:
        for message in (" ", "\n", "\t\n"):
            with self.subTest(message=repr(message)):
                result = run_hook(SILENCE_HOOK, {"last_assistant_message": message})
                self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_missing_or_null_final_message_fails_closed(self) -> None:
        for payload in ({}, {"last_assistant_message": None}):
            with self.subTest(payload=payload):
                result = run_hook(SILENCE_HOOK, payload)
                self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_jq_less_fallback_is_fail_closed(self) -> None:
        result = run_hook(
            SILENCE_HOOK,
            {"last_assistant_message": "Done."},
            without_jq=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_jq_less_fallback_allows_verified_empty_message(self) -> None:
        result = run_hook(
            SILENCE_HOOK,
            {"last_assistant_message": ""},
            without_jq=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_chat_phrase_does_not_disable_reinjection(self) -> None:
        result = run_hook(REINJECT_HOOK, {"prompt": "speak freely"})
        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("No user-chat phrase lifts it", context)


if __name__ == "__main__":
    unittest.main()
