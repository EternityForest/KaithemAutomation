from .client import Client
from .server import Server, Register

#The default daemon status of the threads for newly created server objects
daemon = False


def _execute(f):
    f()

#Must be a function that takes a function and executes it. This will be the default function
#used to execute user-supplied callbacks when you don't supply a function at object creation of the server
#and client, and can be used to run them in a thread pool.
execute = _execute