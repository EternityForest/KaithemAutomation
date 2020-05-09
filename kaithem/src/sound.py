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

import subprocess,os,math,time,sys,threading, collections,logging,re,uuid

from . import  util, scheduling,directories,workers, registry,widgets,messagebus, midi
from .config import config

import gc
from . import gstwrapper, jackmanager, jackmixer
log= logging.getLogger("system.sound")

MAX_PRELOADED = 8
gst_preloaded = {}
preloadlock = threading.Lock()


def volumeToDB(vol):
    if vol<0.001:
        return -100
    #Calculated usiung curve fitting, assuming that 0 is 0db,
    #0.5 is 10db below, etc.
    return -38.33333 + 77.80645*vol- 39.56989*vol**2

isStartDone = []
if jackmanager.settings.get('jackMode',None) in ("manage","use"):
    def f():
        try: 
            logging.debug("Initializing JACK")
            jackmanager.reloadSettings()
            jackmanager.startManaging()
        except:
            log.exception("Error managing JACK")
        try:
            isStartDone.append(True)
        except:
            pass
    workers.do(f)
    #Wait up to 3 seconds
    t = time.monotonic()
    while(time.monotonic()-t)< 3:
        if len(isStartDone):
            break
        time.sleep(0.1)
del isStartDone

jackAPIWidget = None

jackClientsFound = False

def tryCloseFds(p):
    if not p:
        return
    try:
        p.stdout.close()
    except:
        pass
    try:
        p.stderr.close()
    except:
        pass 
    try:
        p.stdin.close()
    except:
        pass
class SoundDeviceAlias():
    """An object meant to be looked up by alias, that tells you how to access the sound device it describes,
        using various drivers."""

    jackName = None
    alsaName = None
    pulseName = None

    def __init__(self, *args, **kwargs):
        return super().__init__(*args, **kwargs)
        self._jackName = None

    @property
    def jackName(self):
        if self._jackName:
            return self._jackName


    @jackName.setter
    def jackName(self,v):
        self._jackName = v

    @property
    def mplayerName(self):
        """The name as you would pass it to a -ao flag for mplayer"""
        #If there are any jack outputs, assume we are in jack mode and
        #Jack is preferred if we somehow have both
        if jackClientsFound:
            if self.jackName:
                return "jack:port="+ self.jackName.replace(":","=").replace(",",".")

        if self.alsaName == None:
            if self.jackName == None:
                return None
            return "jack:port="+ self.jackName.replace(":","=").replace(",",".")
        return "alsa:device="+ self.alsaName.replace(":","=").replace(",",".")

class PulseDeviceAlias(SoundDeviceAlias):
    @property
    def mplayerName(self):
        return "pulse"


aliasesLock = threading.Lock()

commonSoundAliases = {"PulseAudio:default": PulseDeviceAlias}
otherSoundAliases = {}
userSoundAliases = {}

def listSoundCardsByPersistentName():
    """
        Only works on linux or maybe mac

       List devices in a dict indexed by human-readable and persistant easy to memorize
       Identifiers. Output is tuples:
       (cardnamewithsubdev(Typical ASLA identifier),physicalDevice(persistent),devicenumber, subdevice)

       Indexed by a long name that contains the persistant locator, subdevice,
       prefixed by three words chosen based on a hash, to help you remember.

       An example of a generated name: 'reformerdatebookmaturity-HDMI2-0xef128000irq129:8'
    """
    with open("/proc/asound/cards") as f:
        c = f.read()

    #RE pattern produces cardnumber, cardname, locator
    c = re.findall(r"[\n\r]*\s*(\d)+\s*\[(\w+)\s*\]:\s*.*?[\n\r]+\s*.*? at (.*?)[\n\r]+",c)

    cards = {}
    #find physical cards
    for i in c:
        n = i[2].strip().replace(" ","").replace(",fullspeed","").replace("[","").replace("]","")
        cards[i[0]] = n

    x = subprocess.check_output(['aplay','-l']).decode("utf8")


    #Groups are cardnumber, cardname, subdevice, longname
    sd = re.findall(r"card (\d+): (\w*)\s\[.*?\], device (\d*): (.*?)\s+\[.*?]",x)

    d = {}

 
    for i in sd:
        #We generate a name that contains both the device path and subdevice
        generatedName = cards[i[0]]+":"+i[2]

        h = util.memorableHash(cards[i[0]]+":"+i[2])
        n = i[3].replace(" ","").replace("\n","")
        try:
            d[n+'-'+h+"-"+generatedName]  = ("hw:"+i[0]+","+i[2], cards[i[0]], (int(i[0]), int(i[2])))
        except KeyError:
            d[n+'-'+h+"-"+generatedName] = ("hw:"+i[0]+","+i[2], cards[i[0]], int(i[0]), int(i[2]))

    return d



lastRefreshedGeneratedAliases = 0

def refreshAutoGeneratedSoundAliases(*dummy):
    lastRefreshedGeneratedAliases = time.time()

    commonSoundAliasesl = {}

    global jackClientsFound

   
    #get the JACK devices    
    try:
        done ={}
        #We want the system outputs, which are inputs to us...
        for i in jackmanager.getPorts(is_audio=True, is_input=True):
            cn=i.name.split(":")[0]
            if cn in done:
                continue
            done[cn]=True
            p = SoundDeviceAlias()
            p.jackName = cn
            commonSoundAliasesl[cn] = p
   
    except ImportError:
       pass
    except:
        log.exception("Error getting jack devices")


    if not commonSoundAliasesl:
        jackClientsFound = False
        #Get the ALSA devices, but only if there are no JACK devices,
        #Because if there are jack devices why would we be using ALSA?

        #Technically there could be an unmanaged alsa device going, 
        #But that's an edge case, because the intended use is to let
        #kaithem handle jack
        try:
            x =  listSoundCardsByPersistentName()
            for i in x:
                p = SoundDeviceAlias()
                p.alsaName= x[i][0]
                commonSoundAliasesl[i] = p
        except:
            pass
    else:
        jackClientsFound = True


    global commonSoundAliases
    commonSoundAliases = commonSoundAliasesl

messagebus.subscribe("/system/jack/newport/", refreshAutoGeneratedSoundAliases)
messagebus.subscribe("/system/jack/delport/", refreshAutoGeneratedSoundAliases)

def getAvailableCards(forceRefresh=False):
   if forceRefresh or time.time()-lastRefreshedGeneratedAliases > 20:
        refreshAutoGeneratedSoundAliases()
   return commonSoundAliases


sound_paths = [""]

p = config['audio-paths']
for i in p:
    if i== '__default__':
        sound_paths.append(os.path.join(directories.datadir,"sounds"))
    else:
        sound_paths.append(i)

builtinSounds = os.listdir(os.path.join(directories.datadir,"sounds"))

def soundPath(fn,extrapaths=[]):
    "Get the full path of a sound file by searching"
    filename = util.search_paths(fn, extrapaths)
    if not filename:
        filename = util.search_paths(fn, sound_paths)

    #Search all module media folders
    if not filename:
        for i in os.listdir( os.path.join(directories.vardir,"modules",'data')):
            p =os.path.join(directories.vardir,"modules",'data',i,"__filedata__",'media')
            filename = util.search_paths(fn, [p])
            if filename:
                break

    #Raise an error if the file doesn't exist
    if not filename or not os.path.isfile(filename):
        raise ValueError("Specified audio file '"+fn+"' was not found")
    return filename


#This class provides some infrastructure to play sounds but if you use it directly it is a dummy.
class SoundWrapper(object):

    backendname = "Dummy Sound Driver(No real sound player found)"
    def __init__(self):
        #Prefetch cache for preloadng sound effects
        self.cache = collections.OrderedDict()
        self.runningSounds = {}

    def readySound(self, *args,**kwargs):
        pass
    
    @staticmethod
    def testAvailable():
        #Default to command based test
        return False

    #little known fact: Kaithem is actually a large collection of
    #mini garbage collectors and bookkeeping code...
    def deleteStoppedSounds(self):
        x = list(self.runningSounds.keys())
        for i in x:
            try:
                if not self.runningSounds[i].isPlaying():
                    self.runningSounds.pop(i)
            except KeyError:
                pass

    def stopAllSounds(self):
        x = list(self.runningSounds.keys())
        for i in x:
            try:
                self.runningSounds.pop(i)
            except KeyError:
                pass

    def getPosition(self,channel = "PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].position()
        except KeyError:
            return False

    def setVolume(self,channel = "PRIMARY"):
        pass

    def setEQ(self,channel="PRIMARY"):
        pass

    def playSound(self,filename,handle="PRIMARY",**kwargs):
        pass

    def stopSound(self, handle ="PRIMARY"):
        pass

    def isPlaying(self,handle="blah"):
        return False

    def pause(self, handle ="PRIMARY"):
        pass

    def resume(self,  handle ="PRIMARY"):
        pass
    
    def fadeTo(self, handle="PRIMARY"):
        self.playSound(self,handle)
    
    def preload(self, filename):
        pass

    def seek(self,position,channel = "PRIMARY"):
        try:
            return self.runningSounds[channel].seek(position)
        except KeyError:
            pass

        
class MadPlayWrapper(SoundWrapper):
    backendname = "MadPlay Sound Player"

    #What this does is it keeps a reference to the sound player process and
    #If the object is destroyed it destroys the process stopping the sound
    #It also abstracts checking if its playing or not.
    class MadPlaySoundContainer(object):
        def __init__(self,filename,**kwargs):
            f = open(os.devnull,"w")
            g = open(os.devnull,"w")
            cmd = ["madplay", filename]
            self.loopcounter = -1 if kwargs.get('loop',False) is True else kwargs.get('loop',False)-1            
            if self.loopcounter:
                    self.end = False
                    def loop_play_again():
                        self.process.poll()
                        if self.process.returncode ==None:
                            return True
                        if not self in backend.runningSounds.values():
                            return False
                        if not self.loopcounter:
                            return False
                        if self.end:
                            return
                        self.loopcounter -=1
                        try:
                            self.process.terminate()
                            tryCloseFds(self.process)
                        except:
                            pass
                        self.process = subprocess.Popen(cmd, stdout=f, stderr=g)
                        return True
                    self.loop_repeat_func = loop_play_again
                    scheduling.RepeatWhileEvent(loop_play_again, 0.05).register()
            self.process = subprocess.Popen(cmd, stdout=f, stderr=g)
            
        def __del__(self):
            try:
                self.process.terminate()
                tryCloseFds(self.process)
                del self.loop_repeat_func
            except:
                pass

        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None or bool(self.loopcounter)

    def playSound(self,filename,handle="PRIMARY",extraPaths=[],**kwargs):
        #Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()            
        fn = soundPath(filename,extraPaths)
   
        #Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.MadPlaySoundContainer(fn,**kwargs)

    def stopSound(self, handle ="PRIMARY"):
        #Delete the sound player reference object and its destructor will stop the sound
            if handle in self.runningSounds:
                #Instead of using a lock lets just catch the error is someone else got there first.
                try:
                    del self.runningSounds[handle]
                except KeyError:
                    pass
        
    def stopAllSounds(self):
        x = list(self.runningSounds.keys())
        for i in x:
            try:
                self.runningSounds[i].end = True
                self.runningSounds.pop(i)
            except KeyError:
                raise

class Mpg123Wrapper(SoundWrapper):
    backendname = "MPG123 Sound Player"

    #What this does is it keeps a reference to the sound player process and
    #If the object is destroyed it destroys the process stopping the sound
    #It also abstracts checking if its playing or not.
    class Mpg123SoundContainer(object):
        def __init__(self,filename,**kwargs):
            f = open(os.devnull,"w")
            g = open(os.devnull,"w")
            cmd = ["mpg123", filename]
            self.loopcounter = -1 if kwargs.get('loop') is True else  kwargs.get('loop')-1            
            if self.loopcounter:
                    self.end = False
                    def loop_play_again():
                        self.process.poll()
                        if self.process.returncode ==None:
                            return True
                        if not self in backend.runningSounds.values():
                            return False
                        if not self.loopcounter:
                            return False
                        if self.end:
                            return
                        self.loopcounter -=1
                        try:
                            self.process.terminate()
                        except:
                            pass
                        tryCloseFds(self.process)

                        self.process = subprocess.Popen(cmd, stdout=f, stderr=g)
                        return True
                    self.loop_repeat_func = loop_play_again
                    scheduling.RepeatWhileEvent(loop_play_again, 0.05).register()
            self.process = subprocess.Popen(cmd, stdout=f, stderr=g)
            
        def __del__(self):
            try:
                self.process.terminate()
                del self.loop_repeat_func
                tryCloseFds(self.process)
            except:
                pass

        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None or bool(self.loopcounter)

    def playSound(self,filename,handle="PRIMARY",extraPaths=[],**kwargs):
        #Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        
        fn = soundPath(filename,extraPaths)

        #Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.Mpg123SoundContainer(fn,**kwargs)

    def stopSound(self, handle ="PRIMARY"):
        #Delete the sound player reference object and its destructor will stop the sound
            if handle in self.runningSounds:
                #Instead of using a lock lets just catch the error is someone else got there first.
                try:
                    del self.runningSounds[handle]
                except KeyError:
                    pass
        
    def stopAllSounds(self):
        x = list(self.runningSounds.keys())
        for i in x:
            try:
                self.runningSounds[i].end = True
                self.runningSounds.pop(i)
            except KeyError:
                raise

class SOXWrapper(SoundWrapper):
    backendname = "SOund eXchange"

    #What this does is it keeps a reference to the sound player process and
    #If the object is destroyed it destroys the process stopping the sound
    #It also abstracts checking if its playing or not.
    class SOXSoundContainer(object):
        def __init__(self,filename,vol,start,end,loop=1):
            f = open(os.devnull,"w")
            g = open(os.devnull,"w")
            self.started = time.time()
            self.process = subprocess.Popen(["play",filename,"vol",str(vol),"trim",str(start),str(end)], stdout = f, stderr = g)
            self.loopcounter = -1 if loop is True else loop-1            
            if self.loopcounter:
                    self.end = False
                    def loop_play_again():
                        self.process.poll()
                        if self.process.returncode ==None:
                            return True
                        if not self in backend.runningSounds.values():
                            return False
                        if not self.loopcounter:
                            return False
                        if self.end:
                            return
                        self.loopcounter -=1
                        try:
                            self.process.terminate()
                        except:
                            pass
                        tryCloseFds(self.process)
                        self.process = subprocess.Popen(["play",filename,"vol",str(vol),"trim",str(start),str(end)], stdout = f, stderr = g)
                        return True
                    self.loop_repeat_func = loop_play_again
                    scheduling.RepeatWhileEvent(loop_play_again, 0.02).register()
            else:
                self.process = subprocess.Popen(["play",filename,"vol",str(vol),"trim",str(start),str(end)], stdout = f, stderr = g)

      
          
        def __del__(self):
            try:
                self.process.terminate()
                del self.loop_repeat_func
                tryCloseFds(self.process)
            except:
                pass

        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None or bool(self.loopcounter)

        def position(self):
            return self.started
        
    def stopAllSounds(self):
        x = list(self.runningSounds.keys())
        for i in x:
            try:
                self.runningSounds[i].end = True
                self.runningSounds.pop(i)
            except KeyError:
                raise

    def playSound(self,filename,handle="PRIMARY",extraPaths=[],**kwargs):

        if 'volume' in kwargs:
            #odd way of throwing errors on non-numbers
            v  = float(kwargs['volume'])
        else:
            v =1;

        if 'start' in kwargs:
            #odd way of throwing errors on non-numbers
            start  = float(kwargs['start'])
        else:
            start =0

        if 'end' in kwargs:
            #odd way of throwing errors on non-numbers
            end  = float(kwargs['end'])
        else:
            end ="-0"

    
        #Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        #Raise an error if the file doesn't exist
        fn = soundPath(filename,extraPaths)

        #Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.SOXSoundContainer(fn, v,start,end,loop=kwargs.get('loop',1))

    def stopSound(self, handle ="PRIMARY"):
        #Delete the sound player reference object and its destructor will stop the sound
            if handle in self.runningSounds:
                #Instead of using a lock lets just catch the error is someone else got there first.
                try:
                    self.runningSounds[i].end = True
                    del self.runningSounds[handle]
                except KeyError:
                    pass

    def isPlaying(self,channel = "PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].isPlaying()
        except KeyError:
            return False


class MPlayerWrapper(SoundWrapper):
    backendname = "MPlayer"

    #What this does is it keeps a reference to the sound player process and
    #If the object is destroyed it destroys the process stopping the sound
    #It also abstracts checking if its playing or not.
    class MPlayerSoundContainer(object):
        def __init__(self,filename,vol,start,end,extras,**kw):
            self.lock = threading.RLock()
            f = open(os.devnull,"w")
            g = open(os.devnull,"w")
            self.nocallback = False
            self.paused = False
            self.volume = vol
            cmd = ["mplayer" , "-nolirc", "-slave" , "-quiet", "-softvol" ,"-ss", str(start)]

           
            if end:
                cmd.extend(["-endpos",str(end)])

            if "output" in kw and kw['output']:
                x = kw['output']

                #Try to resolve it as an identifier.
                getAvailableCards()
                if x in commonSoundAliases:
                    x = commonSoundAliases[x].mplayerName
                
                cmd.extend(["-ao",x])
            else:
                if jackClientsFound:
                    if 'system' in commonSoundAliases:
                        x = commonSoundAliases['system'].mplayerName
                        cmd.extend(["-ao",x])


            if "video_output" in kw:
                cmd.extend(["-vo",kw['output']])

            if "fs" in kw and kw['fs']:
                cmd.extend(["-fs"])

            if "novideo" in kw and kw['novideo']:
                cmd.extend(["-novideo"])
            
            if "pan" in kw and kw['pan']:
                pan = ",pan="+":".join(str(i) for i in kw["pan"])
            else:
                pan = ""

            if 'eq' in extras:
                if extras['eq'] == 'party':
                    cmd.extend(['-af','equalizer=0:1.5:2:-7:-10:-5:-10:-10:1:1,volume='+str((10*math.log10(vol or 10**-30)+5))+pan
                    
                    ])
                else:
                    cmd.extend(['-af','equalizer=' +":".join(extras['eq'])+",volume="+str((10*math.log10(vol or 10**-30)+5))+pan
                    ])
            else:
                cmd.extend(["-af", "volume="+str(10*math.log10(vol or 10**-30))+pan])
            
            if 'loop' in kw:
                cmd.extend(["-loop", str(0 if kw['loop'] is True else int(kw['loop']))])

            self.started = time.time()
            cmd.append(filename)
            self.process = subprocess.Popen(cmd,stdin=subprocess.PIPE, stdout = f, stderr = g)
            #We don't want to slow things down by waiting, but we can at least catch some of the errors that happen fast.
            self.process.poll()
            if not self.process.returncode in (None,0):
                raise RuntimeError("Mplayer nonzero error code: "+str(self.process.returncode))
                
            x= kw.get('callback',False)
            if x:
                def f():
                    if self.isPlaying():
                        return True
                    else:
                        if not self.nocallback:
                            x()
                        return False
                self.callback = f
                scheduling.RepeatWhileEvent(f,0.1).register()
                        
                    

        def __del__(self):
            try:
                self.process.terminate()
                tryCloseFds(self.process)
            except:
                pass
        def stop(self):
            try:
                self.process.terminate()
                tryCloseFds(self.process)

            except:
                pass

        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None

        def position(self):
            return time.time() - self.started

        def wait(self):
            #Block until sound is finished playing.
            self.process.wait()


        def seek(self,position):
            with self.lock:
                if self.isPlaying():
                    try:
                        if sys.version_info < (3,0):
                            self.process.stdin.write(bytes("pausing_keep seek "+str(position)+" 2\n"))
                        else:
                            self.process.stdin.write(bytes("pausing_keep seek "+str(position)+" 2\n",'utf8'))
                        self.process.stdin.flush()
                        self.started = time.time()-position
                    except:
                        pass


        def setVol(self,volume):
            self.volume = volume
            with self.lock:
                if self.isPlaying():
                    try:
                        if sys.version_info < (3,0):
                            self.process.stdin.write(bytes("pausing_keep volume "+str(volume*100)+" 1\n"))
                        else:
                            self.process.stdin.write(bytes("pausing_keep volume "+str(volume*100)+" 1\n",'utf8'))
                        self.process.stdin.flush()
                    except:
                        pass

        def setEQ(self,eq):
            with self.lock:
                if self.isPlaying():
                    try:
                        if sys.version_info < (3,0):
                            self.process.stdin.write(bytes("pausing_keep af_cmdline equalizer "+":".join([str(i) for i in eq]) +"\n"))
                        else:
                            self.process.stdin.write(bytes("pausing_keep af_cmdline equalizer "+":".join([str(i) for i in eq]) +"\n", "utf8"))
                        self.process.stdin.flush()
                    except Exception as e:
                        raise e

        def pause(self):
            with self.lock:
                try:
                    if not self.paused:
                        self.process.stdin.write(b"pause \n")
                        self.process.stdin.flush()
                        self.paused= True
                except:
                    pass

        def resume(self):
            with self.lock:
                try:
                    if self.paused:
                        self.process.stdin.write(b"pause \n")
                        self.process.stdin.flush()
                        self.paused = False
                except:
                    pass

    def playSound(self,filename,handle="PRIMARY",extraPaths=[],**kwargs):
        if 'volume' in kwargs:
            #odd way of throwing errors on non-numbers
            v  = float(kwargs['volume'])
        else:
            v =1;

        if 'start' in kwargs:
            #odd way of throwing errors on non-numbers
            start  = float(kwargs['start'])
        else:
            start =0

        if 'end' in kwargs:
            #odd way of throwing errors on non-numbers
            end  = float(kwargs['end'])
        else:
            end = None

        if 'output' in kwargs:
            e = {"output":kwargs['output']}
        else:
            e = {}

        if 'fs' in kwargs:
            e['fs'] = kwargs['fs']
            
        if 'loop' in kwargs:
            e['loop'] = kwargs['loop']
        if 'pan' in kwargs:
            e['pan'] = kwargs['pan']
            
        if 'novideo' in kwargs:
            e['novideo'] = kwargs['novideo']

        if 'eq' in kwargs:
            extras={'eq':kwargs['eq']}
        else:
            extras={}
        #Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        #Raise an error if the file doesn't exist
        fn = soundPath(filename,extraPaths)
        #Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.MPlayerSoundContainer(fn,v,start,end,extras,**e)

    def stopSound(self, handle ="PRIMARY"):
        #Delete the sound player reference object and its destructor will stop the sound
            if handle in self.runningSounds:
                #Instead of using a lock lets just catch the error is someone else got there first.
                try:
                    x= self.runningSounds[handle]
                    del self.runningSounds[handle]
                    x.nocallback = True
                    del x
                except KeyError:
                    pass

    def isPlaying(self,channel = "PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].isPlaying()
        except KeyError:
            return False

    def wait(self,channel = "PRIMARY"):
        "Block until any sound playing on a channel is finished"
        try:
            self.runningSounds[channel].wait()
        except KeyError:
            return False

    def setVolume(self,vol,channel = "PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].setVol(vol)
        except KeyError:
            pass

    def seek(self,position,channel = "PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].seek(position)
        except KeyError:
            pass

    def setEQ(self,eq,channel = "PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].setEQ(eq)
        except KeyError:
            pass

    def pause(self,channel = "PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].pause()
        except KeyError:
            pass

    def resume(self,channel = "PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].resume()
        except KeyError:
            pass

    def fadeTo(self,file,length=1.0, block=False, handle="PRIMARY",**kwargs):
        try:
            x = self.runningSounds[handle]
        except KeyError:
            x = None
        if x and not length:
            x.stop()
        
        k = kwargs.copy()
        k.pop('volume',0)

        #Allow fading to silence
        if file:
            self.playSound(file,handle=handle,volume=0,**kwargs)

        if not x:
            return
        if not length:
            return

        try:
            v = x.volume
        except:
            return

        def f():
            t = time.monotonic()
           

            while x and time.monotonic()-t<length:
                x.setVol(max(0,v*  (1-(time.monotonic()-t)/length)))
                self.setVolume(min(1,kwargs.get('volume',1)*((time.monotonic()-t)/length)),handle)
                time.sleep(1/48.0)
            if x:
                x.stop()
        if block:
            f()
        else:
            workers.do(f)



from . import gstwrapper
class GSTAudioFilePlayer(gstwrapper.Pipeline):
    def __init__(self, file, volume=1, output="@auto",onBeat=None, _prevPlayerObject=None,systemTime=False):

        if not output:
            output="@auto"
        self.filename = file

        self.finalGain = volume
        
        self.lastFileSize = os.stat(file).st_size

        if self.lastFileSize==0:
            for i in range(10):
                self.lastFileSize = os.stat(file).st_size
                if self.lastFileSize>0:
                    break
                time.sleep(1)

        if self.lastFileSize==0:
            raise RuntimeError("File was still zero bytes after 10 seconds")
        
        self.lastPosition = 0
       
        self.lastFileSizeChange = 0

        gstwrapper.Pipeline.__init__(self,str(uuid.uuid4()),systemTime=False,realtime=70)
        self.aw =None
        self.ended = False

        self.lastBeat = 0
        self.peakDetect = 0
        self.detectedBeatInterval = 1/60
        self.beat = onBeat
        
        self._prevPlayerObject = _prevPlayerObject


        self.src = self.addElement('filesrc',location=file)
        self.queue = self.addElement("queue")

        decodeBin = self.addElement('decodebin',low_percent=15)
        #self.addElement('audiotestsrc')
        isVideo=False

        for i in (".mkv",".flv",".wmv",".mp4",".avi"):
            if file.endswith(i):
                isVideo=True
        if isVideo:
            decodeBin.set_property("low-percent",80)
            q=self.addElement('queue', connectToOutput=decodeBin, connectWhenAvailable="audio")
        
            self.addElement('audiorate')
            self.addElement('audioconvert')

        else:
            self.addElement('audioconvert',connectToOutput=decodeBin,connectWhenAvailable="audio")
    
        self.addElement('audioresample')


        
        if onBeat:
            self.addLevelDetector()

        self.fader = self.addElement('volume', volume=volume)

        if output=="@auto":
            self.sink = self.addElement('autoaudiosink')
        elif output.startswith("@pulse"):
            s = output.split(":")
            if len(s)>1:
                s=s[1]
            else:
                s=s[0]
            self.sink = self.addElement('pulsesink')

        elif output.startswith("@alsa:"):
            self.addElement('alsasink',device= output[6:])

        #No jack clients at all means it probably isn't running
        elif not jackClientsFound:
            if "hw:" in output or  "usb:" in output: 
                self.addElement('alsasink',device= output)
            else:
                raise ValueError("Bad output: "+output)
        
        #Default to just using jack
        else:
            cname="player"+str(time.monotonic())+"_out"

            self.sink = self.addElement('jackaudiosink', buffer_time=16000 if not isVideo else 80000, 
            latency_time=8000 if not isVideo else 40000,slave_method=0,port_pattern="jhjkhhhfdrhtecytey",
            connect=0,client_name=cname,sync=False)

            #Default to the system outout if nothing selected, even if jack in use.
            if not output:
                output='system'
            self.aw = jackmanager.Airwire(cname, output)
            self.aw.connect()
        #Get ready!
        self.pause()


    def loopCallback(self):
        size= os.stat(self.filename).st_size
        if not size==self.lastFileSize:
            self.lastFileSizeChange = time.monotonic()
            self.lastFileSize=size

        self.lastPosition = self.getPosition()

    def onEOS(self):
        #If the file has changed size recently, this might not be a real EOS,
        #Just a buffer underrun. Lets just try again 
        if self.lastFileSizeChange> (time.monotonic()-3):
            self.pause()
            self.seek(self.lastPosition-0.1)
            time.sleep(3)
            self.play()
        else:
            gstwrapper.Pipeline.onEOS(self)
    
    def setVol(self,v):
        #We are going to do a perceptual gain algorithm here
        db = volumeToDB(v)

        #Now convert to a raw gain
        vGain = 10**(db/20)

        self.setFader(vGain if not vGain<-0.01 else 0)


    def setFader(self,level):
        with self.lock:
            try:
                if self.fader:
                    self.fader.set_property('volume', level)
            except ReferenceError:
                pass
    
    def stop(self):

        #Prevent any ugly noise that GSTreamer might make when stopped at
        #The wrong time
        try:
            if self.aw:
                self.aw.disconnect()
        except:
            logging.exception("Err disconnecting airwire")

        gstwrapper.Pipeline.stop(self)

        if self._prevPlayerObject:
            p = self._prevPlayerObject()
            if p:
                p.stop()

    def resume(self):
        self.start()
  
    def onStreamFinished(self):
        self.ended=True

    def isPlaying(self):
        return self.running


    def addLevelDetector(self):
        self.addElement("level", post_messages=True, peak_ttl=300*1000*1000,peak_falloff=60)

    def on_message(self, bus, message,userdata):
        s = message.get_structure()
        if not s:
            return True
        if  s.get_name() == 'level':
            if self.board:
                rms = sum([i for i in s['rms']])/len(s['rms'])
                self.peakDetect = max(self.peakDetect, rms)
                timeSinceBeat = time.monotonic()-self.lastBeat

                threshold =self.peakDetect-(1+ (3*max(1,timeSinceBeat/self.detectedBeatInterval)))
                if timeSinceBeat> self.detectedBeatInterval/8:
                    if rms>threshold:
                        self.beat()
                        self.detectedBeatInterval = (self.detectedBeatInterval*3 + timeSinceBeat)/4
                        self.peakDetect*=0.996
        return True


class GStreamerBackend(SoundWrapper):
    backendname = "Gstreamer"

    @staticmethod
    def testAvailable():
       
        return not gstwrapper.testGst()==None
    #What this does is it keeps a reference to the sound player process and
    #If the object is destroyed it destroys the process stopping the sound
    #It also abstracts checking if its playing or not.
    class GStreamerContainer(object):
        def __init__(self,filename,output="@auto",**kwargs):

            with preloadlock:
                if (filename,output) in gst_preloaded:
                    self.pl = gst_preloaded[filename,output][0]
                    del gst_preloaded[filename,output]
                else:
                    self.pl = GSTAudioFilePlayer(filename, kwargs.get('volume',1),output=output)


            self.pl.setVol(kwargs.get('volume',1))
            if not  kwargs.get('pause',0):
                self.pl.start()
            else:
                self.pl.pause()

            self.volume= kwargs.get('volume',1)
            
        def __del__(self):
            try:
                self.pl.stop()
            except:
                pass

        def isPlaying(self):
            return not self.pl.ended
        
        def setVol(self,v,final=True):
            self.volume=v
            if final:
                self.finalGain = v
            self.pl.setVol(v)

        def pause(self):
            self.pl.pause()
        
        def resume(self):
            self.pl.resume()

        def stop(self):
            self.pl.stop()
        def seek(self):
            self.pl.seek()
    
        def position():
            try:
                return self.pl.getPosition()
            except:
                return 0

    def preload(self,filename,output="@auto"):
        if not os.path.exists(filename):
            return

        #Has to be in a background thread to actually make sense

        def f():
            with preloadlock:
                if (filename,output) in gst_preloaded:
                    return
                t=time.monotonic()
                torm = {}

                #Clean up any unused preload requests
                for i in gst_preloaded:
                    if t-gst_preloaded[i][1]>60:
                        torm[i]=1

                for i in gst_preloaded:
                    if not gst_preloaded[i][0].running:
                        torm[i]=1

                #Out of space, but nothing marked for deletion, now we shorten
                #The window to find something deletable
                if len(gst_preloaded)>MAX_PRELOADED and not torm:
                    for i in gst_preloaded:
                        if t-gst_preloaded[i][1]>5:
                            torm[i]=1
                            break
                        
                #Actually remove from list
                for i in torm:
                    try:
                        gst_preloaded[i][0].stop()
                        del gst_preloaded[i]
                    except:
                        logging.exception("Error cleaning up preloaded sound")
                    

                #We still might not have anything to delete. Assume in that case
                #It's nonsense churn spamming up everything, and that we can safely
                #just ignore the preload and load it on demand
                if len(gst_preloaded)<MAX_PRELOADED:
                    try:
                        if not os.path.exists(filename):
                            return
                        p =GSTAudioFilePlayer(filename,output=output)
                        gst_preloaded[(filename,output)] = (p,time.monotonic())
                    except:
                        logging.exception("Error preloading sound")
        workers.do(f)
    
    def playSound(self,filename,handle="PRIMARY",extraPaths=[],_prevPlayerObject=None, finalGain=None,**kwargs):
        #Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()            
        fn = soundPath(filename,extraPaths)

        if 'volume' in kwargs:
            #odd way of throwing errors on non-numbers
            v  = float(kwargs['volume'])
        else:
            v =1;
        if finalGain is None:
            finalGain=v

        
        if 'start' in kwargs:
            #odd way of throwing errors on non-numbers
            start  = float(kwargs['start'])
        else:
            start =0

        if 'end' in kwargs:
            #odd way of throwing errors on non-numbers
            end  = float(kwargs['end'])
        else:
            end = None

        if "output" in kwargs and kwargs['output']:
                x = kwargs['output']

                #Try to resolve it as an identifier.
                getAvailableCards()
                if x in commonSoundAliases:
                    if jackClientsFound:
                        x = commonSoundAliases[x].jackName
                    else:
                        x = "@alsa:"+commonSoundAliases[x].alsaName
                output=x
        else:
            output = "@auto"
        #Play the sound with a background process and keep a reference to it
        pl = self.GStreamerContainer(fn,volume=v,output=output,_prevPlayerObject=_prevPlayerObject)
        pl.finalGain = finalGain
        self.runningSounds[handle] = pl
    
    def isPlaying(self,channel = "PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].isPlaying()
        except KeyError:
            return False

    def stopSound(self, handle ="PRIMARY"):
        #Delete the sound player reference object and its destructor will stop the sound
            if handle in self.runningSounds:
                #Instead of using a lock lets just catch the error is someone else got there first.
                try:
                    del self.runningSounds[handle]
                except KeyError:
                    pass
        
    def stopAllSounds(self):

        x = list(self.runningSounds.keys())
        for i in x:
            try:
                self.runningSounds[i].end = True
                self.runningSounds.pop(i)
            except KeyError:
                raise
    def setVolume(self,vol,channel = "PRIMARY",final=True):
            "Return true if a sound is playing on channel"
            try:
                return self.runningSounds[channel].setVol(vol,final)
            except (KeyError,ReferenceError):
                pass
    
    def pause(self,channel = "PRIMARY" ):
        try:
            return self.runningSounds[channel].pause()
        except KeyError:
            pass

    def resume(self,channel = "PRIMARY" ):
        try:
            return self.runningSounds[channel].pause()
        except KeyError:
            pass
    
    def fadeTo(self,file,length=1.0, block=False, detach=True, handle="PRIMARY",**kwargs):
        try:
            x = self.runningSounds[handle]
            if detach:
                #Detach from that handle name
                del self.runningSounds[handle]
        except KeyError:
            x = None
        if x and not length:
            x.stop()
        
        k = kwargs.copy()

        if 'volume' in kwargs:
            del k['volume']

        #Allow fading to silence
        if file:
            #PrevplayerObject makes the new sound reference the old, so the old doesn't
            #get GCed and stop
            self.playSound(file,handle=handle, _prevPlayerObject=x, volume=0, finalGain=kwargs.get('volume',1),**k)
        def f():
            t = time.monotonic()
            try:
                v = x.volume
            except:
                v=0

            while time.monotonic()-t<length:
                ratio = ((time.monotonic()-t)/length)

                try:
                    targetVol=self.runningSounds[handle].finalGain
                except:
                    pass

                if x:
                    x.setVol(max(0,v* (1-ratio)))

                if file:
                    self.setVolume(min(1,targetVol*ratio),handle,final=False)
                time.sleep(1/48.0)
            
            try:
                targetVol=self.runningSounds[handle].finalGain
                self.setVolume(min(1,targetVol),handle)
            except Exception as e:
                print(e)

            if x:
                x.stop()

        if block:
            f()
        else:
            workers.do(f)
   
l = {'sox':SOXWrapper, 'mpg123':Mpg123Wrapper, "mplayer":MPlayerWrapper, "madplay":MadPlayWrapper, 'gstreamer':GStreamerBackend}


backend = SoundWrapper()
if util.which('pulseaudio'):
    pulseaudio=True
else:
    pulseaudio=False
    
    
for i in config['audio-backends']:
    try:
        if util.which(i) or l[i].testAvailable():
            backend = l[i]()
            break
    except:
            messagebus.postMessage("/system/notifications/errors","Failed to initialize audio backend "+i," may be able to use fallback")

def stopAllSounds():
    midi.allNotesOff()
    backend.stopAllSounds()


def oggSoundTest(output=None):
    t="test"+str(time.time())
    playSound("alert.ogg",output=output, handle=t)
    for i in range(100):
        if isPlaying(t):
            return
        time.sleep(1)
    raise RuntimeError("Sound did not report as playing within 100ms")

#Make fake module functions mapping to the bound methods.
playSound = backend.playSound
stopSound = backend.stopSound
isPlaying = backend.isPlaying
resolveSound = soundPath
pause = backend.pause
resume = backend.resume
setvol = backend.setVolume
setEQ = backend.setEQ
position = backend.getPosition
fadeTo = backend.fadeTo
readySound = backend.readySound
preload= backend.preload
