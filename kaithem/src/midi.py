#Copyright Daniel Dunn 2019
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


from . import directories
import os, yaml,logging,weakref

#https://musical-artifacts.com/artifacts/639
DEFAULT_SOUNDFONT = os.path.join(directories.datadir, "sounds/babyfont.sf3")


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
    with open(os.path.join(directories.datadir,"gm_instruments.yaml")) as f:
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
                return (bank,i)
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
    def __init__(self, soundfont=DEFAULT_SOUNDFONT,jackClientName=None,
        connectMidi=None, connectOutput=None,reverb=False,chorus=False, ondemand=True):
        players[id(self)]=self

        if jackClientName:
           from . import jackmanager
           if not jackmanager.getPorts():
               raise RuntimeError("It appears that JACK is not running")
               
        if not os.path.isfile(soundfont):
            raise OSError("Soundfont: "+soundfont+" does not exist or is not a file")
        self.soundfont = soundfont

        import fluidsynth
        self.fs = fluidsynth.Synth()
        self.fs.setting("synth.chorus.active", 1 if chorus else 0)
        self.fs.setting("synth.reverb.active", 1 if reverb else 0)

        try:
            self.fs.setting("synth.dynamic-sample-loading", 1 if ondemand else 0)
        except:
            logging.exception("No dynamic loading support, ignoring")
        self.sfid = self.fs.sfload(soundfont)
        usingJack = False

        if jackClientName:
           self.fs.setting("audio.jack.id", jackClientName)
           usingJack = True

        if connectMidi:
            pass
            #self.midiAirwire = jackmanager.Mono

        if connectOutput:
            self.airwire= jackmanager.Airwire(jackClientName or 'KaithemFluidsynth',connectOutput)
            self.airwire.connect()

        if usingJack:
           if not jackClientName:
                self.fs.setting("audio.jack.id", "KaithemFluidsynth")

           self.fs.setting("midi.driver", 'jack')
           self.fs.start(driver="jack", midi_driver="jack")

        else:
            self.fs.start()

    def setInstrument(self,channel, instrument,bank=0):
        bank, insNumber = findGMInstrument(instrument,self.soundfont,bank)
        self.fs.program_select(channel, self.sfid, bank, insNumber)

    def __del__(self):
        if hasattr(self,'fs'):
            self.fs.delete()

class MidiAPI():
    instrumentSearch = getGMInstruments
    FluidSynth = FluidSynth
    @property
    def numbersToGM(self):
        return getGMInstruments()

    