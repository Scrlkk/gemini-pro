"""Safe auto-selection of Android devices exposed through multiple ADB transports.

Aliases are deduplicated ONLY if they share the same kernel boot UUID.
When devices differ, choose a unique device running Google One or the only
one with Google One installed. Never choose arbitrarily among candidates.
"""
import re
import socket
import subprocess

GOOGLE_ONE = "com.google.android.apps.subscriptions.red"
BOOT_UUID = re.compile(r"^[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}$")
# MuMu 12 instances increment by 32 from 16384; keep legacy MuMu/Nox/LDPlayer ports as fallback.
EMULATOR_PORTS = ("16384", "16416", "16448", "16480", "16512", "7555", "21503", "62001")


def adb_command(adb, *args):
    try:
        return subprocess.run([str(adb), *args], capture_output=True,
                              text=True, errors="replace", timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return None


def online_serials(adb):
    result = adb_command(adb, "devices")
    if result is None or result.returncode != 0:
        return []
    online = []
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "device":
            online.append(fields[0])
    return online


def _is_local_port_open(port, timeout=0.25):
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_online_serials(adb, ports=EMULATOR_PORTS):
    """Return online ADB serials, probing listening local emulator ports if none are online."""
    online = online_serials(adb)
    if online:
        return online
    for port in ports:
        if not _is_local_port_open(port):
            continue
        adb_command(adb, "connect", f"127.0.0.1:{port}")
        online = online_serials(adb)
        if online:
            break
    return online


def boot_uuid(adb, serial):
    result = adb_command(adb, "-s", serial, "shell", "cat", "/proc/sys/kernel/random/boot_id")
    if result is None or result.returncode != 0:
        return ""
    value = result.stdout.strip()
    return value.lower() if BOOT_UUID.fullmatch(value) else ""


def running_google_one(adb, serial):
    result = adb_command(adb, "-s", serial, "shell", "pidof", GOOGLE_ONE)
    return bool(result is not None and result.returncode == 0 and
                any(token.isdigit() for token in result.stdout.split()))


def installed_google_one(adb, serial):
    result = adb_command(adb, "-s", serial, "shell", "pm", "path", GOOGLE_ONE)
    return bool(result is not None and result.returncode == 0 and
                "package:" in result.stdout)


def prefer_alias(serials):
    # Use emulator-5554 before TCP transports ONLY for proven VM aliases.
    return sorted(serials, key=lambda s: (
        0 if re.fullmatch(r"emulator-\d+", s) else 1, s))[0]


def same_boot_transports(adb, selected, serials):
    """True only when all observed transports belong to the selected device."""
    online = list(dict.fromkeys(serials))
    if selected not in online:
        return False
    if len(online) == 1:
        return True
    identity = boot_uuid(adb, selected)
    return bool(identity and all(boot_uuid(adb, serial) == identity
                                 for serial in online if serial != selected))


def auto_select_device(adb, *, preferred=None, serials=None):
    """Return a single serial, or None if there is no safe unique choice."""
    online = list(dict.fromkeys(serials if serials is not None else online_serials(adb)))
    if preferred:
        return preferred if preferred in online else None
    if not online:
        return None
    if len(online) == 1:
        return online[0]

    groups = {}
    for serial in online:
        boot = boot_uuid(adb, serial)
        key = "boot:" + boot if boot else "transport:" + serial
        groups.setdefault(key, []).append(serial)
    representatives = [prefer_alias(group) for group in groups.values()]
    if len(representatives) == 1:
        return representatives[0]

    for test in (running_google_one, installed_google_one):
        candidates = [s for s in representatives if test(adb, s)]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            return None
    return None
