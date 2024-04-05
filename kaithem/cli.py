import sys
import urllib.parse
import requests
import getpass
import urllib

args = []
kwargs = {}

for i in sys.argv[1:]:
    if i.startswith("--"):
        a, b = i.split("=", 1)
        a = a[2:]

        kwargs[a] = b
    else:
        args.append(i)

with open("/dev/shm/kaithem-api-key-" + getpass.getuser(), "r") as f:
    key = f.read()

with open("/dev/shm/kaithem-api-port-" + getpass.getuser(), "r") as f:
    port = f.read()

cmd = [sys.argv[1]] + args


url = (
    "http://localhost:"
    + port
    + "/cli/cmd/"
    + "/".join(urllib.parse.quote(i, "") for i in cmd)
)

kwargs["api_key"] = key

print(requests.post(url, data=kwargs, timeout=float(kwargs.get("timeout", 15))))
