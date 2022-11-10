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

#Whatever it used to be was way too high and causingh seg faults if you mess up
sys.setrecursionlimit(256)

 collections.abc.Hashable


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
                        "Thread stopping due to exception: "+self.name)
                    raise e
            else:
                try:
                    threadlogger.info("Thread starting: "+self.name)
                    run_old(*args, **kw)
                    threadlogger.info("Thread stopping: "+self.name)

                except Exception as e:
                    threadlogger.exception(
                        "Thread stopping due to exception: "+self.name)
                    from src import messagebus
                    messagebus.postMessage("/system/notifications/errors","Thread: "+self.name +" stopped due to exception ")
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
