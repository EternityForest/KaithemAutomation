
#Copyright Daniel Dunn 2020 

#Scullery is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Scullery is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Scullery.  If not, see <http://www.gnu.org/licenses/>.

import time,weakref,os
gmInstruments = None

players = weakref.WeakValueDictionary()


def allNotesOff():
    try:
        for i in players:
            players[i].fs.all_notes_off(-1)
    except:
        pass


def getGMInstruments():
    global gmInstruments
    if gmInstruments:
        return gmInstruments
    with os.path.join(os.path.dirname(os.path.abspath(__file__)),'gm_instruments.yaml') as f:
        gmInstruments = yaml.load(f.read())
    return gmInstruments

def findGMInstrument(name, look_in_soundfont=None,bank=None):
    #Allow manually selected instruments
    try:
        return (bank,int(name))
    except:
        pass
    name = name.replace("(",'').replace(')','')
    #Try to find a matching patch name in the soundfont
    if look_in_soundfont:
        try:
            from sf2utils.sf2parse import Sf2File
            with open(look_in_soundfont, 'rb') as sf2_file:
                sf2 = Sf2File(sf2_file)
            #Names
            x= [i[0].split(b"\0")[0].decode("utf8") for i in sf2.raw.pdta['Phdr']]
        except Exception as e:
            logging.exception("Can't get metadata from this soundfont")
            print("Error looking through soundfont data",e)
            x = []

        #Indexes
        for i in range(len(x)):
            n = x[i].lower()
            n=n.replace("(",'').replace(')','')
            n=n.split(" ")            
            match = True

            for j in name.lower().split(" "):
                if not j in n:
                    #Bank 128 is reserved for drums so it can substitute for drum related words
                    if not (j in ('kit','drums','drum') and sf2.raw.pdta['Phdr'][i][2]==128):
                        match = False
            if match:
                if bank==None:
                    return (sf2.raw.pdta['Phdr'][i][2],sf2.raw.pdta['Phdr'][i][1])
                return (bank,sf2.raw.pdta['Phdr'][i][1])

    x= getGMInstruments()
    for i in x:
        n = x[i].lower()
        n=n.replace("(",'').replace(')','')
        n=n.split(" ")
        match = True
        for j in name.lower().split(" "):
            if not j in n:
                match = False
        if match:
            return (bank or 0,i)
    raise ValueError("No matching instrument")

class FluidSynth():
    defaultSoundfont = "/usr/share/sounds/sf2/FluidR3_GM.sf2"

    def __init__(self, soundfont=None,jackClientName=None,
        connectMidi=None, connectOutput=None,reverb=False,chorus=False, ondemand=True):
        players[id(self)]=self

        if jackClientName:
           from . import jack
           if not jack.getPorts():
               raise RuntimeError("It appears that JACK is not running")
        
        self.soundfont = soundfont or self.defaultSoundfont

        if not os.path.isfile(self.soundfont):
            raise OSError("Soundfont: "+soundfont+" does not exist or is not a file")

        from . thirdparty import fluidsynth
        self.fs = fluidsynth.Synth()
        self.fs.setting("synth.chorus.active", 1 if chorus else 0)
        self.fs.setting("synth.reverb.active", 1 if reverb else 0)

        try:
            self.fs.setting("synth.dynamic-sample-loading", 1 if ondemand else 0)
        except:
            logging.exception("No dynamic loading support, ignoring")
        self.sfid = self.fs.sfload(self.soundfont)
        usingJack = False

        if jackClientName:
           self.fs.setting("audio.jack.id", jackClientName)
           usingJack = True

        if connectMidi:
            pass
            #self.midiAirwire = jackmanager.Mono

        if connectOutput:
            self.airwire= jack.Airwire(jackClientName or 'KaithemFluidsynth',connectOutput)
            self.airwire.connect()

        if usingJack:
           if not jackClientName:
                self.fs.setting("audio.jack.id", "KaithemFluidsynth")

           self.fs.setting("midi.driver", 'jack')
           self.fs.start(driver="jack", midi_driver="jack")

        else:
            #self.fs.setting("audio.driver", 'alsa')
            self.fs.start()
        self.fs.program_select(0, self.sfid, 0, 0)

    def setInstrument(self,channel, instrument,bank=None):
        bank, insNumber = findGMInstrument(instrument,self.soundfont,bank)
        self.fs.program_select(channel, self.sfid, bank, insNumber)

    def noteOn(self,channel,note, velocity):
        self.fs.noteon(channel, note, velocity)

    def noteOff(self,channel,note):
        self.fs.noteoff(channel, note)

    def __del__(self):
        if hasattr(self,'fs'):
            self.fs.delete()
            del self.fs
