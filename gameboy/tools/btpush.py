#!/usr/bin/env -S uv run --quiet --with dbus-next python3
# btpush.py — push a file to the N810 over Bluetooth OBEX Object Push.
#
#   tools/btpush.py <file> [mac]
#
# Talks to org.bluez.obex (bluez-obex package). obexd activates on demand in
# the user session; if it's not running this starts it via D-Bus activation.
import asyncio
import sys
from pathlib import Path

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus

N810 = "00:1D:6E:D4:C7:62"
OBEX = "org.bluez.obex"


async def push(mac: str, path: str) -> int:
    src = str(Path(path).resolve())
    bus = await MessageBus(bus_type=BusType.SESSION).connect()

    client = bus.get_proxy_object(
        OBEX, "/org/bluez/obex", await bus.introspect(OBEX, "/org/bluez/obex")
    ).get_interface("org.bluez.obex.Client1")

    session_path = await client.call_create_session(mac, {"Target": Variant("s", "opp")})
    print(f"session: {session_path}")

    session = bus.get_proxy_object(
        OBEX, session_path, await bus.introspect(OBEX, session_path)
    )
    opp = session.get_interface("org.bluez.obex.ObjectPush1")
    props = session.get_interface("org.freedesktop.DBus.Properties")

    done = asyncio.Event()
    result = {"status": "unknown"}

    def on_props_changed(iface, changed, invalidated):
        if "Status" in changed:
            result["status"] = changed["Status"].value
            if result["status"] in ("complete", "error"):
                done.set()

    props.on_properties_changed(on_props_changed)

    transfer_path, _ = await opp.call_send_file(src)
    print(f"transfer started: {transfer_path} — accept it on the N810")

    await asyncio.wait_for(done.wait(), timeout=300)
    print(f"status: {result['status']}")
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    f = sys.argv[1] if len(sys.argv) > 1 else None
    mac = sys.argv[2] if len(sys.argv) > 2 else N810
    if not f or not Path(f).is_file():
        sys.exit(f"usage: btpush.py <file> [mac]  (file must exist)")
    try:
        sys.exit(asyncio.run(push(mac, f)))
    except Exception as e:
        sys.exit(f"btpush: {e}")
