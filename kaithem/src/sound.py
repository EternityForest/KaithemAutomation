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

import subprocess,os,math
from . import util
from .config import config


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
    
    def playSound(self,filename,handle="PRIMARY",**kwargs):
        pass
    
    def stopSound(self, handle ="PRIMARY"):
        pass
    
    def isPlaying(self):
        return False
    
    

class Mpg123Wrapper(SoundWrapper):
    backendname = "MPG123 Sound Player"
    
    #What this does is it keeps a reference to the sound player process and
    #If the object is destroyed it destroys the process stopping the sound
    #It also abstracts checking if its playing or not.
    class Mpg123SoundContainer(object):
        def __init__(self,filename):
            f = open(os.devnull,"w")
            g = open(os.devnull,"w")
            self.process = subprocess.Popen(["mpg123",filename], stdout = f, stderr = g)
            
        def __del__(self):
            try:
                self.process.terminate()
            except:
                pass
        
        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None
        
    def playSound(self,filename,handle="PRIMARY",**kwargs):
        #Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        #Raise an error if the file doesn't exist
        if not os.path.isfile(filename):
            raise ValueError("Specified audio file'"+filename+"' does not exist")
        
        #Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.Mpg123SoundContainer(filename)
    
    def stopSound(self, handle ="PRIMARY"):
        #Delete the sound player reference object and its destructor will stop the sound
            if handle in self.runningSounds:
                #Instead of using a lock lets just catch the error is someone else got there first.
                try:
                    del self.runningSounds[handle]
                except KeyError:
                    pass
    
    def isPlaying(self,channel = "PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].isPlaying()
        except KeyError:
            return False

class SOXWrapper(SoundWrapper):
    backendname = "SOund eXchange"
    
    #What this does is it keeps a reference to the sound player process and
    #If the object is destroyed it destroys the process stopping the sound
    #It also abstracts checking if its playing or not.
    class SOXSoundContainer(object):
        def __init__(self,filename,vol,start,end):
            f = open(os.devnull,"w")
            g = open(os.devnull,"w")
            self.started = time.time()
            self.process = subprocess.Popen(["play",filename,"vol",str(vol),"trim",str(start),str(end)], stdout = f, stderr = g)
            
        def __del__(self):
            try:
                self.process.terminate()
            except:
                pass
        
        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None
        
        def position(self):
            return self.started
        
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
        if not os.path.isfile(filename):
            raise ValueError("Specified audio file'"+filename+"' does not exist")
        
        #Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.SOXSoundContainer(filename,v,start,end)
    
    def stopSound(self, handle ="PRIMARY"):
        #Delete the sound player reference object and its destructor will stop the sound
            if handle in self.runningSounds:
                #Instead of using a lock lets just catch the error is someone else got there first.
                try:
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
        def __init__(self,filename,vol,start,end,**kw):
            f = open(os.devnull,"w")
            g = open(os.devnull,"w")
            
            cmd = ["mplayer",filename,"slave","quiet","af","volume",str(math.log10(vol)*5),"ss",str(start)]
            if end:
                cmd.extend(["endpos",str(end)])
            if "output" in kw:
                cmd.extend(["ao","pulse"+kw['output']])
            self.process = subprocess.Popen(cmd,stdout = f, stderr = g)
            
        def __del__(self):
            try:
                self.process.terminate()
            except:
                pass
        
        def isPlaying(self):
            self.process.poll()
            return self.process.returncode == None
        
        def position(self):
            return float(self.process.communicate("get_time_pos").decode('utf8').split('='))
        
        def setVol(self,volume):
            self.process.communicate("volume "+str(volume*100)+" 1")
        
    def playSound(self,filename,handle="PRIMARY",**kwargs):
        
        
        if 'volume' in kwargs:
            #odd way of throwing errors on non-numbers
            v  = float(kwargs['volume'])*100
        else:
            v =100;
        
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
        #Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        #Raise an error if the file doesn't exist
        if not os.path.isfile(filename):
            raise ValueError("Specified audio file'"+filename+"' does not exist")
        
        #Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.MPlayerSoundContainer(filename,v,start,end,**e)
    
    def stopSound(self, handle ="PRIMARY"):
        #Delete the sound player reference object and its destructor will stop the sound
            if handle in self.runningSounds:
                #Instead of using a lock lets just catch the error is someone else got there first.
                try:
                    del self.runningSounds[handle]
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
        

l = {'sox':SOXWrapper, 'mpg123':Mpg123Wrapper, "mplayer":MPlayerWrapper}


backend = SoundWrapper()

for i in config['audio-backends']:
    if util.which(i):
        #Don't use MPlayer without pulseaudio, we need to support mu
        if i =="mplayer":
            if util.which("pulseaudio"):
                backend = l[i]()
                break
        else:
            backend = l[i]()
            break
            

#Make fake module functions mapping to the bound methods.
playSound = backend.playSound
stopSound = backend.stopSound
isPlaying = backend.isPlaying
stopAllSounds = backend.stopAllSounds
setvol = backend.setVolume
position = backend.getPosition

    
    
