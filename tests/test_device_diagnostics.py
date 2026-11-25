"""No-device tests for Play Store account and Google One launch diagnostics."""
import importlib.util
import json
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

script = Path(__file__).resolve().parents[1] / "ultra0.py"
spec = importlib.util.spec_from_file_location("ai_diagnostics", script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DeviceDiagnosticsTests(unittest.TestCase):
    def test_google_one_restart_failure_stops_before_relaunch(self):
        def shell(*args, **kwargs):
            if "pm path" in args[1]:
                return "package:/data/app/base.apk"
            if "force-stop" in args[1]:
                self.assertTrue(kwargs.get("check"))
                raise RuntimeError("Could not stop Google One")
            self.fail("Application must not relaunch after a failed stop")

        with patch.object(mod, "sh", side_effect=shell):
            with self.assertRaisesRegex(RuntimeError, "Could not stop"):
                mod.launch_app()

    def test_active_play_account_button_identifies_profile_with_multiple_accounts(self):
        with patch.object(mod, "ui_xml", return_value='<node package="com.android.vending"/>'), \
             patch.object(mod, "nodes", return_value=[
                 {"desc": "Google Account: Test selected@example.com", "text": ""},
                 {"desc": "", "text": "other@example.com"}]), \
             patch.object(mod, "tap") as tap:
            self.assertEqual(mod.current_play_account(), "selected@example.com")
        tap.assert_not_called()

    def test_new_and_localized_active_profile_labels(self):
        for label in ("Signed in as ", "Google Account: ", "T\u00e0i kho\u1ea3n Google: ",
                      "Google \u5e10\u53f7\uff1a", "Google \u8d26\u53f7: "):
            with self.subTest(label=label), \
                 patch.object(mod, "ui_xml", return_value='<node package="com.android.vending"/>'), \
                 patch.object(mod, "nodes", return_value=[
                     {"desc": label + "selected@example.com", "text": ""},
                     {"desc": "", "text": "other@example.com"}]):
                self.assertEqual(mod.current_play_account(), "selected@example.com")

    def test_conflicting_active_profile_labels_fail_closed(self):
        with patch.object(mod, "ui_xml", return_value='<node package="com.android.vending"/>'), \
             patch.object(mod, "nodes", return_value=[
                 {"desc": "Signed in as one@example.com", "text": ""},
                 {"desc": "Google Account: two@example.com", "text": ""}]), \
             patch.object(mod, "tap") as tap:
            self.assertEqual(mod.current_play_account(), "")
        tap.assert_not_called()

    def test_russian_account_settings_label_is_recognized(self):
        with patch.object(mod, "ui_xml", return_value='<node package="com.android.vending"/>'), \
             patch.object(mod, "nodes", side_effect=[
                 [{"desc": "\u0410\u043a\u043a\u0430\u0443\u043d\u0442 \u0438 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438", "text": "", "x": 1, "y": 2}],
                 [{"desc": "selected@example.com", "text": ""}]]), \
             patch.object(mod, "tap") as tap, patch.object(mod, "sh"), patch.object(mod.time, "sleep"):
            self.assertEqual(mod.current_play_account(), "selected@example.com")
        tap.assert_called_once_with(1, 2)

    def test_offer_check_reports_play_store_startup_failure_without_querying(self):
        with ExitStack() as mocks:
            for name in ("find_adb", "pick_device", "ensure_root", "ensure_network",
                         "ensure_frida_server", "ensure_module_apk"):
                mocks.enter_context(patch.object(mod, name))
            vending = mocks.enter_context(patch.object(mod, "ensure_vending", return_value=False))
            query = mocks.enter_context(patch.object(mod, "process"))
            mocks.enter_context(patch.object(Path, "mkdir"))
            report = mocks.enter_context(patch.object(Path, "write_text"))
            mocks.enter_context(patch.object(sys, "argv", ["ultra0.py", "--list"]))
            self.assertEqual(mod.main(), 0)
        vending.assert_called_once_with(retry_startup=True)
        query.assert_not_called()
        self.assertEqual(json.loads(report.call_args.args[0])["status"], "play_store_not_started")

    def test_play_store_startup_retry_is_limited_to_offer_checks(self):
        for retry, expected_launches in ((False, 1), (True, 2)):
            with self.subTest(retry=retry), \
                 patch.object(mod, "sh", return_value="") as adb, \
                 patch.object(mod.time, "sleep"):
                mod.ensure_vending(retry_startup=retry)
            commands = [call.args[1] for call in adb.call_args_list]
            launch = f"monkey -p {mod.VENDING} -c android.intent.category.LAUNCHER 1"
            self.assertEqual(commands.count(launch), expected_launches)
            self.assertEqual(commands.count(f"am force-stop {mod.VENDING}"), int(retry))

    def test_play_store_already_running_is_not_restarted(self):
        with patch.object(mod, "sh", return_value="1234") as adb:
            mod.ensure_vending(retry_startup=True)
        adb.assert_called_once_with("shell", f"pidof {mod.VENDING}")

    def test_unknown_account_fails_closed_without_launching(self):
        with patch.object(mod, "current_play_account", return_value=""), \
             patch.object(mod, "launch_app") as launch:
            result = mod.process("example@example.com", add=False, no_switch=True)
            self.assertEqual(result["status"], "account_unverified")
            launch.assert_not_called()

    def test_account_mismatch_is_separate_from_unknown(self):
        with patch.object(mod, "current_play_account", return_value="another@example.com"), \
             patch.object(mod, "launch_app") as launch:
            result = mod.process("example@example.com", add=False, no_switch=True)
            self.assertEqual(result["status"], "wrong_account")
            launch.assert_not_called()

    def test_play_store_comes_to_foreground_before_account_read(self):
        xml = ['<node package="com.google.android.apps.subscriptions.red" />',
               '<node package="com.android.vending" />',
               '<node package="com.android.vending" />']
        profile = [{"desc": "Account and settings", "text": "", "x": 12, "y": 34}]
        email = [{"desc": "example@example.com", "text": "", "x": 12, "y": 34}]
        called = []
        with patch.object(mod, "ui_xml", side_effect=xml), \
             patch.object(mod, "nodes", side_effect=[profile, email]), \
             patch.object(mod, "tap"), patch.object(mod.time, "sleep"), \
             patch.object(mod, "sh", side_effect=lambda *a, **kw: called.append(a) or ""):
            result = mod.current_play_account()
            self.assertEqual(result, "example@example.com")
            self.assertTrue(any("am start -n com.android.vending/" in " ".join(a) for a in called))

    def test_slow_play_store_profile_icon_is_retried(self):
        xml = ['<node package="com.google.android.apps.subscriptions.red" />',
               '<node package="com.android.vending" />',
               '<node package="com.android.vending" />',
               '<node package="com.android.vending" />']
        loading = [{"desc": "Loading", "text": "", "x": 0, "y": 0}]
        profile = [{"desc": "Account and settings", "text": "", "x": 12, "y": 34}]
        email = [{"desc": "example@example.com", "text": "", "x": 12, "y": 34}]
        with patch.object(mod, "ui_xml", side_effect=xml), \
             patch.object(mod, "nodes", side_effect=[loading, profile, email]), \
             patch.object(mod, "tap"), patch.object(mod.time, "sleep"), \
             patch.object(mod, "sh", return_value=""):
            self.assertEqual(mod.current_play_account(), "example@example.com")

    def test_missing_google_one_is_not_launched(self):
        with patch.object(mod, "sh", return_value="") as adb:
            self.assertEqual(mod.launch_app(), 0)
            self.assertEqual(adb.call_count, 1)

    def test_slow_google_one_launch_is_retried(self):
        seen = {"pid": 0}
        def shell(*args, **kwargs):
            cmd = " ".join(args)
            if "pm path" in cmd: return "package:/data/app/base.apk"
            if "pidof" in cmd:
                seen["pid"] += 1
                return "" if seen["pid"] == 1 else "1234"
            return ""
        with patch.object(mod, "sh", side_effect=shell), patch.object(mod.time, "sleep") as pause:
            self.assertEqual(mod.launch_app(), 1234)
            self.assertEqual(pause.call_count, 2)


if __name__ == "__main__":
    unittest.main()
