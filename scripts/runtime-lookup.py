#!/usr/bin/env python3
"""ASCII-only runtime discovery for Windows PowerShell and other terminals.

The original helpers print Unicode progress banners. Those outputs may fail in
cp1252 pipelines. Capture banners and emit only one Base64-encoded UTF-8 value.
No purchase, offer or payment operations are performed here.
"""
import argparse
import base64
import contextlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class RuntimeUICaptureError(RuntimeError):
    """A recognized UI capture failure, mapped to the shared exit code 23."""


def resolve_value(command, serial=None, vmindex=None):
    with contextlib.redirect_stdout(io.StringIO()):
        if command == "adb":
            import setup_env
            return str(setup_env.find_adb())
        if command == "connect":
            import setup_env
            from device_selector import ensure_online_serials
            return ",".join(ensure_online_serials(setup_env.find_adb()))
        if command == "device":
            import setup_env
            from device_selector import auto_select_device
            return auto_select_device(setup_env.find_adb()) or ""
        if command == "connect-device":
            import setup_env
            return setup_env.connect_emulator(setup_env.find_adb()) or ""
        if command == "start-mumu":
            import os
            from mumu_remote import start_android
            if sys.platform != "win32":
                raise RuntimeError("MuMu startup is Windows-only")
            return start_android(os.environ.get("ADB_PATH", "adb"), vmindex=vmindex)
        if command == "play-accounts-existing":
            # Startup must not install ADB or connect to emulator ports.
            from device_diagnostics import locate_adb
            from device_selector import online_serials
            import ultra0
            adb = locate_adb()
            if not adb or not serial or serial not in online_serials(adb):
                raise RuntimeError("Existing Android transport unavailable")
            ultra0.ADB = adb
            ultra0.SERIAL = serial
            return json.dumps(ultra0.available_google_accounts(), separators=(",", ":"))
        if command in ("play-account", "play-accounts"):
            import ultra0
            ultra0.ADB = ultra0.find_adb()
            ultra0.pick_device(preferred=serial)
            if command == "play-accounts":
                # Candidate list only: not verified as current billing account.
                return json.dumps(ultra0.available_google_accounts(), separators=(",", ":"))
            try:
                return str(ultra0.current_play_account() or "")
            except ultra0.UICaptureError:
                raise RuntimeUICaptureError("Android UI capture failed") from None
    raise ValueError("Unsupported runtime lookup command")


def main(argv=None):
    parser = argparse.ArgumentParser(description="ASCII-safe runtime metadata lookup")
    parser.add_argument("command", choices=("adb", "connect", "device", "connect-device", "start-mumu", "play-account", "play-accounts", "play-accounts-existing"))
    parser.add_argument("--serial", help="ADB device serial (required for play-account)")
    parser.add_argument("--vmindex", type=int, help="Existing MuMu instance number")
    args = parser.parse_args(argv)
    if args.command in ("play-account", "play-accounts", "play-accounts-existing") and not args.serial:
        parser.error("--serial is required for Play account lookup")
    try:
        value = (resolve_value(args.command, args.serial, args.vmindex)
                 if args.command == "start-mumu" else resolve_value(args.command, args.serial))
    except RuntimeUICaptureError:
        return 23
    except (Exception, SystemExit) as exc:
        if args.command == "start-mumu":
            try:
                from mumu_remote import MuMuError
                if isinstance(exc, MuMuError):
                    print("MUMU_RECOVERY:" + str(exc), file=sys.stderr)
                    return 1
            except ImportError:
                pass
        print("Runtime lookup failed ({0}); run python setup_env.py for ADB diagnostics.".format(
            type(exc).__name__), file=sys.stderr)
        return 1
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    print("RUNTIME_RESULT:" + encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
