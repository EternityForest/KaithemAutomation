import os
import random

from scullery import persist

from kaithem.src import config, directories

sentences: list[str] = []

if config.config["quotes_file"] == "default":
    sentences = persist.load(os.path.join(directories.datadir, "quotes.yaml"))
else:
    sentences = persist.load(config.config["quotes_file"])


def lorem() -> str:
    "Return a random sentence from the quotes.yaml file"
    return random.choice(sentences)


def get_logdir() -> str:
    """Get the user and machine specific log directory"""
    return directories.logdir
