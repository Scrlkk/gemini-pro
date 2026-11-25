"""Offline tests for explicit, fail-closed manual Android verification."""
import io
from subprocess import CompletedProcess, TimeoutExpired
import threading
import unittest
from unittest.mock import patch

import ultra0


class BlockingInput:
    def __init__(self):
        self.release = threading.Event()

    def readline(self):
        self.release.wait(1)
        return "\n"


class ManualVerificationTests(unittest.TestCase):
    FRESH = b'<hierarchy><node text="fresh"/></hierarchy>'

    def _capture(self, results):
        with patch.object(ultra0.subprocess, "run", side_effect=results) as run, \
             patch.object(ultra0.time, "sleep"), \
             patch.object(ultra0.sys, "stderr", io.StringIO()) as stderr:
            result = ultra0.ui_xml()
        return result, run, stderr.getvalue()

    @staticmethod
    def _result(code=0, stdout=b"", stderr=b""):
        return CompletedProcess([], code, stdout, stderr)

    def test_success_and_exit_139_with_complete_fresh_xml(self):
        for code in (0, 139):
            with self.subTest(code=code):
                result, run, log = self._capture([
                    self._result(code), self._result(stdout=self.FRESH), self._result()])
                self.assertEqual(result, self.FRESH.decode())
                self.assertEqual(run.call_count, 3)
                dump, read, cleanup = [call.args[0] for call in run.call_args_list]
                path = dump[-1]
                self.assertRegex(path, r"^/sdcard/eplus-ui-[0-9a-f]{32}\.xml$")
                self.assertEqual(dump[-4:], ["shell", "uiautomator", "dump", path])
                self.assertEqual(read[-3:], ["shell", "cat", path])
                self.assertEqual(cleanup[-4:], ["shell", "rm", "-f", path])
                self.assertEqual(log, "")

    def test_ui_dump_failure_cannot_return_an_old_hierarchy(self):
        stale = b'<hierarchy><node text="stale"/></hierarchy>'
        result, run, log = self._capture([
            self._result(1, stdout=stale, stderr=b"dump failed"),
            self._result(), self._result(0), self._result(stdout=self.FRESH), self._result()])
        self.assertEqual(result, self.FRESH.decode())
        self.assertEqual(run.call_count, 5)
        self.assertNotEqual(run.call_args_list[0].args[0][-1], run.call_args_list[2].args[0][-1])
        self.assertIn("dump exit 1", log)
        self.assertNotIn("stale", log)

    def test_invalid_crash_recovery_is_bounded_and_does_not_guess(self):
        for bad in (self._result(1, stdout=self.FRESH),
                    self._result(stdout=b"<hierarchy>"),
                    self._result(stdout=b"<wrong></wrong>"),
                    self._result(stdout=b"<hierarchy><x></hierarchy>")):
            with self.subTest(bad=bad), \
                 patch.object(ultra0.subprocess, "run", side_effect=[
                    self._result(139), bad, self._result(),
                    self._result(139), bad, self._result()]) as run, \
                 patch.object(ultra0.time, "sleep"):
                with self.assertRaisesRegex(ultra0.UICaptureError, "^Android UI capture failed$"):
                    ultra0.ui_xml()
                self.assertEqual(run.call_count, 6)

    def test_timeout_retries_once_then_stops(self):
        with patch.object(ultra0.subprocess, "run", side_effect=[
                TimeoutExpired("adb", 20), self._result(),
                TimeoutExpired("adb", 20), self._result()]) as run, \
             patch.object(ultra0.time, "sleep"):
            with self.assertRaises(ultra0.UICaptureError):
                ultra0.ui_xml()
            self.assertEqual(run.call_count, 4)

    def test_cleanup_failure_preserves_valid_capture(self):
        for cleanup in (TimeoutExpired("adb", 3), OSError("private@example.com"),
                        self._result(1, stderr=b"private@example.com")):
            with self.subTest(cleanup=cleanup):
                result, run, log = self._capture([
                    self._result(139), self._result(stdout=self.FRESH), cleanup])
                self.assertEqual(result, self.FRESH.decode())
                self.assertEqual(run.call_count, 3)
                self.assertIn("cleanup failed", log)
                self.assertNotIn("private@example.com", log)

    def test_cleanup_failure_cannot_mask_capture_failure(self):
        with patch.object(ultra0.subprocess, "run", side_effect=[
                self._result(139), self._result(1), OSError("private"),
                self._result(139), self._result(1), TimeoutExpired("adb", 3)]), \
             patch.object(ultra0.time, "sleep"), \
             patch.object(ultra0.sys, "stderr", io.StringIO()) as stderr:
            with self.assertRaisesRegex(ultra0.UICaptureError, "^Android UI capture failed$"):
                ultra0.ui_xml()
        self.assertNotIn("private", stderr.getvalue())

    def test_adb_diagnostics_do_not_leak_xml_or_emails(self):
        result, run, log = self._capture([
            self._result(1, stderr=b'<hierarchy>private@example.com</hierarchy>'),
            self._result(), self._result(), self._result(stdout=self.FRESH), self._result()])
        self.assertEqual(result, self.FRESH.decode())
        self.assertIn("dump exit 1", log)
        self.assertNotIn("private@example.com", log)
        self.assertNotIn("<hierarchy>", log)

    def test_crash_during_account_inspection_never_guesses_identity(self):
        with patch.object(ultra0, "ui_xml", side_effect=ultra0.UICaptureError("Android UI capture failed")), \
             patch.object(ultra0, "sh") as sh:
            with self.assertRaises(ultra0.UICaptureError):
                ultra0.current_play_account()
            sh.assert_not_called()

    def test_enter_acknowledgement_allows_continue(self):
        with patch.object(ultra0.sys, "stdin", io.StringIO("\n")):
            self.assertTrue(ultra0.wait_human("Test-only prompt", timeout=1))
        self.assertFalse(ultra0.WAITING["on"])

    def test_closed_stdin_never_counts_as_approval(self):
        with patch.object(ultra0.sys, "stdin", io.StringIO("")):
            self.assertFalse(ultra0.wait_human("Test-only prompt", timeout=1))
        self.assertFalse(ultra0.WAITING["on"])

    def test_timeout_does_not_fall_through_as_success(self):
        blocked = BlockingInput()
        try:
            with patch.object(ultra0.sys, "stdin", blocked):
                self.assertFalse(ultra0.wait_human("Test-only prompt", timeout=0.05))
            self.assertFalse(ultra0.WAITING["on"])
        finally:
            blocked.release.set()

    def test_card_setup_does_not_invent_billing_address(self):
        fields = [{"cls": "EditText", "x": 10, "y": 20}] * 7
        card = {"number": "4111111111111111", "exp": "0129",
                "cvc": "000", "holder": "Actual Name"}
        with patch.object(ultra0, "sh"), \
             patch.object(ultra0, "tap_text", return_value=True), \
             patch.object(ultra0, "nodes", return_value=fields), \
             patch.object(ultra0, "ui_xml", return_value="<xml/>"), \
             patch.object(ultra0, "tap"), \
             patch.object(ultra0, "type_text") as text_input, \
             patch.object(ultra0, "wait_human", return_value=True) as confirm, \
             patch.object(ultra0.time, "sleep"):
            self.assertTrue(ultra0.add_card(card))
        entered = [call.args[0] for call in text_input.call_args_list]
        self.assertEqual(entered, ["4111111111111111", "01", "29", "000", "Actual Name"])
        self.assertNotIn("123 Main St", entered)
        self.assertNotIn("Portland", entered)
        confirm.assert_called_once()

    def test_unconfirmed_payment_method_prevents_checkout(self):
        with patch.object(ultra0, "add_card", return_value=False) as add, \
             patch.object(ultra0, "launch_app") as launch:
            report = ultra0.process(
                "test@example.com", add=False,
                card={"number": "test", "exp": "0129", "cvc": "000", "holder": "Test"})
        self.assertEqual(report["status"], "payment_method_not_confirmed")
        add.assert_called_once()
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
