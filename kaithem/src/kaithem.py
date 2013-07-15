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

#This is the global general purpose utility thing
import time
import modules
import weekday
import workers
import subprocess
import threading
import random
import sound
import messagebus

class Kaithem():
    class misc(object):
        def lorem():
            return ("""lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin vitae laoreet eros. Integer nunc nisl, ultrices et commodo sit amet, dapibus vitae sem. Nam vel odio metus, ac cursus nulla. Pellentesque scelerisque consequat massa, non mollis dolor commodo ultrices. Vivamus sit amet sapien non metus fringilla pretium ut vitae lorem. Donec eu purus nulla, quis venenatis ipsum. Proin rhoncus laoreet ullamcorper. Etiam fringilla ligula ut erat feugiat et pulvinar velit fringilla.""")
        
        def do(f):
            workers.do(f)
        
        
    class time(object):
        def month():
            return(time.localtime().tm_mon)
            
        def day():
            return(time.localtime().tm_mday)
            
        def year():
            return(time.localtime().tm_year)
            
        def hour():
            return(time.localtime().tm_hour)
            
        def hour():
            return(time.localtime().tm_hour)
    
        def minute():
            return(time.localtime().tm_min)
            
        def second():
            return(time.localtime().tm_sec)

        def dayofweek():
            return (weekday.DayOfWeek())
    
    class sys(object):
        def shellex(cmd):
            return (subprocess.check_output(cmd,shell=True))
        
        def shellexbg(cmd):
            subprocess.Popen(cmd,shell=True)
            
    class Web(object):
        def urlForPage(module,page):
            return "/pages/page/"+url(i)+'/page/'+url(j)
    
    class sound(object):
        def playSound(soundfile, soundhandle='PRIMARY'):
            sound.playSound(soundfile,soundhandle)
            
        def stopSound(handle ):
            sound.stopSound(handle)
        
        def stopAllSounds():
            sound.stopAllSounds()
        
        
    class message(object):
        def postMessage(topic,message):
            messagebus.postMessage(topic,message)
            
        def subscribe(topic,callback ):
            messagebus.subscribe(topic,callback)
        
        
    
    

class obj():
    pass




kaithem = Kaithem()
kaithem.globals = obj() #this is just a place to stash stuff.


