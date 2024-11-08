# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

"""This file handles the big configuration file, provides access to it, and handles default settings"""

import argparse
import os
import sys
from typing import Any

import jsonschema
import structlog
import yaml
from scullery import snake_compat

logger = structlog.get_logger(__name__)
config: dict[str, Any] = {}

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


def load(cfg: dict[str, Any]):
    "Param overrtides defaults"
    _argp = argparse.ArgumentParser()

    # Manually specify a confifuration file, or else there must be one in /etc/kaithem
    _argp.add_argument("-d")
    _argp.add_argument("-p")

    # Debig runners put weird stuff that breaks things
    if "pytest" in sys.argv[0]:
        argcmd = _argp.parse_args([])
    else:
        argcmd = _argp.parse_args(sys.argv[1:])

    # This can't bw gotten from directories or wed get a circular import
    with open(os.path.join(_dn, "default_configuration.yaml")) as f:
        _defconfig = yaml.load(f, Loader=yaml.SafeLoader)
    # Config starts out as the default but individual options
    # Can be added or overridden by the user's settings.
    config = _defconfig.copy()

    config.update(cfg or {})
    config = snake_compat.snakify_dict_keys(config)

    default_conf_location = os.path.expanduser("~/kaithem/config.yaml")
    vd = os.path.expanduser("~/kaithem/")

    _usr_config = {}

    # Attempt to open any manually specified config file
    if argcmd.d:
        vd = os.path.expanduser(argcmd.d)
        with open(os.path.join(vd, "config.yaml")) as f:
            _usr_config = yaml.load(f, yaml.SafeLoader) or {}
            logger.info(
                "Loaded configuration from " + os.path.join(vd, "config.yaml")
            )

    if "site_data_dir" in cfg:
        p = os.path.join(cfg["site_data_dir"], "config.yaml")
        vd = cfg["site_data_dir"]
        if os.path.exists(p):
            with open(p) as f:
                _usr_config = yaml.load(f, yaml.SafeLoader) or {}
                logger.info("Loaded configuration from " + p)

    elif os.path.exists(default_conf_location):
        with open(default_conf_location) as f:
            _usr_config = yaml.load(f, yaml.SafeLoader) or {}
            logger.info("Loaded configuration from " + default_conf_location)

    else:
        _usr_config = {}
        logger.info("No CFG File Specified. Using Defaults.")

    config["site_data_dir"] = vd

    for i in _usr_config:
        config[i] = _usr_config[i]

    if argcmd.p:
        config["https_port"] = int(argcmd.p)
    return config


def initialize(cfg: dict[str, Any] | None = None):
    "Load the config from defaults and the command line,"
    c = load(cfg or {})
    with open(os.path.join(_dn, "config-schema.yaml")) as f:
        jsonschema.validate(c, yaml.load(f, Loader=yaml.SafeLoader))
    # Allow code to set config keys before this loads that can override the
    # file
    c.update(config)
    config.update(c)
