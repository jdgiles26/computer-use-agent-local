from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from computer_use_agent import (
    ActionSafety,
    ActionValidator,
    BrowserTool,
    JsonActionParser,
    ModelSelector,
    WorkingMemory,
    pick_reviewer_model,
)
from desktop_control import DesktopTool, DesktopControlError


class ModelSelectorTests(unittest.TestCase):
    def test_best_model_skips_incomplete_shards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gpt-oss-20b-MXFP4.gguf").write_bytes(b"x" * 1024)
            (root / "Qwen3.5-122B-A10B-Q3_K_S-00003-of-00003.gguf").write_bytes(b"x" * 2048)

            selector = ModelSelector(root)
            best = selector.best_model()

            self.assertEqual(best.path.name, "gpt-oss-20b-MXFP4.gguf")

    def test_detect_incomplete_shards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shard = root / "demo-00002-of-00003.gguf"
            shard.write_bytes(b"x")

            selector = ModelSelector(root)

            self.assertTrue(selector.detect_incomplete_shards(shard))


class JsonActionParserTests(unittest.TestCase):
    def test_extracts_plain_json(self) -> None:
        data = JsonActionParser.extract_json('{"action":"finish","args":{"message":"done"}}')
        self.assertEqual(data["action"], "finish")
        self.assertEqual(data["args"]["message"], "done")

    def test_extracts_json_inside_code_fence(self) -> None:
        data = JsonActionParser.extract_json(
            '```json\n{"action":"list_files","args":{"path":"."},"message":"inspect"}\n```'
        )
        self.assertEqual(data["action"], "list_files")
        self.assertEqual(data["args"]["path"], ".")

    def test_prefers_action_json_over_embedded_example_object(self) -> None:
        data = JsonActionParser.extract_json(
            'The supported action looks like {"app_name":"Safari"}.\n'
            '{"action":"desktop_open_app","args":{"app_name":"Terminal"},"message":"open terminal"}'
        )
        self.assertEqual(data["action"], "desktop_open_app")
        self.assertEqual(data["args"]["app_name"], "Terminal")

    def test_strips_reasoning_markup_and_extracts_final_action(self) -> None:
        data = JsonActionParser.extract_json(
            '<|channel|>analysis<|message|>Thinking about the next step.<|end|>'
            '{"action":"desktop_open_app","args":{"app_name":"Terminal"},"message":"Open Terminal"}'
        )
        self.assertEqual(data["action"], "desktop_open_app")
        self.assertEqual(data["args"]["app_name"], "Terminal")


class BrowserToolTests(unittest.TestCase):
    def test_snapshot_summary_prefers_interactive_refs(self) -> None:
        summary = BrowserTool.summarize_snapshot_text(
            """
            - generic [ref=e1]
            - textbox "Email" [active] [ref=e2]
            - button "Continue" [ref=e3]
            - generic [ref=e4]
            """
        )
        self.assertIn('textbox "Email" [active] [ref=e2]', summary)
        self.assertIn('button "Continue" [ref=e3]', summary)
        self.assertNotIn("- generic [ref=e1]", summary)

    def test_resolve_cli_command_prefers_workspace_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            wrapper = scripts / "playwright_cli.sh"
            wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            with mock.patch.dict("os.environ", {}, clear=False):
                self.assertEqual(BrowserTool.resolve_cli_command(root), [str(wrapper.resolve())])


class ActionSafetyTests(unittest.TestCase):
    def test_workspace_path_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            safety = ActionSafety(Path(tmp))
            allowed, resolved, reason = safety.is_path_allowed("notes.txt")
            self.assertTrue(allowed)
            self.assertIsNotNone(resolved)
            self.assertEqual(reason, "ok")

    def test_outside_workspace_path_allowed(self) -> None:
        """With unrestricted access, paths outside workspace are now allowed."""
        with tempfile.TemporaryDirectory() as tmp:
            safety = ActionSafety(Path(tmp))
            allowed, resolved, reason = safety.is_path_allowed("../escape.txt")
            self.assertTrue(allowed)
            self.assertIsNotNone(resolved)
            self.assertEqual(reason, "ok")

    def test_destructive_shell_allowed(self) -> None:
        """With unrestricted access, destructive commands like rm are now allowed."""
        with tempfile.TemporaryDirectory() as tmp:
            safety = ActionSafety(Path(tmp))
            allowed, reason = safety.check_shell("rm -rf /")
            self.assertTrue(allowed)
            self.assertEqual(reason, "ok")

    def test_sudo_shell_allowed(self) -> None:
        """With unrestricted access, sudo commands are now allowed."""
        with tempfile.TemporaryDirectory() as tmp:
            safety = ActionSafety(Path(tmp))
            allowed, reason = safety.check_shell("sudo nmap -sS 192.168.1.1")
            self.assertTrue(allowed)
            self.assertEqual(reason, "ok")

    def test_safe_shell_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            safety = ActionSafety(Path(tmp))
            allowed, reason = safety.check_shell("pwd")
            self.assertTrue(allowed)
            self.assertEqual(reason, "ok")


class ActionValidatorTests(unittest.TestCase):
    def test_missing_required_arg_is_rejected(self) -> None:
        valid, reason = ActionValidator.validate("browser_click", {})
        self.assertFalse(valid)
        self.assertIn("requires arg: ref", reason)

    def test_new_generic_actions_are_supported(self) -> None:
        valid, reason = ActionValidator.validate("desktop_set_clipboard", {"text": "hello"})
        self.assertTrue(valid)
        self.assertEqual(reason, "ok")
        valid, reason = ActionValidator.validate("browser_tab_new", {"url": "https://example.com"})
        self.assertTrue(valid)
        self.assertEqual(reason, "ok")


class ReviewerModelTests(unittest.TestCase):
    def test_pick_reviewer_model_auto_chooses_alternative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "model-a-instruct.gguf"
            alternative = root / "model-b-chat.gguf"
            primary.write_bytes(b"x" * 1024)
            alternative.write_bytes(b"x" * 2048)
            with mock.patch("computer_use_agent.MODELS_DIR", root):
                picked = pick_reviewer_model("auto", primary)
            self.assertEqual(picked, alternative)

    def test_pick_reviewer_model_empty_disables_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "model-a.gguf"
            primary.write_bytes(b"x" * 1024)
            self.assertIsNone(pick_reviewer_model("", primary))


class WorkingMemoryTests(unittest.TestCase):
    def test_repeated_action_warning_after_same_shell_signature(self) -> None:
        memory = WorkingMemory()
        for _ in range(3):
            memory.add("shell", {"command": "nmap -sV 192.168.1.1"}, "error", "Command timed out after 30 seconds.")
        summary = "\n".join(memory.summary_lines())
        self.assertIn("Pattern warning", summary)
        self.assertIn("Stall warning", summary)

    def test_latest_success_and_error_are_summarized(self) -> None:
        memory = WorkingMemory()
        memory.add("desktop_open_app", {"app_name": "Terminal"}, "ok", "Opened app Terminal")
        memory.add("shell", {"command": "nmap -sV 192.168.1.1"}, "error", "exit=1")
        summary = "\n".join(memory.summary_lines())
        self.assertIn("Latest success", summary)
        self.assertIn("Latest error", summary)


class DesktopToolTests(unittest.TestCase):
    def test_normalize_modifiers(self) -> None:
        modifiers = DesktopTool.normalize_modifiers(["command", "shift"])
        self.assertEqual(modifiers, ["command", "shift"])

    def test_invalid_modifier_raises(self) -> None:
        with self.assertRaises(DesktopControlError):
            DesktopTool.normalize_modifiers(["weird"])

    def test_key_code_for_known_key(self) -> None:
        self.assertEqual(DesktopTool.key_code_for("enter"), 36)

    def test_key_code_for_unknown_key_raises(self) -> None:
        with self.assertRaises(DesktopControlError):
            DesktopTool.key_code_for("notakey")

    def test_open_settings_panel_rejects_unknown_panel(self) -> None:
        with self.assertRaises(DesktopControlError):
            DesktopTool.open_settings_panel("unknown")

    def test_set_clipboard_writes_text(self) -> None:
        tool = DesktopTool(Path("."), Path("./output"))
        completed = subprocess.CompletedProcess(args=["/usr/bin/pbcopy"], returncode=0, stdout="", stderr="")
        with mock.patch("desktop_control.subprocess.run", return_value=completed) as run_mock:
            message = tool.set_clipboard("hello")
        self.assertIn("Copied 5 characters", message)
        run_mock.assert_called_once()

    def test_get_clipboard_reads_text(self) -> None:
        tool = DesktopTool(Path("."), Path("./output"))
        completed = subprocess.CompletedProcess(args=["/usr/bin/pbpaste"], returncode=0, stdout="copied", stderr="")
        with mock.patch("desktop_control.subprocess.run", return_value=completed):
            self.assertEqual(tool.get_clipboard(), "copied")


if __name__ == "__main__":
    unittest.main()
