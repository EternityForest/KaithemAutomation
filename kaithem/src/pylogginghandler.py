#Copyright Daniel Dunn 2016
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
import logging

from . import messagebus
logging.getLogger().setLevel(30)
class MessageBusHandler(logging.Handler):
    def emit(self,r):
        messagebus.postMessage("system/pylogging/"+r.levelname, self.format(r))
logging.getLogger().addHandler(MessageBusHandler())
