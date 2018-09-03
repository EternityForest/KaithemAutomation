#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

Code to set up import hooks for Python 2 to automatically strip hints from
modules when they are loaded.  Note the use of `imp` is deprecated for Python 3.

This example code was very helpful: https://github.com/aroberge/splore

"""

from __future__ import print_function, division, absolute_import
import imp
import sys
import os

version = sys.version_info[0]

strip_importer_instance = None # Only install one, then modify its static attributes.

class StripHintsImporter(object):
    """Strip hints on import."""
    stripper_fun_to_use = {} # Dict of stripper funs keyed by canonical dir paths.

    def find_module(self, module_name, path=None):
        """Find the module with the given name.  Uses `path`, or `sys.path` if
        it is omitted.  Returns `(file, pathname, description)`.

        As of now UTF-8 encoding is assumed."""
        self.module_info = imp.find_module(module_name, path)
        return self

    def load_module(self, module_name):
        """Load the module."""
        if module_name in sys.modules:
            return sys.modules[module_name]

        module_path = self.module_info[1]

        # Use regular loader unless in a dir that was registered.
        #print("doing an import...............")
        canonical_module_dir_path = os.path.dirname(os.path.realpath(module_path))
        #print("canonical_module_dir_path =", canonical_module_dir_path)
        if canonical_module_dir_path not in self.stripper_fun_to_use:
            #print("doing normal import since not in dir....")
            module = imp.load_module(module_name, *self.module_info)
            return module
        else:
            stripper_fun_to_use = self.stripper_fun_to_use[canonical_module_dir_path]

        # Attempt to process the module with strip hints.
        try:
            source = stripper_fun_to_use(module_path)
            # TODO: Really should read the encoding magic comment, if there is one,
            # and encode the string in that encoding.
            if version == 2:
                source = source.encode("utf-8")
            #print("the stripped source is:\n", source, sep="")
            module = imp.new_module(module_name)

            # =============
            # Below are like example in https://www.python.org/dev/peps/pep-0302/
            mod = sys.modules.setdefault(module_path, module)
            mod.__file__ = "<%s>" % self.__class__.__name__
            mod.__loader__ = self

            ispkg = self.module_info[0] is None and self.module_info[1] is not None
            if ispkg:
                mod.__path__ = []
                mod.__package__ = module_path
            else:
                mod.__package__ = module_path.rpartition('.')[0]
            # ==============

            sys.modules[module_name] = module
            exec(source, module.__dict__)
        except Exception as e:
            print("strip_hints error in loading module {0}: {1}."
                    .format(module_name, e.__class__.__name__), file=sys.stderr)
            raise # Re-raise instead of fallback to regular import.
            # module = imp.load_module(module_name, *self.module_info)
        return module

def register_stripper_fun(calling_module_file, stripper_fun, py3_also=False):
    """The function called from a module `__init__` or from a script file to
    declare that all later imports from that directory should be processed on
    import to strip type hints.  This is based on the `realpath` of the
    directory of the module."""
    if version == 3 and not py3_also:
        return

    global strip_importer_instance
    if not strip_importer_instance:
        strip_importer_instance = StripHintsImporter()
        sys.meta_path.insert(0, strip_importer_instance)

    canonical_module_dir = os.path.dirname(os.path.realpath(calling_module_file))
    #print("registering import dir", canonical_module_dir)
    strip_importer_instance.stripper_fun_to_use[canonical_module_dir] = stripper_fun

