"""Regression contracts for the landing page and vow-enforcement hooks."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SILENCE_HOOK = ROOT / "hooks" / "scripts" / "enforce-silence.sh"
REINJECT_HOOK = ROOT / "hooks" / "scripts" / "reinject-vow.sh"


def run_hook(
    path: Path,
    payload: dict[str, object] | str,
    *,
    without_jq: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a hook with structured or deliberately malformed raw input."""
    env = os.environ.copy()
    input_text = payload if isinstance(payload, str) else json.dumps(payload)

    def invoke() -> subprocess.CompletedProcess[str]:
        # Executable and hook paths are repository-owned constants; only the
        # JSON fixture is variable, and it is passed through stdin.
        return subprocess.run(  # noqa: S603
            ["/bin/bash", str(path)],
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    if not without_jq:
        return invoke()
    with tempfile.TemporaryDirectory() as path_dir:
        Path(path_dir, "python3").symlink_to(sys.executable)
        env["PATH"] = path_dir
        return invoke()


class EditModeOriginContract(unittest.TestCase):
    """Protect the edit-mode channel from cross-origin frames."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the single-page application once for textual contracts."""
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_postmessage_never_uses_wildcard_target(self) -> None:
        """Require a concrete target origin for every edit-mode send."""
        self.assertNotIn("postMessage({ type:'__edit_mode_set_keys', edits:{ [key]: val } }, '*')", self.html)
        self.assertNotIn("postMessage({ type:'__edit_mode_available' }, '*')", self.html)
        self.assertNotIn("postMessage({ type:'__edit_mode_dismissed' }, '*')", self.html)
        self.assertIsNone(re.search(r"postMessage\([^;\n]+,\s*['\"]\*['\"]\)", self.html))

    def test_outbound_protocol_uses_same_origin_helper(self) -> None:
        """Route outbound edit messages through the same-origin helper."""
        self.assertIn("const EDIT_MODE_ORIGIN = window.location.origin;", self.html)
        self.assertIn("window.parent.postMessage(payload, EDIT_MODE_ORIGIN)", self.html)

    def test_inbound_protocol_checks_parent_source_and_origin(self) -> None:
        """Accept inbound edit messages only from the same-origin parent."""
        self.assertIn(
            "if (e.source !== window.parent || e.origin !== EDIT_MODE_ORIGIN) return;",
            self.html,
        )


class SilenceHookContract(unittest.TestCase):
    """Enforce exact-empty Stop messages with and without jq."""

    def test_empty_final_message_allows_stop(self) -> None:
        """Allow a verified empty final assistant message."""
        result = run_hook(SILENCE_HOOK, {"last_assistant_message": ""})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_any_final_text_blocks_stop(self) -> None:
        """Block even formerly permitted bracketed gestures."""
        result = run_hook(SILENCE_HOOK, {"last_assistant_message": "[bows]"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_whitespace_only_final_text_blocks_stop(self) -> None:
        """Treat whitespace as visible assistant output."""
        for message in (" ", "\n", "\t\n"):
            with self.subTest(message=repr(message)):
                result = run_hook(SILENCE_HOOK, {"last_assistant_message": message})
                self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_missing_or_null_final_message_fails_closed(self) -> None:
        """Block payloads that do not prove the final message is empty."""
        for payload in ({}, {"last_assistant_message": None}):
            with self.subTest(payload=payload):
                result = run_hook(SILENCE_HOOK, payload)
                self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_jq_less_fallback_is_fail_closed(self) -> None:
        """Block non-empty messages when Python is the JSON parser."""
        result = run_hook(
            SILENCE_HOOK,
            {"last_assistant_message": "Done."},
            without_jq=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_jq_less_fallback_allows_verified_empty_message(self) -> None:
        """Allow only a top-level exact-empty message without jq."""
        result = run_hook(
            SILENCE_HOOK,
            {"last_assistant_message": ""},
            without_jq=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_jq_less_fallback_rejects_nested_empty_message(self) -> None:
        """Reject an empty message hidden under a nested object."""
        result = run_hook(
            SILENCE_HOOK,
            {"nested": {"last_assistant_message": ""}},
            without_jq=True,
        )
        self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_jq_less_fallback_rejects_malformed_json(self) -> None:
        """Reject malformed input containing a deceptive empty fragment."""
        result = run_hook(
            SILENCE_HOOK,
            '{"last_assistant_message":""',
            without_jq=True,
        )
        self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_chat_phrase_does_not_disable_reinjection(self) -> None:
        """Keep reinjecting the vow for former escape phrases."""
        result = run_hook(REINJECT_HOOK, {"prompt": "speak freely"})
        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("No user-chat phrase lifts it", context)


if __name__ == "__main__":
    unittest.main()
