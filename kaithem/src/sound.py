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

import subprocess,os,math,time,sys,threading
from . import  util, scheduling,directories
from .config import config

sound_paths = [""]

p = config['audio-paths']
for i in p:
    if i== 'default':
        sound_paths.append(os.path.join(directories.datadir,"sounds"))
    else:
        sound_paths.append(i)

def soundPath(fn):
    fn = util.search_paths(filename, sound_paths)
        #Raise an error if the file doesn't exist
    if not fn or not os.path.isfile(fn):
        raise ValueError("Specified audio file'"+filename+"' was not found")
    return fn


#This class provides some infrastructure to play sounds but if you use it directly it is a dummy.
class SoundWrapper(object):

    runningSounds = {}
    backendname = "Dummy Sound Driver(No real sound player found)"
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
                del self.loop_repeat_func
            except:
                pass

        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None or bool(self.loopcounter)

    def playSound(self,filename,handle="PRIMARY",**kwargs):
        #Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        
        fn = util.search_paths(filename, sound_paths)
        #Raise an error if the file doesn't exist
        if not fn or not os.path.isfile(fn):
            raise ValueError("Specified audio file'"+filename+"' was not found")

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
                        self.process = subprocess.Popen(cmd, stdout=f, stderr=g)
                        return True
                    self.loop_repeat_func = loop_play_again
                    scheduling.RepeatWhileEvent(loop_play_again, 0.05).register()
            self.process = subprocess.Popen(cmd, stdout=f, stderr=g)
            
        def __del__(self):
            try:
                self.process.terminate()
                del self.loop_repeat_func
            except:
                pass

        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None or bool(self.loopcounter)

    def playSound(self,filename,handle="PRIMARY",**kwargs):
        #Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        
        fn = util.search_paths(filename, sound_paths)
        #Raise an error if the file doesn't exist
        if not fn or not os.path.isfile(fn):
            raise ValueError("Specified audio file'"+filename+"' was not found")

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
                    print(self.loopcounter)
                    self.end = False
                    def loop_play_again():
                        print(self.loopcounter)
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

    def playSound(self,filename,handle="PRIMARY",**kwargs):

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
        fn = util.search_paths(filename, sound_paths)
        #Raise an error if the file doesn't exist
        if not fn or not os.path.isfile(fn):
            raise ValueError("Specified audio file'"+filename+"' was not found")

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
            cmd = ["mplayer" , "-slave" , "-quiet", "-softvol" ,"-ss", str(start)]

            if not 'eq' in extras:
                cmd.extend(["-af", "equalizer=0:0:0:0:0:0:0:0:0:0,volume="+str(10*math.log10(vol or 10**-30))])
            if end:
                cmd.extend(["-endpos",str(end)])

            if "output" in kw and pulseaudio:
                cmd.extend(["-ao",kw['output']])
                           

            if "video_output" in kw:
                cmd.extend(["-vo",kw['output']])

            if "fs" in kw and kw['fs']:
                cmd.extend(["-fs"])

            if "novideo" in kw and kw['novideo']:
                cmd.extend(["-novideo"])

            if 'eq' in extras:
                if extras['eq'] == 'party':
                    cmd.extend(['-af','equalizer=0:1.5:2:-7:-10:-5:-10:-10:1:1,volume='+str((10*math.log10(vol or 10**-30)+5))])
                else:
                    cmd.extend(['-af','equalizer=' +":".join(extras['eq'])+",volume="+str((10*math.log10(vol or 10**-30)+5))])
            if 'loop' in kw:
                cmd.extend(["-loop", str(0 if kw['loop'] is True else int(kw['loop']))])

            self.started = time.time()
            cmd.append(filename)
            self.process = subprocess.Popen(cmd,stdin=subprocess.PIPE, stdout = f, stderr = g)
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
            except:
                pass

        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None

        def position(self):
            return time.time() - self.started

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

    def playSound(self,filename,handle="PRIMARY",**kwargs):


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
            
        if 'novideo' in kwargs:
            e['novideo'] = kwargs['novideo']

        if 'eq' in kwargs:
            extras={'eq':kwargs['eq']}
        else:
            extras={}
        #Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        #Raise an error if the file doesn't exist
        fn = util.search_paths(filename, sound_paths)
        #Raise an error if the file doesn't exist
        if not fn or not os.path.isfile(fn):
            raise ValueError("Specified audio file'"+filename+"' not found")

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
    


l = {'sox':SOXWrapper, 'mpg123':Mpg123Wrapper, "mplayer":MPlayerWrapper, "madplay":MadPlayWrapper}


backend = SoundWrapper()
if util.which('pulseaudio'):
    pulseaudio=True
else:
    pulseaudio=False
    
    
for i in config['audio-backends']:
    if util.which(i):
        backend = l[i]()
        break


#Make fake module functions mapping to the bound methods.
playSound = backend.playSound
stopSound = backend.stopSound
isPlaying = backend.isPlaying
pause = backend.pause
resume = backend.resume
stopAllSounds = backend.stopAllSounds
setvol = backend.setVolume
setEQ = backend.setEQ
position = backend.getPosition
playSound("alert.ogg",handle="poop",loop=True)
