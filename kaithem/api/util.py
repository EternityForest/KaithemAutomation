import os
import random

from scullery import persist

from kaithem.src import config, directories, util

sentences: list[str] = []

if config.config["quotes_file"] == "default":
    sentences = persist.load(os.path.join(directories.datadir, "quotes.yaml"))
else:
    sentences = persist.load(config.config["quotes_file"])


def bip39_hash(
    input: str | bytes, num_words: int = 4, separator: str = " "
) -> str:
    """Return a bip39 hash of a string or bytes object"""
    if isinstance(input, str):
        val = input.encode("utf-8")
    else:
        val = input
    return util.memorableHash(val, num=num_words, separator=separator)


def lorem() -> str:
    "Return a random sentence from the quotes.yaml file"
    return random.choice(sentences)


def get_logdir() -> str:
    """Get the user and machine specific log directory"""
    return directories.logdir


def get_vardir() -> str:
    """Get the main kaithem storage dir"""
    return directories.vardir


def get_builtin_datadir() -> str:
    """Get the builtin data dir.
    Do not rely on things in this dir not changing"""
    return directories.datadir
