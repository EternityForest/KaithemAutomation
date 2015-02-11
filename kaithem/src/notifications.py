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

notificationslog =   []

def makenotifier():
    if not 'LastSawMainPage' in cherrypy.response.cookie:
        t = float(cherrypy.request.cookie["LastSawMainPage"].value)
    else:
        t = float(cherrypy.response.cookie["LastSawMainPage"].value)
        
    b = countnew(t)
    if b[2]:
        c = 'warning'
    if b[3]:
        c = 'error'
    else:
         c = ""
         
    if b[0]:
        s = "<span class='%s'>(%d)</span>" %(c,b[0])
    else:
        s = ''
    return s


def countnew(since):
        normal = 0
        errors = 0
        warnings = 0
        total = 0
        x = list(notificationslog)
        x.reverse()
        for i in x:
            if not i[0] > since:
                break
            else:
                if 'warning' in i[1]:
                    warnings +=1
                elif 'error' in i[1]:
                    errors += 1
                else:
                    normal += 1
                total +=1
        return [total,normal,warnings,errors]
    
class WI():
    @cherrypy.expose
    def countnew(self,**kwargs):
        pages.require('/admin/mainpage.view')
        return json.dumps(countnew(float(kwargs['since'])))
    
    @cherrypy.expose
    def mostrecent(self,**kwargs):
        pages.require('/admin/mainpage.view')
        return json.dumps(notificationslog[-int(kwargs['count']):])

    
def subscriber(topic,message):
    global notificationslog
    notificationslog.append((time.time(),topic,message))
    #Delete all but the most recent N notifications, where N is from the config file.
    notificationslog = notificationslog[-config['notifications-to-keep']:] 
    
messagebus.subscribe('/system/notifications/',subscriber)

def printer(t,m):
        print("\n"+ strftime() + ":\n" +"On Topic: "+t+"\n"+ m+"\n")

for i in config['print-topics']:
    messagebus.subscribe(i,printer)
