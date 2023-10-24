#!/usr/bin/python3
# Copyright Daniel Dunn 2013-2015
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


import logging
import traceback
import threading
import http.cookies

import sys
import re
import os

def test_access(i):
    try:
        os.listdir(i)
        return True
    except Exception:
        return False


original_path = sys.path
# Snapcraft is putting in nonsense path entries
sys.path = [i for i in sys.path if test_access(i)]


#Whatever it used to be was way too high and causingh seg faults if you mess up
sys.setrecursionlimit(256)

# Compatibility with older libraries.
try:
    import collections.abc
    collections.Hashable = collections.abc.Hashable
    collections.Callable = collections.abc.Callable
    collections.MutableMapping = collections.abc.MutableMapping
    collections.Mapping = collections.abc.Mapping
    collections.Iterable = collections.abc.Iterable
except Exception:
    pass

# Library that makes threading and lock operations, which we use a lot of, use native code on linux
try:
    import pthreading
    pthreading.monkey_patch()
except Exception:
    pass

# Dump stuff to stderr when we get a segfault
try:
    import faulthandler
    faulthandler.enable()
except Exception:
    logger.exception(
        "Faulthandler not found. Segfault error messages disabled. use pip3 install faulthandler to fix"
    )


# Python 3.7 doesn't support the samesite attribute, which we need.
try:
    http.cookies.Morsel._reserved['samesite'] = 'SameSite'
except:
    logging.exception("Samesite enable monkeypatch did not work. It is probably no longer needed on newer pythons, ignore this message")

threadlogger = logging.getLogger("system.threading")

class rtMidiFixer():
    def __init__(self,obj):
        self.__obj=obj
        
    def __getattr__(self,attr):
        if hasattr(self.__obj,attr):
            return getattr(self.__obj,attr)
        #Convert from camel to snake API
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', attr).lower()
        return getattr(self.__obj,name)
    
    def delete(self):
        #Let GC do this
        pass
        
    def __del__(self):
        try:
            self.__obj.delete()
        except AttributeError:
            self.__obj.close_port()
        self.__obj=None
    
try:
    import rtmidi
    if hasattr(rtmidi,"MidiIn"):
        def mget(*a,**k):
            m=rtmidi.MidiIn(*a,**k)
            return rtMidiFixer(m)
        rtmidi.RtMidiIn =mget
        
        
    if hasattr(rtmidi,"MidiOut"):
        def moget(*a,**k):
            m=rtmidi.MidiOut(*a,**k)
            return rtMidiFixer(m)
        rtmidi.RtMidiOut =moget
except:
    logging.exception("RtMidi compatibility error")



def installThreadLogging():
    """
    Workaround for sys.excepthook thread bug
    From
    http://spyced.blogspot.com/2007/06/workaround-for-sysexcepthook-bug.html
    (https://sourceforge.net/tracker/?func=detail&atid=105470&aid=1230540&group_id=5470).
    Call once from __main__ before creating any threads.
    If using psyco, call psyco.cannotcompile(threading.Thread.run)
    since this replaces a new-style class method.

    Modified by kaithem project to do something slightly different. Credit to Ian Beaver.
    What our version does is posts to the message bus when a thread starts, stops, or has an exception.
    """
    init_old = threading.Thread.__init__

    def init(self, *args, **kwargs):
        init_old(self, *args, **kwargs)
        run_old = self.run

        def run_with_except_hook(*args, **kw):
            if self.name.startswith("nostartstoplog."):
                try:
                    run_old(*args, **kw)
                except Exception as e:
                    threadlogger.exception(
                        "Thread stopping due to exception: "+self.name +  " with ID: " +  str(threading.current_thread().ident))
                    raise e
            else:
                try:
                    threadlogger.info("Thread starting: "+self.name +  " with ID: " +  str(threading.current_thread().ident))
                    run_old(*args, **kw)
                    threadlogger.info("Thread stopping: "+self.name +  " with ID: " +  str(threading.current_thread().ident))

                except Exception as e:
                    threadlogger.exception(
                        "Thread stopping due to exception: "+self.name +  " with ID: " +  str(threading.current_thread().ident))
                    from . import messagebus
                    messagebus.postMessage("/system/notifications/errors","Thread: " + self.name + " with ID: " + str(threading.current_thread().ident) + " stopped due to exception ")
                    raise e
        # Rename thread so debugging works
        try:
            if self._target:
                run_with_except_hook.__name__ = self._target.__name__
                run_with_except_hook.__module__ = self._target.__module__
        except:
            try:
                run_with_except_hook.__name__ = "run"
            except:
                pass
        self.run = run_with_except_hook
    threading.Thread.__init__ = init

installThreadLogging()