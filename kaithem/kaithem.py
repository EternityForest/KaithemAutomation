#!/usr/bin/python3

# This is your primary launcher, if starting on a Linux system


# Hack to keep pyyaml working till we find a better way
try:
    import collections.abc
    collections.Hashable = collections.abc.Hashable
    collections.Callable = collections.abc.Callable
    collections.MutableMapping = collections.abc.MutableMapping
except Exception:
    pass

from src import main 
