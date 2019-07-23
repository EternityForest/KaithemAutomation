"""Daikin device discovery."""
import socket

from datetime import timedelta
from typing import Dict, List  # noqa: F401
from urllib.parse import unquote

DISCOVERY_MSG = b"DAIKIN_UDP/common/basic_info"

UDP_SRC_PORT = 30000
UDP_DST_PORT = 30050

DISCOVERY_ADDRESS = '<broadcast>'
DISCOVERY_TIMEOUT = timedelta(seconds=2)


class Daikin:
    """Base class to discover Daikin devices."""

    def __init__(self):
        """Initialize the Daikin discovery."""
        self.entries = []  # type: List[Dict[str, str]]

    def scan(self):
        """Scan the network."""
        self.update()

    def all(self):
        """Scan and return all found entries."""
        self.scan()
        return self.entries

    def update(self):
        """Scan network for Daikin devices."""
        entries = []

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(DISCOVERY_TIMEOUT.seconds)
        sock.bind(("", UDP_SRC_PORT))

        try:

            sock.sendto(DISCOVERY_MSG, (DISCOVERY_ADDRESS, UDP_DST_PORT))

            while True:
                try:
                    data, (address, _) = sock.recvfrom(1024)

                    entry = {x[0]: x[1] for x in (
                        e.split('=', 1)
                        for e in data.decode("UTF-8").split(','))}

                    # expecting product, mac, activation code, version
                    if 'ret' not in entry or entry['ret'] != 'OK':
                        # non-OK return on response
                        continue

                    if 'mac' not in entry:
                        # no mac found for device"
                        continue

                    if 'type' not in entry or entry['type'] != 'aircon':
                        # no mac found for device"
                        continue

                    if 'name' in entry:
                        entry['name'] = unquote(entry['name'])

                    # in case the device was not configured to have an id
                    # then use the mac address
                    if 'id' in entry and entry['id'] == '':
                        entry['id'] = entry['mac']

                    entries.append({
                        'id': entry['id'],
                        'name': entry['name'],
                        'ip': address,
                        'mac': entry['mac'],
                        'ver': entry['ver'],
                    })

                except socket.timeout:
                    break

        finally:
            sock.close()

        self.entries = entries


def main():
    """Test Daikin discovery."""
    from pprint import pprint
    daikin = Daikin()
    pprint("Scanning for Daikin devices..")
    daikin.update()
    pprint(daikin.entries)


if __name__ == "__main__":
    main()
