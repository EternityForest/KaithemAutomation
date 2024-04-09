# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

"""This file handles the big configuration file, provides access to it, and handles default settings"""

import argparse
import logging
import os
import sys
from typing import Any, Dict, Optional

import jsonschema
import yaml

logger = logging.getLogger("system")
config = {}

##########################################################
# Modified code from ibt of stackoverflow. Uses literal style for scalars instead of ugly folded.


def should_use_block(value):
    if "\n" in value:
        return True
    if "\r" in value:
        return True
    return False


def my_represent_scalar(self, tag, value, style=None):
    if style is None:
        if should_use_block(value):
            style = "|"
        else:
            style = self.default_style

    node = yaml.representer.ScalarNode(tag, value, style=style)
    if self.alias_key is not None:
        self.represented_objects[self.alias_key] = node
    return node


yaml.representer.BaseRepresenter.represent_scalar = my_represent_scalar

_dn = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "data")

#################################################################

_argp = argparse.ArgumentParser()

# Manually specify a confifuration file, or else there must be one in /etc/kaithem
_argp.add_argument("-c")
_argp.add_argument("-p")
_argp.add_argument("--initialpackagesetup")

argcmd = _argp.parse_args(sys.argv[1:])


def load(cfg: Dict[str, Any]):
    "Param overrtides defaults"
    # This can't bw gotten from directories or wed get a circular import
    with open(os.path.join(_dn, "default_configuration.yaml")) as f:
        _defconfig = yaml.load(f, Loader=yaml.SafeLoader)
    # Config starts out as the default but individual options
    # Can be added or overridden by the user's settings.
    config = _defconfig.copy()

    config.update(cfg or {})

    vardir = os.path.expanduser(config["site-data-dir"])
    default_conf_location = os.path.join(vardir, "config.yaml")

    # Attempt to open any manually specified config file
    if argcmd.c:
        with open(argcmd.c) as f:
            _usr_config = yaml.load(f, yaml.SafeLoader) or {}
            logger.info("Loaded configuration from " + argcmd.c)

    elif os.path.exists(default_conf_location):
        with open(default_conf_location) as f:
            _usr_config = yaml.load(f, yaml.SafeLoader) or {}
            logger.info("Loaded configuration from " + default_conf_location)

    else:
        _usr_config = {}
        logger.info("No CFG File Specified. Using Defaults.")

    for i in _usr_config:
        config[i] = _usr_config[i]

    if argcmd.p:
        config["https-port"] = int(argcmd.p)
    return config


def reload():
    c = load()
    with open(os.path.join(_dn, "config-schema.yaml")) as f:
        jsonschema.validate(c, yaml.load(f, Loader=yaml.SafeLoader))
    config.update(c)


def initialize(cfg: Optional[Dict[str, Any]] = None):
    "Load the config from defaults and the command line,"
    c = load(cfg)
    with open(os.path.join(_dn, "config-schema.yaml")) as f:
        jsonschema.validate(c, yaml.load(f, Loader=yaml.SafeLoader))
    # Allow code to set config keys before this loads that can override the
    # file
    c.update(config)
    config.update(c)
