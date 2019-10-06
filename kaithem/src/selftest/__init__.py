#Copyright Daniel Dunn 2019
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

#This file runs a self test when python starts. Obviously we do
#Not want to clutter up the rraw

import threading,traceback,logging


def runtest():
    from .. import messagebus
    try:
        from . import eventsystem,statemachinestest,messagebustest,tagpointstest,testpersist

        eventsystem.eventSystemTest()
        statemachinestest.stateMachinesTest()
        messagebustest.test()
        tagpointstest.testTags()
        testpersist.test()
        logging.info("Self test was sucessful")
    except:
        messagebus.postMessage("/system/notifications/errors",    "Self Test Error\n"+traceback.format_exc(chain=True))
    finally:
       pass

t = threading.Thread(daemon=True,name="KaithemBootSelfTest", target=runtest)
t.start()