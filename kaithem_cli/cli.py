import getpass
import os
import sys
import urllib
import urllib.parse

import niquests

args = []
kwargs = {}

for i in sys.argv[1:]:
    if i.startswith("--"):
        a, b = i.split("=", 1)
        a = a[2:]

        kwargs[a] = b
    else:
        args.append(i)

with open("/dev/shm/kaithem-api-key-" + getpass.getuser()) as f:
    key = f.read()

with open("/dev/shm/kaithem-api-port-" + getpass.getuser()) as f:
    port = f.read()

cmd = [sys.argv[1]] + args[1:]


url = (
    "http://localhost:"
    + port
    + "/cli/cmd/"
    + "/".join(urllib.parse.quote(i, "") for i in cmd)
)

kwargs["api_key"] = key


def main():
    r = niquests.post(
        url, data=kwargs, timeout=float(kwargs.get("timeout", 15))
    )

    with os.fdopen(sys.stdout.fileno(), "wb", closefd=False) as stdout:
        stdout.write(r.content)
        stdout.flush()


if __name__ == "__main__":
    main()
