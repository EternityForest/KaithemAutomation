#!/usr/bin/python3
#Copyright Daniel Dunn 2013-2015
#This file is part of Kaithem Automation.

#Kaithem Automation is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Kaithem Automation is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.



import logging,traceback,threading

threadlogger = logging.getLogger("system.threading")
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
            try:
                threadlogger.info("Thread starting: "+self.name)
                run_old(*args, **kw)
                threadlogger.info("Thread stopping: "+self.name)

            except Exception as e:
                threadlogger.exception("Thread stopping due to exception: "+self.name)
                raise e
        #Rename thread so debugging works
        try:
            if self._target:
                run_with_except_hook.__name__ = self._target.__name__
                run_with_except_hook.__module__ =self._target.__module__
        except:
            try:
                run_with_except_hook.__name__ = "run"
            except:
                pass
        self.run = run_with_except_hook
    threading.Thread.__init__ = init

