"""Explicit Windows MuMu startup, adapted from contributor PR #92."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import time


class MuMuError(RuntimeError):
    """Safe startup error; never includes raw tool output."""


def find_manager(mumu_dir: str | None = None) -> Path:
    configured = mumu_dir or os.environ.get("MUMU_DIR")
    roots = [Path(configured)] if configured else [
        Path(root) / "Netease" / name
        for root in (os.environ.get("ProgramFiles", "C:/Program Files"),
                     os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"),
                     "D:/Program Files")
        for name in ("MuMu", "MuMuPlayer", "MuMuPlayer-12.0",
                     "MuMuPlayerGlobal-12.0", "MuMu Player 12")
    ]
    for root in roots:
        for manager in (root / "nx_main" / "MuMuManager.exe", root / "shell" / "MuMuManager.exe", root / "MuMuManager.exe"):
            if manager.is_file():
                return manager
    raise MuMuError("MuMu Manager not found. Install MuMu or configure MUMU_DIR.")


def _run(args, timeout):
    return subprocess.run(args, capture_output=True, text=True,
                          errors="replace", timeout=timeout)


def _remaining(deadline, cap):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise MuMuError("MuMu startup timed out. Check Android boot and ADB debugging.")
    return min(remaining, cap)


def _manager(manager, args, deadline, operation):
    try:
        result = _run([str(manager), *args], _remaining(deadline, 30))
    except (OSError, subprocess.TimeoutExpired):
        raise MuMuError(f"MuMu {operation} failed. Check the manager and retry.") from None
    if result.returncode:
        raise MuMuError(f"MuMu {operation} failed. Check the manager and retry.")
    return result.stdout


def _instances(manager, deadline):
    raw = _manager(manager, ["info", "-v", "all"], deadline, "instance query")
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError
        if "adb_port" in data or "vmindex" in data or "index" in data:
            index = str(data.get("vmindex", data.get("index", "")))
            if not index.isdecimal():
                raise ValueError
            return {int(index): data}
        if any(not isinstance(v, dict) or not str(k).isdecimal() for k, v in data.items()):
            raise ValueError
        return {int(k): v for k, v in data.items()}
    except (ValueError, TypeError):
        raise MuMuError("MuMu instance metadata is invalid. Open MuMu manually.") from None


def connect_existing_instance(adb_path: str, poll):
    """Start a player, then verify that any additional transports are aliases."""
    from device_selector import same_boot_transports
    serial = start_android(adb_path)
    observed = poll()
    if observed.state != "connected" or not same_boot_transports(
            adb_path, serial, observed.devices):
        raise MuMuError("The started instance is not the only online device. Disconnect other devices or select explicitly.")
    return observed


def start_android(adb_path: str, vmindex: int | None = None,
                  mumu_dir: str | None = None, timeout_seconds: int = 180) -> str:
    """Launch an existing player, never create a VM or select unrelated ADB devices."""
    manager = find_manager(mumu_dir)
    adb = shutil.which(adb_path) or (adb_path if Path(adb_path).is_file() else None)
    if not adb:
        raise MuMuError("ADB not found. Install Android platform-tools first.")
    if timeout_seconds <= 0:
        raise MuMuError("MuMu startup timeout must be positive.")
    deadline = time.monotonic() + timeout_seconds
    _manager(manager, ["main", "launch"], deadline, "main launch")
    known = _instances(manager, deadline)
    if vmindex is None:
        if len(known) != 1:
            raise MuMuError("No unique MuMu instance. Open the intended existing instance manually.")
        vmindex = next(iter(known))
    if vmindex not in known:
        raise MuMuError("Requested MuMu instance not found. Check the instance number.")
    _manager(manager, ["control", "--vmindex", str(vmindex), "launch"], deadline, "instance launch")
    while time.monotonic() < deadline:
        try:
            info = _instances(manager, deadline).get(vmindex, {})
            port = str(info.get("adb_port", ""))
            if port.isdecimal() and 1 <= int(port) <= 65535:
                serial = f"127.0.0.1:{int(port)}"
                try:
                    _run([adb, "connect", serial], _remaining(deadline, 8))
                except subprocess.TimeoutExpired:
                    pass
                result = _run([adb, "devices"], _remaining(deadline, 8))
                if not result.returncode and any(
                    line.split()[:2] == [serial, "device"]
                    for line in result.stdout.splitlines()
                ):
                    current = _instances(manager, deadline).get(vmindex, {})
                    if str(current.get("adb_port", "")) == port:
                        return serial
        except (subprocess.TimeoutExpired, MuMuError):
            # Manager metadata may be temporarily unavailable while Android boots.
            # The shared deadline still bounds all polling attempts.
            pass
        except OSError:
            raise MuMuError("ADB could not run. Check Android platform-tools.") from None
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    raise MuMuError("MuMu startup timed out. Check Android boot and ADB debugging.")
