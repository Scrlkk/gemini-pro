#!/usr/bin/env python3
"""One-shot, read-only SKU metadata query on the device verified by Step 1.

No signup, account switching, Play UI taps, setup repairs or checkout.
Prints one token-free JSON object on stdout. No logs or reports are saved.
"""
from __future__ import annotations

import argparse
import json
import re
import signal
import subprocess
import sys
import threading
from pathlib import Path

from device_diagnostics import locate_adb
from device_selector import online_serials
from sku_check_core import sanitize_offers, validate_skus

ROOT = Path(__file__).resolve().parent
PKG = "com.google.android.apps.subscriptions.red"
SERIAL_RE = re.compile(r"^[A-Za-z0-9._:-]{1,90}$")
ALLOWED_CODES = {
    "observed", "no_offers", "not_returned", "device_not_ready",
    "billing_unavailable", "timeout", "query_error", "cancelled", "unusable_metadata",
}


def fail(code: str) -> dict:
    return {
        "status": code if code in ALLOWED_CODES else "query_error",
        "items": [], "missing_skus": [],
        "account_binding_verified": False,
        "eligibility_verified": False, "subscription_active_verified": False,
    }


def find_adb() -> str | None:
    """Use the shared non-installing locator, including local platform-tools."""
    return locate_adb()


def _bounded_cleanup(action, timeout: float = 2.0) -> bool:
    """Do not let an unresponsive native cleanup block CLI output indefinitely."""
    completed = threading.Event()

    def run():
        try:
            action()
        except Exception:
            pass
        finally:
            completed.set()

    threading.Thread(target=run, daemon=True, name="sku-cleanup").start()
    return completed.wait(timeout)


def _adb_output(adb: str, serial: str, *args: str) -> str:
    try:
        result = subprocess.run(
            [adb, "-s", serial, "shell", *args],
            capture_output=True, timeout=10, check=False,
        )
        return result.stdout.decode("utf-8", "replace").strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _frida_device(adb: str, serial: str, pid: int):
    # Reuse the existing engine's strict device/PID mapping. It writes local
    # diagnostics, so discard them here rather than corrupting the JSON output.
    import contextlib
    import io
    import ultra0
    previous_adb = ultra0.ADB
    try:
        ultra0.ADB = adb
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return ultra0.get_target_frida_device(pid, serial)
    finally:
        ultra0.ADB = previous_adb


def check_skus(serial: str, skus: list[str], timeout: int = 25) -> dict:
    """One query, no retries. Strict same-device check and guaranteed detach."""
    try:
        validated = validate_skus(skus)
        if not SERIAL_RE.fullmatch(serial):
            return fail("device_not_ready")
        adb = find_adb()
        if not adb or serial not in online_serials(adb):
            return fail("device_not_ready")
        # No am start, force-stop, input tap, root setup, proxy change or APK push.
        pid_text = _adb_output(adb, serial, "pidof", PKG)
        pids = pid_text.split()
        if len(pids) != 1 or not pids[0].isdigit():
            return fail("device_not_ready")
        pid = int(pids[0])
        module = _adb_output(adb, serial, "ls", "/data/local/tmp/module_521.apk")
        if "module_521.apk" not in module:
            return fail("device_not_ready")
        dev = _frida_device(adb, serial, pid)
        if dev is None:
            return fail("device_not_ready")
        if _adb_output(adb, serial, "pidof", PKG) != str(pid):
            return fail("device_not_ready")

        from importlib import resources
        del resources  # Explicitly no dynamic download or loader installation.
        source = (ROOT / "assets/frida/sku_query_readonly.js").read_text(encoding="utf-8")
        needle = "var SKU_REQUEST = [];"
        if source.count(needle) != 1:
            return fail("query_error")
        source = source.replace(needle, "var SKU_REQUEST = " + json.dumps(validated) + ";")
        session = None
        script = None
        done = threading.Event()
        raw: list[dict] = []
        returned_skus: set[str] = set()
        no_offer_skus: set[str] = set()
        truncated = False
        completed = {"code": "query_error"}

        def receive(message, _data):
            nonlocal truncated
            if message.get("type") == "error":
                completed["code"] = "query_error"
                done.set()
                return
            payload = message.get("payload")
            if not isinstance(payload, dict):
                return
            ev = payload.get("ev")
            if ev == "offer":
                sku = payload.get("sku")
                if sku not in validated:
                    return
                returned_skus.add(sku)
                if payload.get("no_offers") is True:
                    no_offer_skus.add(sku)
                elif len(raw) < 100:
                    raw.append({key: payload.get(key) for key in
                                ("sku", "offer_id", "base_plan_id", "phases")})
                else:
                    truncated = True
            elif ev == "done":
                code = payload.get("code")
                completed["code"] = code if code in ("ok", "billing_unavailable", "device_not_ready") else "query_error"
                done.set()

        try:
            session = dev.attach(pid)
            script = session.create_script(source)
            script.on("message", receive)
            script.load()
            if not done.wait(timeout):
                return fail("timeout")
            if completed["code"] != "ok":
                return fail(completed["code"])
            if serial not in online_serials(adb) or _adb_output(adb, serial, "pidof", PKG) != str(pid):
                return fail("device_not_ready")
            return sanitize_offers(raw, validated,
                                   returned_skus=tuple(returned_skus),
                                   no_offer_skus=tuple(no_offer_skus),
                                   truncated=truncated)
        finally:
            if script is not None:
                _bounded_cleanup(lambda: script.exports_sync.close())
            if session is not None:
                _bounded_cleanup(session.detach)
    except (Exception, SystemExit):
        # Never print exceptions: Frida/debug strings can expose device details.
        return fail("query_error")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only ProductDetails inspection; NO checkout")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--sku", action="append", required=True)
    args = parser.parse_args(argv)
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, interrupted)
    try:
        result = check_skus(args.serial, args.sku)
    except KeyboardInterrupt:
        result = fail("cancelled")
    except (Exception, SystemExit):
        result = fail("query_error")
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0 if result["status"] in ("observed", "no_offers", "not_returned", "unusable_metadata") else 1


if __name__ == "__main__":
    raise SystemExit(main())
