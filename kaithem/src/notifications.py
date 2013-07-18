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

import messagebus,time
from config import config

keep_notifications = config['keep-notifications']
notificationslog =   []

def subscriber(topic,message):
    global notificationslog
    print(message)
    notificationslog.append((time.time(),topic,message))
    notificationslog = notificationslog[-keep_notifications:] 
    
messagebus.subscribe('/system/notifications',subscriber)