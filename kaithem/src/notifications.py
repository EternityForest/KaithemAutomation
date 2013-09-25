#Copyright Daniel Black 2013
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

import time,json
import cherrypy
from . import messagebus,pages
from .unitsofmeasure import strftime
from .config import config

keep_notifications = config['notifications-to-keep']
notificationslog =   []

class WI():
    @cherrypy.expose
    def countnew(self,**kwargs):
        pages.require('/admin/mainpage.view')
        normal = 0
        errors = 0
        warnings = 0
        total = 0
        x = list(notificationslog)
        x.reverse()
        for i in x:
            if not i[0] > float(kwargs['since']):
                break
            else:
                if 'warning' in i[1]:
                    warnings +=1
                elif 'error' in i[1]:
                    errors += 1
                else:
                    normal += 1
                total +=1
        return json.dumps([total,normal,warnings,errors])
    
def subscriber(topic,message):
    global notificationslog
    notificationslog.append((time.time(),topic,message))
    #Delete all but the most recent N notifications, where N is from the config file.
    notificationslog = notificationslog[-keep_notifications:] 
    
messagebus.subscribe('/system/notifications/',subscriber)

def printer(t,m):
        print("\n"+ strftime() + ":\n" +"On Topic: "+t+"\n"+ m+"\n")

for i in config['print-topics']:
    messagebus.subscribe(i,printer)
