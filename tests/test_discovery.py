import time
import pytest
from desk.discovery import BeaconBroadcaster, BeaconListener

def test_beacon_roundtrip():
    # Use a high random UDP port for discovery test to avoid conflicts
    test_disc_port = 18766
    devices_seen = []

    def on_update(devs):
        nonlocal devices_seen
        devices_seen = devs

    listener = BeaconListener(discovery_port=test_disc_port, on_update=on_update, expiry=2.0)
    listener.start()

    broadcaster = BeaconBroadcaster(
        port=9999,
        discovery_port=test_disc_port,
        name="TestHost",
        protected=True,
        interval=0.2,
    )
    broadcaster.start()

    # Wait for broadcast and listener reception
    t0 = time.time()
    while time.time() - t0 < 3.0:
        if devices_seen:
            break
        time.sleep(0.1)

    broadcaster.stop()
    listener.stop()

    assert len(devices_seen) > 0, "No devices discovered via UDP beacon"
    dev = devices_seen[0]
    assert dev["name"] == "TestHost"
    assert dev["port"] == 9999
    assert dev["protected"] is True
