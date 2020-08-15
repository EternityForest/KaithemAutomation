#Copyright Daniel Dunn 2013
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

#This file manages a work queue that feeds a threadpool
#Tasks will be performed on a best effort basis and errors will be caught and ignored.

from scullery  import workers

import traceback
import cherrypy

def workersErrorHandler(f):
    #If we can, try to send the exception back whence it came
    try:
        from . import newevt
        if f[0].__module__ in newevt.eventsByModuleName:
            newevt.eventsByModuleName[f[0].__module__]._handle_exception()
    except:
        print(traceback.format_exc())

workers.backgroundFunctionErrorHandlers=[workersErrorHandler]
backgroundFunctionErrorHandlers
#Get the relevant config
from . import config as cfg
from .config import config

qsize = cfg.config['task-queue-size']
count = cfg.config['worker-threads']
wait =  cfg.config['wait-for-workers']

#Start
workers.start(count,qsize,wait)

#Only now do we do the import, as we will actually have everything loaded
from scullery.workers import *

atexit.register(EXIT)
cherrypy.engine.subscribe("exit",EXIT)
