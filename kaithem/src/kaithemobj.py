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
import unitsofmeasure
import workers
import subprocess
import threading
import random
import sound
import messagebus
import util
import cherrypy

#This exception is what we raise rom within the page handler to serve a static file
class ServeFileInsteadOfRenderingPageException(Exception):
    pass


class Kaithem():
    @staticmethod
    class misc(object):
        def lorem():
            return ("""lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin vitae laoreet eros. Integer nunc nisl, ultrices et commodo sit amet, dapibus vitae sem. Nam vel odio metus, ac cursus nulla. Pellentesque scelerisque consequat massa, non mollis dolor commodo ultrices. Vivamus sit amet sapien non metus fringilla pretium ut vitae lorem. Donec eu purus nulla, quis venenatis ipsum. Proin rhoncus laoreet ullamcorper. Etiam fringilla ligula ut erat feugiat et pulvinar velit fringilla.""")
        @staticmethod    
        def do(f):
            workers.do(f)
        
        
    class time(object):

        @staticmethod
        def month():
            return(time.localtime().tm_mon)

        @staticmethod
        def day():
            return(time.localtime().tm_mday)

        @staticmethod
        def year():
            return(time.localtime().tm_year)

        @staticmethod
        def hour():
            return(time.localtime().tm_hour)

        @staticmethod
        def hour():
            return(time.localtime().tm_hour)

        @staticmethod
        def minute():
            return(time.localtime().tm_min)

        @staticmethod   
        def second():
            return(time.localtime().tm_sec)

        @staticmethod
        def dayofweek():
            return (unitsofmeasure.DayOfWeek())
    
    class sys(object):
        @staticmethod
        def shellex(cmd):
            return (subprocess.check_output(cmd,shell=True))

        @staticmethod
        def shellexbg(cmd):
            subprocess.Popen(cmd,shell=True)
            
        @staticmethod
        def lsdirs(path):
            return util.get_immediate_subdirectories(path)
            
        @staticmethod  
        def lsfiles(path):
            return util.get_files(path)
        
        @staticmethod
        def which(exe):
            return util.which(exe)
        
    
            
    class web(object):
        @staticmethod
        def unurl(s):
            return util.unurl(s)
        
        @staticmethod
        def url(s):
            return util.url(s)
        
        @staticmethod
        def goBack():
            raise cherrypy.HTTPRedirect(cherrypy.request.headers['Referer'])
        
        @staticmethod
        def serveFile(path, contenttype = "",name = None):
            "Skip the rendering of the current page and Serve a static file instead."
            if name == None:
                name = path
            e = ServeFileInsteadOfRenderingPageException()
            e.f_filepath = path
            e.f_MIME = contenttype
            e.f_name = name
            raise e
    
    class sound(object):

        @staticmethod
        def play(soundfile, soundhandle='PRIMARY'):
            sound.playSound(soundfile,soundhandle)

        @staticmethod 
        def stop(soundhandle='PRIMARY'):
            sound.stopSound(soundhandle)

        @staticmethod
        def stopAll():
            sound.stopAllSounds()
            
        @staticmethod
        def isPlaying(handle="PRIMARY"):
            return sound.isPlaying(handle)
        
        
    class message():
        @staticmethod
        def postMessage(topic,message):
            print(message)
            messagebus.postMessage(topic,message)

        @staticmethod   
        def subscribe(topic,callback ):
            messagebus.subscribe(topic,callback)
        
class obj():
    pass




kaithem = Kaithem()
kaithem.globals = obj() #this is just a place to stash stuff.


