"""Offline startup regression tests."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import mumu_remote as mu


class MuMuTests(unittest.TestCase):
    def test_custom_manager(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = Path(directory) / "nx_main" / "MuMuManager.exe"
            manager.parent.mkdir()
            manager.touch()
            self.assertEqual(mu.find_manager(directory), manager)

    def test_shell_manager_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = Path(directory) / "shell" / "MuMuManager.exe"
            manager.parent.mkdir()
            manager.touch()
            self.assertEqual(mu.find_manager(directory), manager)

    def test_started_device_aliases_are_accepted_but_distinct_devices_are_not(self):
        from device_diagnostics import ConnectionStatus
        serial = "127.0.0.1:16416"
        observed = ConnectionStatus("connected", ("emulator-5554", serial))
        for identities, succeeds in ((["boot-a", "boot-a"], True),
                                      (["boot-a", "boot-b"], False),
                                      (["", ""], False)):
            with self.subTest(identities=identities), \
                 patch.object(mu, "start_android", return_value=serial), \
                 patch("device_selector.boot_uuid", side_effect=identities):
                if succeeds:
                    self.assertEqual(mu.connect_existing_instance("adb", lambda: observed), observed)
                else:
                    with self.assertRaises(mu.MuMuError):
                        mu.connect_existing_instance("adb", lambda: observed)

    def test_manager_failure_is_safe(self):
        with patch.object(mu, "_run", return_value=subprocess.CompletedProcess([], 1, "", "private@example.com")):
            with self.assertRaisesRegex(mu.MuMuError, "^MuMu main launch failed"):
                mu._manager(Path("manager"), ["main", "launch"], mu.time.monotonic()+10, "main launch")

    def test_multiple_instances_do_not_launch_without_choice(self):
        with patch.object(mu, "find_manager", return_value=Path("manager")), \
             patch.object(mu.shutil, "which", return_value="adb"), \
             patch.object(mu, "_manager") as manager, \
             patch.object(mu, "_instances", return_value={2: {}, 5: {}}):
            with self.assertRaisesRegex(mu.MuMuError, "No unique"):
                mu.start_android("adb")
            manager.assert_called_once()

    def test_dynamic_port_binds_selected_instance_and_ignores_other_device(self):
        info = [{2: {}, 5: {}}, {5: {}}, {5: {"adb_port": 16416}}, {5: {"adb_port": 16416}}]
        output = subprocess.CompletedProcess([], 0, "other\tdevice\n127.0.0.1:16416\tdevice\n", "")
        with patch.object(mu, "find_manager", return_value=Path("manager")), \
             patch.object(mu.shutil, "which", return_value="adb"), \
             patch.object(mu, "_manager") as manager, \
             patch.object(mu, "_instances", side_effect=info), \
             patch.object(mu, "_run", side_effect=[subprocess.TimeoutExpired("adb", 1), output]), \
             patch.object(mu.time, "sleep"):
            self.assertEqual(mu.start_android("adb", vmindex=5), "127.0.0.1:16416")
            self.assertEqual(manager.call_args.args[1], ["control", "--vmindex", "5", "launch"])

    def test_flat_stopped_instance_metadata_without_adb_port(self):
        with patch.object(mu, "_manager", return_value=json.dumps({"vmindex": 7, "name": "stopped"})):
            self.assertEqual(mu._instances(Path("manager"), 0), {7: {"vmindex": 7, "name": "stopped"}})

    def test_flat_metadata_requires_actual_instance_index(self):
        with patch.object(mu, "_manager", return_value=json.dumps({"adb_port": 1234, "vmindex": 7})):
            self.assertEqual(mu._instances(Path("manager"), 0), {7: {"adb_port": 1234, "vmindex": 7}})
        with patch.object(mu, "_manager", return_value='{"adb_port": 1234}'):
            with self.assertRaises(mu.MuMuError):
                mu._instances(Path("manager"), 0)


if __name__ == "__main__":
    unittest.main()
