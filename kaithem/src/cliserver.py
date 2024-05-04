# This file implements a simple sever that CLI tools can use to interact with
# a running kaithem instance.

import base64
import getpass
import hmac
import importlib
import logging
import os
import weakref

import cherrypy

from . import config


class Command:
    def run(self, *a, **k):
        raise NotImplementedError("Someone forgot to override Run")

    def __del__(self):
        logging.warning("CLI command deleted.  Did someone forget a weak ref?")


commands: weakref.WeakValueDictionary[str, Command] = weakref.WeakValueDictionary()

# This key is meant to ensure that nobody other than the user running
# the kaithem process can access the api.
secret_key = base64.b64encode(os.urandom(24)).decode()

with open(f"/dev/shm/kaithem-api-key-{getpass.getuser()}", "w") as f:
    pass

os.chmod(f"/dev/shm/kaithem-api-key-{getpass.getuser()}", 0o600)

with open(f"/dev/shm/kaithem-api-key-{getpass.getuser()}", "a") as f:
    f.write(secret_key)

# be defensive
os.chmod(f"/dev/shm/kaithem-api-key-{getpass.getuser()}", 0o600)


with open(f"/dev/shm/kaithem-api-port-{getpass.getuser()}", "w") as f:
    f.write(str(config.config["http_port"]))


class WebAPI:
    @cherrypy.expose
    def cmd(self, cmd, *args, api_key: str = "", **kw):
        if not hmac.compare_digest(api_key, secret_key):
            raise PermissionError("Correct API key is needed")

        o = commands[cmd]
        o.run(*args, *kw)


class CallAribitraryFunctionCommand(Command):
    def run(self, module, f, *args, **kw):
        """Usage: kaithem-cli from modulename functionname arg1 arg2 arg3"""
        mo = importlib.import_module(module)
        return getattr(mo, f)(*args, **kw)


commands["from"] = CallAribitraryFunctionCommand()
