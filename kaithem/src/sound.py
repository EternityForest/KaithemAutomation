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

import subprocess,os

#This class provides some infrastructure to play sounds but if you use it directly it is a dummy.
class SoundWrapper(object):
 
    runningSounds = {}
    backendname = "Dummy Sound Driver(MPG123 not found)"
    #little known fact: Kaithem is actually a large collection of
    #mini garbage collectors and bookkeeping code...
    def deleteStoppedSounds(self):
        for i in self.runningSounds.keys():
            try:
                if not self.runningSounds[i].playing():
                    self.runningSounds.pop(i)
            except KeyError:
                pass
    
    def stopAllSounds(self):
        for i in self.runningSounds.keys():
            try:
                self.runningSounds.pop(i)
            except KeyError:
                pass
    
    def playSound(self,filename,handle="PRIMARY"):
        pass
    def stopSound(self, handle ="PRIMARY"):
        pass
    

class Mpg123Wrapper(SoundWrapper):
    backendname = "MPG123 Sound Player"
    
    #What this does is it keeps a reference to the sound player process and
    #If the object is destroyed it destroys the process stopping the sound
    #It also abstracts checking if its playing or not.
    class Mpg123SoundContainer(object):
        def __init__(self,filename):
            self.process = subprocess.Popen(["mpg123",filename])
            
        def __del__(self):
            self.process.terminate()
        
        def playing(self):
          return self.process.poll()
        
    def playSound(self,filename,handle="PRIMARY"):
        #Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        #Raise an error if the file doesn't exist
        if not os.path.isfile(filename):
            raise ValueError("Specified audio file'"+filename+"' does not exist")
        
        #Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.Mpg123SoundContainer(filename)
    
    def stopSound(self, handle ="PRIMARY"):
        #Delete the sound player reference object and its destructor will stop the sound
            if handle in self.runningsounds:
                #Instead of using a lock lets just catch the error is someone else got there first.
                try:
                    del self.runningSounds[handle]
                except KeyError:
                    pass
    
            
#See if we have mpg123 installed at all and if not use the dummy driver.
if subprocess.check_output("which mpg123",shell = True):
    backend = Mpg123Wrapper()
else:
    backend = SoundWrapper()

#Make fake module functions mapping to the bound methods.
playSound = backend.playSound
stopSound = backend.stopSound
stopAllSounds = backend.stopAllSounds


    
    
