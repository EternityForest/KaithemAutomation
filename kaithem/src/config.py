# Copyright Daniel Dunn 2013
# This file is part of Kaithem Automation.

# Kaithem Automation is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Kaithem Automation is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

"""This file handles the big configuration file, provides access to it, and handles default settings"""

import yaml
import argparse
import sys
import os
import jsonschema
import logging
from typing import Optional, Dict, Any

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
_argp.add_argument("--nosecurity")

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

    # Attempt to open any manually specified config file
    if argcmd.c:
        with open(argcmd.c) as f:
            _usr_config = yaml.load(f, yaml.SafeLoader)
            logger.info("Loaded configuration from " + argcmd.c)
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
    "Load the config from defaults and the command line, "
    c = load(cfg)
    with open(os.path.join(_dn, "config-schema.yaml")) as f:
        jsonschema.validate(c, yaml.load(f, Loader=yaml.SafeLoader))
    # Allow code to set config keys before this loads that can override the
    # file
    c.update(config)
    config.update(c)
