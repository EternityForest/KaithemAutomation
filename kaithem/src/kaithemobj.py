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

"""This is the global general purpose utility thing that is accesable from almost anywhere in user code."""

import time,random,subprocess,threading,random,gzip,json,yaml,os,ntplib


import cherrypy
from . import unitsofmeasure,workers,sound,messagebus,util,mail,widgets,registry,directories,pages,config
from . import astrallibwrapper as sky

#This exception is what we raise from within the page handler to serve a static file
class ServeFileInsteadOfRenderingPageException(Exception):
    pass


class Kaithem():
    class misc(object):
        @staticmethod
        def lorem():
            return(random.choice(sentences))
            #return ("""lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin vitae laoreet eros. Integer nunc nisl, ultrices et commodo sit amet, dapibus vitae sem. Nam vel odio metus, ac cursus nulla. Pellentesque scelerisque consequat massa, non mollis dolor commodo ultrices. Vivamus sit amet sapien non metus fringilla pretium ut vitae lorem. Donec eu purus nulla, quis venenatis ipsum. Proin rhoncus laoreet ullamcorper. Etiam fringilla ligula ut erat feugiat et pulvinar velit fringilla.""")
      
        @staticmethod    
        def do(f):
            workers.do(f)
            
        @staticmethod    
        def uptime():
            return time.time()-systasks.systemStarted
        
        @staticmethod
        def errors(f):
            try:
                f()
            except Exception as e:
                return e
            return None
            
        
    class time(object):
        @staticmethod
        def strftime(*args):
            return unitsofmeasure.strftime(*args)
        
        @staticmethod
        def time():
            return time.time()

        @staticmethod
        def month():
            return(unitsofmeasure.Month())

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
        def isdst(self):
            #It returns 1 or 0, cast to bool because that's just weird.
            return(bool(time.localtime().tm_isdst))
                   
        @staticmethod
        def dayofweek():
            return (unitsofmeasure.DayOfWeek())
        
        @staticmethod
        def isDark(lat=None,lon=None):
            return (sky.isDark(lat,lon))
        
        @staticmethod
        def isRahu(lat=None,lon=None):
            if lat == None:
                if lon == None:
                    lat = registry.get("system/location/lat",None)
                    lon = registry.get("system/location/lon",None)
                if lat == None or lon ==None:
                    raise RuntimeError("No server location set, fix this in system settings")
                
            return (sky.isRahu(lat,lon))
        
        @staticmethod
        def isDay(lat=None,lon=None):
            if lat == None:
                if lon == None:
                    lat = registry.get("system/location/lat",None)
                    lon = registry.get("system/location/lon",None)
                if lat == None or lon ==None:
                    raise RuntimeError("No server location set, fix this in system settings")
            return (sky.isDay(lat,lon))
        
        @staticmethod
        def isNight(lat=None,lon=None):
            if lat == None:
                if lon == None:
                    lat = registry.get("system/location/lat",None)
                    lon = registry.get("system/location/lon",None)
                if lat == None or lon ==None:
                    raise RuntimeError("No server location set, fix this in system settings")
            return (sky.isNight(lat,lon))
        
        @staticmethod
        def isLight(lat=None,lon=None):
            if lat == None:
                if lon == None:
                    lat = registry.get("system/location/lat",None)
                    lon = registry.get("system/location/lon",None)
                if lat == None or lon ==None:
                    raise RuntimeError("No server location set, fix this in system settings")
            return (sky.isLight(lat,lon))
        
        @staticmethod
        def isDark(lat=None,lon=None):
            if lat == None:
                if lon == None:
                    lat = registry.get("system/location/lat",None)
                    lon = registry.get("system/location/lon",None)
                if lat == None or lon ==None:
                    raise RuntimeError("No server location set, fix this in system settings")
            return (sky.isDark(lat,lon))
        
        @staticmethod
        def moonPhase():
            return sky.moon()
        
        @staticmethod
        def accuracy():
            return util.timeaccuracy()
                
        
    
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
        @staticmethod
        def sensors():
            try:
                if util.which('sensors'):
                     return (subprocess.check_output('sensors').decode('utf8'))
                else:
                     return('"sensors" command failed(lm_sensors not available)')
            except:
                return('sensors call failed')
    
    class registry(object):
        @staticmethod
        def set(key,value):
            registry.set(key,value)
            
        @staticmethod
        def get(*args,**kwargs):
            return registry.get(*args,**kwargs)
        
    
    class mail(object):
        @staticmethod
        def send(recipient,subject,message):
            mail.raw_send(message,recipient,subject)
            
        @staticmethod
        def listSend(list,subject,message):
            mail.rawlistsend(subject,message,list)
            
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
            #Give it some text for when someone decides to call it from the wrong place
            e = ServeFileInsteadOfRenderingPageException("If you see this exception, it means someone tried to serve a file from somewhere that was not a page.")
            e.f_filepath = path
            e.f_MIME = contenttype
            e.f_name = name
            raise e
        
        @staticmethod
        def user():
            x =pages.getAcessingUser()
            if x:
                return x
            else:
                return ''
            
        @staticmethod
        def hasPermission(permission):
            return pages.canUserDoThis(permission)
        
    
    class sound(object):

        @staticmethod
        def play(*args,**kwargs):
            sound.playSound(*args,**kwargs)

        @staticmethod 
        def stop(*args,**kwargs):
            sound.stopSound(*args,**kwargs)
            
        @staticmethod 
        def pause(*args,**kwargs):
            sound.pause(*args,**kwargs)
            
        @staticmethod 
        def resume(*args,**kwargs):
            sound.resume(*args,**kwargs)

        @staticmethod
        def stopAll():
            sound.stopAllSounds()
            
        @staticmethod
        def isPlaying(*args,**kwargs):
            return sound.isPlaying(*args,**kwargs)
        
        @staticmethod
        def position(*args,**kwargs):
            return sound.position(*args,**kwargs)
        
        @staticmethod
        def setvol(*args,**kwargs):
            return sound.setvol(*args,**kwargs)
        
        
    class message():
        @staticmethod
        def post(topic,message):
            messagebus.postMessage(topic,message)

        @staticmethod   
        def subscribe(topic,callback ):
            messagebus.subscribe(topic,callback)
    
    class persist():
        @staticmethod
        def save(data,fn,mode="default"):
            if os.path.isdir(fn):
                raise RuntimeError("Filename is already present as a directory, refusing to overwrite directory")
            #create the directory if it does not exist.
            util.ensure_dir(os.path.split(fn)[0])
            if mode=="backup":
                if os.path.isfile(fn):
                    os.rename(fn, fn+'~')
            try:
                if fn.endswith(".gz"):
                    f = gzip.GzipFile(fn,mode='wb')
                    x = fn[:-3]
                elif fn.endswith(".bz2"):
                    f = bz2.BZ2File(fn,mode='wb')
                    x = fn[:-4]
                else:
                    f = open(fn,'wb')
                    x=fn
                
                if x.endswith(".json"):
                    f.write(json.dumps(data).encode('utf8'))
                elif x.endswith(".yaml"):
                    f.write(yaml.dump(data).encode('utf8'))
                elif x.endswith(".txt"):
                    f.write(str(data).encode())
                elif x.endswith(".bin"):
                    f.write(data)
                else:
                    raise ValueError('Unsupported File Extension')
            finally:
                f.close()
                
            if mode=="backup":
                if os.path.isfile(fn+'~'):
                    os.remove(fn+'~')

        @staticmethod
        def load(filename,autorecover = True):
            try:
                if filename.endswith(".gz"):
                    f = gzip.GzipFile(filename,mode='rb')
                    filename = filename[:-3]
                elif filename.endswith(".bz2"):
                    filename = filename[:-4]
                    f = bz2.BZ2File(filename,mode='rb')
                else:
                    f = open(filename,'rb')
                
                if filename.endswith(".json"):
                    r=json.loads(f.read().decode('utf8'))
                elif filename.endswith(".yaml"):
                    r=yaml.load(f.read().decode('utf8'))
                elif filename.endswith(".txt"):
                    r=f.read().decode('utf8')
                elif filename.endswith(".bin"):
                    r=f.read()
                else:
                    raise ValueError('Unsupported File Extension')
            except Exception as e:
                try:
                    f.close()
                except:
                    pass
                if not autorecover:
                    raise e
                else:
                    return kaithem.persist.load(filename +'~', False)
            try:
                f.close()
            except:
                pass
                
            return r
            
    class string():
        @staticmethod
        def usrstrftime(*a):
            return unitsofmeasure.strftime(*a)
         
        @staticmethod
        def SIFormat(number,d=2):
            return unitsofmeasure.siFormatNumber(number,d)
        
        @staticmethod
        def formatTimeInterval(s,places=2):
            return unitsofmeasure.formatTimeInterval(s,places)
        
    class events():
        pass
        #Stuff gets inserted here externally
        
        
class obj():
    pass

    
kaithem = Kaithem()
kaithem.widget = widgets
kaithem.globals = obj() #this is just a place to stash stuff.

if config.config['quotes-file'] == 'default':
    sentences= kaithem.persist.load(os.path.join(directories.datadir,"quotes.yaml"))
else:
    sentences= kaithem.persist.load(config.config['quotes-file'])
