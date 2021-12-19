import weakref

import sys
import os
import importlib
import json
import copy 
import logging
from typing import Dict, Type


_known_device_types: Dict[str, Dict]= {}
"""
Cache of discovered data about devices
"""


# Programmatically generated device classes go here
device_classes= weakref.WeakValueDictionary()
"""
This dict lets you programmatically add new devices
"""


def discover() -> Dict[str,Dict]:
    """Search system paths for modules that have a devices manifest.

    Returns:
        A dict indexed by the device type name, with the values being info dicts.
        Keys not documented here should be considered opaque.

        description: A free text, paragraph or less short description, taken from the device manifest.

        importable: The full module(including the submodule) you would import to get the class to build this device.

        classname: The name of the class you would import
    
    """

    paths = copy.deepcopy(sys.path)
    here = os.path.dirname(os.path.abspath(__file__))
    paths.append(here)

    # Priority
    for i in reversed(paths):
        if not os.path.isdir(i):
            continue
        for d in os.listdir(i):
            folder = os.path.join(i,d)
            if os.path.isdir(folder):
                if os.path.isfile(os.path.join(folder, "devices_manifest.json")):
                    try:
                        with open(os.path.join(folder, "devices_manifest.json")) as f:
                            d = f.read()
                            d = json.loads(d)

                        for dev in d['devices']:
                            _known_device_types[dev] = d['devices'][dev]

                            #Special case handling devices included in this library for demo purposes.
                            modulename =os.path.basename(folder)
                            if os.path.dirname(folder)== here:
                                modulename= "iot_device"

                            x = d['devices'][dev].get("submodule",None)
                            if x:
                                modulename=modulename+"."+x

                            _known_device_types[dev]['importable'] = modulename

                            if not 'description' in _known_device_types[dev]:
                                _known_device_types[dev]['description'] = ''

                            if not 'classname' in _known_device_types[dev]:
                                _known_device_types[dev]['classname'] = dev
                    except:
                        logging.exception("Error with devices manifest in: "+folder)
    return _known_device_types


def get_class(data) -> Type:
    """
    Return the class that one would use to construct a device given it's data.  Automatically search all system paths.

    Returns:
        A class, not an instance
    """
    t = data['type']

    if t in device_classes:
        try:
            return device_classes[data]
        except KeyError:
            pass

    if not t in _known_device_types:
        discover()

    classname =  _known_device_types[t].get("classname",t)

    m = _known_device_types[t]['importable']
    module  =  importlib.import_module(m)
    return module.__dict__[classname]
 
