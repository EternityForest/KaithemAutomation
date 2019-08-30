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
__doc__=''



import weakref
import threading
import base64

import os,re,time,subprocess,hashlib,struct,threading,atexit,select,traceback

#Util is not used anywhere else
from . import util, workers
wordlist = util.mnemonic_wordlist

#This is an acceptable dependamcy, it will be part of libkaithem if such a thing exists
from . import messagebus

import logging

log = logging.getLogger("system.jack")

jackclient =None
#from, to pairs.
connections=[]

lock = threading.RLock()

#Currently we only support using the default system card as the
#JACK backend. We prefer this because it's easy to get Pulse working right.
usingDefaultCard = True

def isConnected(f,t):
    if not isinstance(f, str):
        f=f.name
    if not isinstance(t, str):
        t=t.name

    with lock:
        return jackclient.get_port_by_name(t) in jackclient.get_all_connections(jackclient.get_port_by_name(f))

def setupPulse():
    try:
        subprocess.check_call(['pulseaudio','-k'],timeout=5)
    except:
        pass
    time.sleep(0.1)
    try:
        #This may mean it's already running, but hanging in some way
        try:
            subprocess.check_call(['pulseaudio','-D'],timeout=5)
        except:
            subprocess.check_call(['killall','-9','pulseaudio'],timeout=5)
            subprocess.check_call(['pulseaudio','-D'],timeout=5)
            pass
        time.sleep(0.1)
        subprocess.check_call("pactl load-module module-jack-sink channels=2; pactl load-module module-jack-source channels=2; pacmd set-default-sink jack_out;",shell=True,timeout=5)
    except:
        log.exception("Error configuring pulseaudio")

def ensureConnections(*a,**k):
    "Auto restore connections in the connection list"
    try:
        with lock:
            for i in allConnections:
                try:
                    allConnections[i].reconnect()
                except:
                    print(traceback.format_exc)
    except:
        log.exception("Probably just a weakref that went away.")
messagebus.subscribe("/system/jack/newport",ensureConnections)

import weakref
allConnections=weakref.WeakValueDictionary()

activeConnections=weakref.WeakValueDictionary()


errlog = []

class MonoAirwire():
    """Represents a connection that should always exist as long as there
    is a reference to this object. You can also enable and disable it with 
    the connect() and disconnect() functions.
    
    They start out in the connected state
    """
    def __init__(self, orig, to):
        self.orig=orig
        self.to = to
        self.active = True

    def disconnect(self):
        self.disconnected = True
        try:
            del allConnections[self.orig, self.to]
        except:
            pass
        try:
            with lock:
                if isConnected(self.orig,self.to):
                    jackclient.disconnect(self.orig, self.to)
                    del activeConnections[self.orig,self.to]
        except:
            pass

    def __del__(self):
        if self.active:
            with lock:
                if isConnected(self.orig,self.to):
                    jackclient.disconnect(self.orig, self.to)

    def connect(self):
        allConnections[self.orig, self.to]= self
        self.connected=True
        self.reconnect()

    def reconnect(self):
        if self.orig and self.to:
            try:
                if not isConnected(self.orig,self.to):
                    with lock:
                        jackclient.connect(self.orig,self.to)
                    activeConnections[self.orig, self.to]=self
            except:
                print(traceback.format_exc())

class Effect():
    def __init__(self, effectype):
        pass
        #Todo, create the gstreamer element 

class MultichannelAirwire(MonoAirwire):
    "Link all outputs of f to all inputs of t, in sorted order"


    def _getEndpoints(self):
        f = self.orig
        if not f:
            return None,None
        
        t = self.to
        if not t:
            return None,None
        return f,t

    def reconnect(self):
        """Connects the outputs of channel strip(Or other JACK thing)  f to the inputs of t, one to one, until
        you run out of ports. 
        
        Note that channel strips only have the main inputs but can have sends,
        so we have to distinguish them in the regex.
        """
        if not self.active:
            return
        f,t=self._getEndpoints()
        if not f:
            return

        with lock:
            if jackclient:
                outPorts = jackclient.get_ports(f+":*",is_output=True,is_audio=True)
                inPorts = jackclient.get_ports(t+":*",is_input=True,is_audio=True)
                #Connect all the ports
                for i in zip(outPorts,inPorts):
                    if not isConnected(i[0].name,i[1].name):
                        jackclient.connect(i[0],i[1])
                        activeConnections[i[0].name,i[1].name]=self

    def disconnect(self):
        if not jackclient:
            return
        f,t=self._getEndpoints()
        if not f:
            return

        with lock:
            outPorts = jackclient.get_ports(f+":*",is_output=True,is_audio=True)
            inPorts = jackclient.get_ports(t+":*",is_input=True,is_audio=True)

            #Connect all the ports
            for i in zip(outPorts,inPorts):
                if isConnected(i[0],i[1]):
                    jackclient.disconnect(i[0],i[1])
                    try:
                        del activeConnections[i[0].name,i[1].name]
                    except KeyError:
                        pass

    def __del__(self):
        self.disconnect()


def CombiningAirwire(MultichannelAirwire):
    def reconnect(self):
        """Connects the outputs of channel strip f to the port t. As in all outputs
        to one input.
        """
        if not self.active:
            return
        f,t=self._getEndpoints()
        if not f:
            return
        with lock:
            outPorts = jackclient.get_ports(f+":*",is_output=True,is_audio=True)
        
            inPort = jackclient.get_ports(t)[0]
            if not inPort:
                return


            #Connect all the ports
            for i in outPorts:
                if not isConnected(i.name,inPort.name):
                    jackclient.connect(i,inPort)




    def disconnect(self):
        f,t=self._getEndpoints()
        if not f:
            return

        with lock:
            outPorts = jackclient.get_ports(f+":*",is_output=True,is_audio=True)
        
            inPort = jackclient.get_ports(t)[0]
            if not inPort:
                return

            #Disconnect all the ports
            for i in outPorts:
                if isConnected(i.name,inPort.name):
                    i.disconnect(inPort)
                    try:
                        del activeConnections[i,inPort]
                    except KeyError:
                        pass

def Airwire(f,t):
    if f==None or t==None:
        return MonoAirwire(None,None)
    if ":" in f:
        if not ":" in t:
           return CombiningAirwire(f,t)
        return MonoAirwire(f,t)
    else:
        return MultichannelAirwire(f,t)

def onPortConnect(a,b,connected):
    #Whem things are manually disconnected we don't
    #Want to always reconnect every time
    if not connected:
        log.info("JACK port "+ a.name+" disconnected from "+b.name)
        i = (a.name,b.name)
        #Try to stop whatever airwire or set therof
        #from remaking the connection
        if i in activeConnections:
            try:
                #Deactivate first, that must keep it from using the api
                #From within the callback
                activeConnections[i].active=False
                del allConnections[i]
                del activeConnections[i]
            except:
                pass
    else:
        log.info("JACK port "+ a.name+" connected to "+b.name)

def onPortRegistered(port,registered):
    if registered:
        log.info("JACK port registered: "+port.name)
        messagebus.postMessage("/system/jack/newport",[port.name, port.is_input] )
    else:
        log.info("JACK port unregistered: "+port.name)
        messagebus.postMessage("/system/jack/delport",port.name)

class ChannelStrip():
    def init(self, name,stereo=False, sends=[]):
        """What is a channel strip? It takes 1 or two input channels,
            puts them through a fader, a variable number of effects sends
            that can all have individual destinations,

            then puts the main signal through a set of effects
            (Generated from Effect objects), then onto a Destination,
            which is either a single port, or a pair of ports for
            stereo. 
            
            If the destination is simply the name of a client,
            it's first 2 ports will be used, in sorted order.

            If the client has only 1 port, then BOTH channels will
            be linked to that ONE input.
        
        """
        self.name=name
        self.effects=[]
        self.destination = b''
        self.source =b''
        self.sends = sends

        self.send_airwires = []

    def connectOutput(self, dest):
       self.outAirwire = Airwire(self,dest)
    
    def connectInput(self, src):
        self.inAirwire = Airwire(src, self)





############################################################################
####################### This section manages the actual sound IO and creates jack ports



#This code runs once when the event loads. It also runs when you save the event during the test compile
#and may run multiple times when kaithem boots due to dependancy resolution
__doc__=''

oldi,oldo,oldmidis  = None,None,None



alsa_in_instances={}
alsa_out_instances ={}

failcards = {}

#The options we use to tune alsa_in and alsa_out
#so they don't sound horrid
iooptions=["-p", "128", "-t","384", "-m", "384", "-q","1", "-r", "48000", "-n","32"]



toretry_in = {}
toretry_out ={}


def compressnumbers(s):
    """Take a string that's got a lot of numbers and try to make something 
        that represents that number. Tries to make
        unique strings from things like usb-0000:00:14.0-2
    
    """
    n = ''
    currentnum = ''
    for i in s:
        if i in '0123456789':
            #Exclude leading zeros
            if currentnum or (not(i=='0')):
                currentnum+=i
        else:
            n+=currentnum
            currentnum=''

    return n+currentnum

  


def try_stop(p):
    try:
        p.terminate()
    except:
        pass
def closeAlsaProcess(x):
    #Why not a proper terminate?
    #It seemed to ignore that sometimes.
    x.kill()
    x.wait()




def cleanupstring(s):
    "Get rid of special characters and common redundant words that provide no info"
    x = s.replace(":0","0")
    x = s.replace(":0",":")
    x = s.replace(":0",":")

    x = s.replace(" ","").replace("\n","").replace("*","").replace("(","")
    x=x.replace(")","").replace("-","").replace(":",".").replace("Audio","")
    x=x.replace("Lpe","").replace("-","").replace("Generic","").replace("Device",'')
    return x


def enumeratePCI():
    "generate the PCI numbering that cardsfromregex needs"
    #We are going to list out all the PCI bus devices and give them numbers
    #So we can use fewer bits for that. Here we assign them all numbers hopefully
    #From 0 to 128. Scatter around by hash to at least try to stay consistent if
    #They change.
    pciNumbers = {}
    usedNumbers = {}
    if os.path.exists("/sys/bus/pci/devices"):
        for i in sorted(os.listdir("/sys/bus/pci/devices")):
            n=struct.unpack("<Q",hashlib.sha1(i.encode('utf8')).digest()[:8])[0]%128
            while n in usedNumbers:
                n+=1
            usedNumbers[n]=i
            pciNumbers[n]=i
    return pciNumbers




def assignName(locator,longname, usedFirstWords,pciNumbers):
    """Given the relevant context, return a two-word easy to remember name to the card with the given
        'locator' which is usually something like usb-0000:00:14.0-1
    """
    #Handle USB locators
    if 'usb' in locator:
        x = locator.split("-")
        if len(x)>2:
            controller = x[1]
            usbpath = x[2]

            if not controller in pciNumbers:
                #Not a PCI controller. We don't know how to enumerate these in a compact
                #Way, so we have to just trust that there is only one or two of them
                pval = 1
                accum = 0
                #Use base 8 to convert the usb path into a number. Assume that it's little endian.
                #We of course may have numbers that overflow and such, but we will deal with collisions
                #From that.
                digitNumber = 0
                for j in reversed(controller):
                    if j.lower() in '0123456789abcdef':
                        accum+=int(j,16)*pval
                        #Optimize for PCI bus stuff.  The last digit(Reversed to the first)
                        #Can only be 0 to 7. We use a nonlinear base system where the firt hex
                        #digit is multiplied by 8, and the second by 8*16, even though it can be up to 15.
                        #This is very confusing.
                        if digitNumber:
                            pval*=16
                        else:
                            pval*=8
                        digitNumber +=1

                #We just have to trust that we aren't likely to have two of these weird USB
                #things with locators separated by more than 128, and if we do the chance
                #of collision is low anyway.  This whole block is mostly for embedded ARM stuff
                #with one controller
                n = usbpath[0]
                if n in '0123456789':
                    accum = int(n)*128
            else:
                #We know the PCI number we generated for this. Take the first digit
                #Of the path and add it in, so that the first word varies with root port.
                #This seems kinda nice, to group things by root port.
                n = usbpath[0]
                if n in '0123456789':
                    accum = int(n)*128 +pciNumbers[controller]
                else:
                    accum=pciNumbers[controller]

            #Choose an unused first word based on what the controller is.
            first= wordlist[accum%1621]
            s= 0
            #Now we are going to fix collisons.
            while first in usedFirstWords and s<100:
                s+=1
                if usedFirstWords[first]==controller:
                    break
                first=memorableHash(controller+str(s))
            usedFirstWords[first]=controller

            pval = 1
            accum = 0
            #Use base 8 to convert the usb path into a number. Assume that it's little endian.
            #We of course may have numbers that overflow and such, but we will deal with collisions
            #From that.
            for j in usbpath:
                if j in '0123456789':
                    accum+=int(j)*pval
                    pval*=8
            # 1621 is a prime number. We use this for modulo
            # to prevent discarding higher order bits.
            second = wordlist[accum%1621]
        else:
            first = memorableHash(x[2])
            second = memorableHash(x[1])
    #handle nonusb
    else:
        controller =locator
        first=memorableHash(controller)

        while first in usedFirstWords and s<100:
            s+=1
            if usedFirstWords[first]==controller:
                break
            first=memorableHash(controller+str(s))
        second=memorableHash(longname)


    #Note that we could still have collisions. We are going to fix that
    #In the second step
    h = first+second
    return h
def generateJackName(words,longname, numberstring,  taken, taken2):
    "Generate a name suitable for direct use as a jack client name"
    n = cleanupstring(longname)
    jackname =n[:4]+'_'+words
    jackname+=numberstring
    jackname=jackname[:28]
    #If there's a collision, we're going to redo everything
    #This of course will mean we're going back to 
    while (jackname in taken) or jackname in taken2:
        h = memorableHash(jackname+cards[i[0]]+":"+i[2])[:12]
        n = cleanupstring(longname)
        jackname =n[:4]+'_'+words
        jackname+=numberstring
        jackname=jackname[:28]
    return jackname

def cardsfromregex(m, cards,usednames = [],pciNumbers={},usedFirstWords = {}):
    """Given the regex matches from arecord or aplay, match them up to the actual 
    devices and give them memorable aliases"""

    d = {}
    #Why sort? We need consistent ordering so that our conflict resolution
    #has the absolute most possible consistency
    def key(a):
        "Sort USBs last, so that PCI stuff gets the first pick"
        return(1 if ('usb' in a[2].lower()) else 0, a)

    m= sorted(m)
    for i in m:
        #We generate a name that contains both the device path and subdevice
        generatedName = cards[i[0]]+"."+i[2]

        longname=i[3]
        locator = cards[i[0]]
        numberstring = compressnumbers(locator)

        h = assignName(locator,longname,usedFirstWords,pciNumbers)

        jackname = generateJackName(h, longname,numberstring,d, usednames)
        
        longname = h+"_"+memorableHash(cards[i[0]]+":"+i[2],num=4,caps=True)+"_"+cards[i[0]]
        
        try:
            d[jackname]  = ("hw:"+i[0]+","+i[2], cards[i[0]], (int(i[0]), int(i[2])), longname)
        except KeyError:
            d[jackname] = ("hw:"+i[0]+","+i[2], cards[i[0]], (int(i[0]), int(i[2])), longname)
    return d



def midiClientsToCardNumbers():
    #Groups are clientnum, name, cardnumber, only if the client actually has a card number
    pattern =r"client\s+(\d+):.+?'(.+?)'.+?card=(\d+)."
    x = subprocess.check_output(['aconnect','-i'],stderr=subprocess.DEVNULL).decode("utf8")
    x = re.findall(pattern,x)

    clients = {}
    for i in x:
        clients[int(i[0])] = (i[1], int(i[2]))
    
    x = subprocess.check_output(['aconnect','-o'],stderr=subprocess.DEVNULL).decode("utf8")
    x = re.findall(pattern,x)

    clients = {}
    for i in x:
        clients[int(i[0])] = (i[1], int(i[2]))
    return clients



midip =None

def scanMidi(m, cards,usednames = [],pciNumbers={},usedFirstWords = {}):
    """Given the regex matches from amidi -l, match them up to the actual 
    devices and give them memorable aliases.
    
    Return a dict that maps the name we have assigned the client, to a name, alsaClientNumber
    which can be used to find the ports "a2jmidid -e" may have registered, and give them aliases.

    Note that the client may have multiple ports, so we have to add disambiguation later.
    """

    d = {}

    midiInfo = midiClientsToCardNumbers()

    for i in midiInfo:
        name= midiInfo[i][0]
        card = str(midiInfo[i][1])
        
        if card in cards:
            locator = cards[card]
        else:
            continue

        numberstring = compressnumbers(locator)

        h = assignName(locator,name,usedFirstWords,pciNumbers)

        jackname = generateJackName(h, name,numberstring,d, usednames)
        
        d[jackname]  = (name,i)
    return d



def readAllSoFar(proc, retVal=b''): 
  counter = 128
  while counter:
    x =(select.select([proc.stdout],[],[],0.1)[0])
    if x:   
        retVal+=proc.stdout.read(1)
    else:
        break
    counter -=1
  return retVal

def readAllErrSoFar(proc, retVal=b''): 
  counter = 128
  while counter:
    x =(select.select([proc.stderr],[],[],0.1)[0])
    if x:   
        retVal+=proc.stderr.read(1)
    else:
        break
    counter -=1
  return retVal

def listSoundCardsByPersistentName():
    """
        Only works on linux or maybe mac

       List devices in a dict indexed by human-readable and persistant easy to memorize
       Identifiers. Output is tuples:
       (cardnamewithsubdev(Typical ASLA identifier),physicalDevice(persistent),devicenumber, subdevice)
    
    """
    with open("/proc/asound/cards") as f:
        d = f.read()

    #RE pattern produces cardnumber, cardname, locator
    c = re.findall(r"[\n\r]*\s*(\d)+\s*\[(\w+)\s*\]:\s*.*?[\n\r]+\s*.*? at (.*?)[\n\r]+",d)

    #Catch the ones that don't have an "at"
    c2 = re.findall(r"[\n\r]*\s*(\d)+\s*\[(\w+)\s*\]:\s*.*?[\n\r]+\s*(.*?)[\n\r]+",d)

    cards = {}
    #find physical cards
    for i in c:
        n = i[2].strip().replace(" ","").replace(",fullspeed","").replace("[","").replace("]","")
        cards[i[0]] = n

    #find physical cards
    for i in c2:
        #Ones with at are caught in c
        if ' at ' in i[2]:
            continue
        n = i[2].strip().replace(" ","").replace(",fullspeed","").replace("[","").replace("]","")
        cards[i[0]] = n

    pci = enumeratePCI()
    usedFirstWords ={}

    x = subprocess.check_output(['aplay','-l'],stderr=subprocess.DEVNULL).decode("utf8")
    #Groups are cardnumber, cardname, subdevice, longname
    sd = re.findall(r"card (\d+): (\w*)\s\[.*?\], device (\d*): (.*?)\s+\[.*?]",x)
    outputs= cardsfromregex(sd,cards,pciNumbers=pci,usedFirstWords=usedFirstWords)
   

    x = subprocess.check_output(['arecord','-l'],stderr=subprocess.DEVNULL).decode("utf8")
    #Groups are cardnumber, cardname, subdevice, longname
    sd = re.findall(r"card (\d+): (\w*)\s\[.*?\], device (\d*): (.*?)\s+\[.*?]",x)
    inputs=cardsfromregex(sd,cards, pciNumbers=pci,usedFirstWords=usedFirstWords)

    midis=scanMidi(sd,cards, pciNumbers=pci,usedFirstWords=usedFirstWords)


    return inputs,outputs,midis


def memorableHash(x, num=1, separator="",caps=False):
    "Use the diceware list to encode a hash. Not meant to be secure."
    o = ""

    if isinstance(x, str):
        x = x.encode("utf8")
    for i in range(num):
        while 1:
            x = hashlib.sha256(x).digest()
            n = struct.unpack("<Q",x[:8])[0]%len(wordlist)
            e = wordlist[n]
            if caps:
                e=e.capitalize()
            #Don't have a word that starts with the letter the last one ends with
            #So it's easier to read
            if o:
                if e[0] == o[-1]:
                    continue
                o+=separator+e
            else:
                o=e
            break
    return o



def shortHash(x, num=8, separator=""):
    "Use the diceware list to encode a hash. Not meant to be secure."
    o = ""

    if isinstance(x, str):
        x = x.encode("utf8")
    x = hashlib.sha256(x).digest()
    b = base64.b64encode(x).decode("utf8").replace("+","").replace("/","")
    return b[:num]



def cleanup():
    import subprocess
    try:
        jackp.kill()
    except:
        pass
    with lock:
        for i in alsa_in_instances:
            alsa_in_instances[i].terminate()
        for i in alsa_out_instances:
            alsa_out_instances[i].terminate()
atexit.register(cleanup)


def stopJack():
    import subprocess
    #Get rid of old stuff
    from . import gstwrapper
    gstwrapper.stopAllJackUsers()
    try:
        subprocess.check_call(['killall','alsa_in'])
    except:
        pass
    try:
        subprocess.check_call(['killall','alsa_out'])
    except:
        pass
    try:
        subprocess.check_call(['killall','a2jmidid'])
    except:
        pass

    try:
        subprocess.check_call(['killall','jackd'])
    except:
        pass


jackp = None
def startJack():
    #Start the JACK server.
    global jackp
    
    if not jackp or not jackp.poll()==None:
        if midip:
            try:
                midip.kill()
            except:
                pass

        try:
            subprocess.check_call(['pulseaudio','-k'])
        except:
            pass
        f = open(os.devnull,"w")
        g = open(os.devnull,"w")
        jackp =subprocess.Popen(['jackd', '-S', '--realtime', '-P' ,'70' ,'-d', 'alsa' ,'-d' ,'hw:0,0' ,'-p' ,'128', '-n' ,'3' ,'-r','48000'],stdout=f, stderr=g,stdin=subprocess.DEVNULL)    
     
        try:
            subprocess.check_call(['chrt', '-f','-p', '70', str(jackp.pid)])
        except:
            log.exception("Error getting RT")
      
        def f():
            global midip
            #Poll till it's actually started, then post the message
            for i in range(120):
                if getPorts():
                    break
                time.sleep(0.5)
            messagebus.postMessage("/system/jack/started",{})
           
            if util.which("a2jmidid"):
                midip = subprocess.Popen("a2jmidid -e",stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True,stdin=subprocess.DEVNULL) 
        workers.do(f)

def handleManagedSoundcards():
    "Make sure that all of our alsa_in and out instances are working as they should be."
    global oldi
    global oldo
    global oldmidis

    #There seems to be a bug in reading errors from the process
    #Right now it's a TODO, but most of the time
    #we catch things in the add/remove detection anyway
    with lock:
        try:
            tr =[]
            for i in alsa_out_instances:
                
                x=readAllSoFar(alsa_out_instances[i])
                e=readAllErrSoFar(alsa_out_instances[i])
                problem = b"err =" in x+e or alsa_out_instances[i].poll()
                problem = problem or b"busy" in (x+e) 

                if problem:
                    log.error("Error in output "+ i +(x+e).decode("utf8") +" status code "+str(alsa_out_instances[i].poll()))
                    closeAlsaProcess(alsa_out_instances[i])
                    tr.append(i)
                    #We have to delete the busy stuff but we can
                    #retry later
                    if b"busy" in (x+e):
                        toretry_out[i]=time.monotonic()+5
                    elif b"No such" in (x+e):
                        toretry_out[i]=time.monotonic()+10
                        log.error("Nonexistant card "+i)
                    else:
                        toretry_out[i]=time.monotonic()

                    log.info("Removed "+i+"o")

                elif not alsa_out_instances[i].poll()==None:
                    tr.append(i)
                    log.info("Removed "+i+"o")

            for i in tr:
                try_stop(alsa_out_instances[i])
                del alsa_out_instances[i]

            tr =[]
            for i in alsa_in_instances:
                
                x= readAllSoFar(alsa_in_instances[i])
                e=readAllErrSoFar(alsa_in_instances[i])
                problem = b"err =" in x+e or alsa_in_instances[i].poll()
                problem = problem or b"busy" in (x+e) 
                if problem :
                    log.error("Error in input "+ i +(x+e).decode("utf8") +" status code "+str(alsa_in_instances[i].poll()))
                    closeAlsaProcess(alsa_in_instances[i])   
                    tr.append(i)
                    if b"busy" in (x+e):
                        toretry_in[i]=time.monotonic()+5
                    
                    if b"No such" in (x+e):
                        toretry_in[i]=time.monotonic()+10
                        log.error("Nonexistant card "+i)
                    else:
                        toretry_out[i]=time.monotonic()

                    log.info("Removed "+i+"i")

                elif not alsa_in_instances[i].poll()==None:
                    tr.append(i)
                    log.info("Removed "+i+"i")

            for i in tr:
                try_stop(alsa_in_instances[i])
                del alsa_in_instances[i]
        except:
            print(traceback.format_exc())



        ##HANDLE CREATING AND GC-ING things
        inp,op,midis = listSoundCardsByPersistentName()
        #This is how we avoid constantky retrying to connect the same few
        #clients that fail, which might make a bad periodic click that nobody
        #wants to hear.
        startPulse = False
        if (inp,op,midis)==(oldi,oldo,oldmidis):

            #However some things we need to retry.
            #Device or resource busy being the main one
            for i in inp:
                if i in toretry_in:
                    if time.monotonic() < toretry_in[i]:
                        continue
                    del toretry_in[i]
                    if not i in alsa_in_instances:
                        #Pulse likes to take over cards so we have to stop it, take the card, then start it. It sucks
                        startPulse = True
                        try:
                            subprocess.check_call(['pulseaudio','-k'])
                        except:
                            pass
                        time.sleep(2)
                        x = subprocess.Popen(["alsa_in"]+iooptions+["-d", inp[i][0], "-j",i+"i"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                        try:
                            subprocess.check_call(['chrt', '-f','-p', '70', str(x.pid)])
                        except:
                            log.exception("Error getting RT")
      
                        alsa_in_instances[i]=x
                        log.info("Added "+i+"i at"+inp[i][1])

            for i in op:
                if i in toretry_out:
                    if time.monotonic() < toretry_out[i]:
                        continue
                    del toretry_out[i]
                    if not i in alsa_out_instances:
                        startPulse=True
                        try:
                            subprocess.check_call(['pulseaudio','-k'])
                        except:
                            pass
                        x = subprocess.Popen(["alsa_out"]+iooptions+["-d", op[i][0], "-j",i+"o"]+iooptions,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                        alsa_out_instances[i]=x

                        try:
                            subprocess.check_call(['chrt', '-f','-p', '70', str(x.pid)])
                        except:
                            log.exception("Error getting RT")
                        log.info("Added "+i+"o")
            #If we stopped it, start it again
            if startPulse:
                setupPulse()

            return
            
        oldi,oldo,oldmidis =inp,op,midis
        print("Not the same")

        #Look for ports with the a2jmidid naming pattern and give them persistant name aliases.
        x = jackclient.get_ports(is_midi=True)
        for i in midis:
            for j in x:
                number = "["+str(midis[i][1])+"]"
                if number in j.name:
                    if i[0] in j.name:
                        try:
                            if not i in j.aliases:
                                print(j.aliases, i)
                                j.set_alias(i)
                        except:
                            log.exception("Error setting MIDI alias")


        for i in inp:
            #HDMI doesn't do inputs as far as I know
            if not i.startswith("HDMI"):
                if not i in alsa_in_instances:
                    if inp[i][0]== "hw:0,0":
                        #We don't do an alsa in for this card because it
                        #Is already the JACK backend
                        if usingDefaultCard:
                            continue
                    x = subprocess.Popen(["alsa_in"]+iooptions+["-d", inp[i][0], "-j",i+"i"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                    alsa_in_instances[i]=x
                    log.info("Added "+i+"i at "+inp[i][1])

        for i in op:
            if not i.startswith("HDMI"):
                if not i in alsa_out_instances:
                    #We do not want to mess with the 
                    if op[i][0]== "hw:0,0":
                        if usingDefaultCard:
                            continue
                    x = subprocess.Popen(["alsa_out"]+iooptions+["-d", op[i][0], "-j",i+'o']+iooptions,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                    alsa_out_instances[i]=x
                    log.info("Added "+i+"o at "+op[i][1])

        #In case alsa_in doesn't properly tell us about a removed soundcard
        #Check for things that no longer exist.
        try:
            tr =[]
            for i in alsa_out_instances:
                if not i in op:
                    tr.append(i)
            for i in tr:
                log.warning("Removed "+i+"o because the card was removed")
                try:
                    closeAlsaProcess(alsa_out_instances[i])
                except:
                    log.exception("Error closing process")
                del alsa_out_instances[i]

            tr =[]
            for i in alsa_in_instances:
                if not i in inp:
                    tr.append(i)
            for i in tr:
                log.warning("Removed "+i+"i because the card was removed")
                try:
                    closeAlsaProcess(alsa_in_instances[i])
                except:
                    log.exception("Error closing process")
                del alsa_in_instances[i]
        except:
            log.exception("Exception in loop")


def work():
    while(1):
        checkJack()
        checkJackClient()
        handleManagedSoundcards()
        ensureConnections()
        time.sleep(5)

t =None

didPatch = False
def startManagingJack():
    import jack, re
    global jackclient
    global t
    global didPatch

    if not didPatch:
        def _get_ports_fix(self, name_pattern='', is_audio=False, is_midi=False,
                    is_input=False, is_output=False, is_physical=False,
                    can_monitor=False, is_terminal=False):
            if name_pattern:
                re.compile(name_pattern)
                    
            return jack.Client._get_ports(self, name_pattern, is_audio, is_midi, 
                                        is_input, is_output, is_physical, 
                                        can_monitor, is_terminal)

        jack.Client._get_ports = jack.Client.get_ports
        jack.Client.get_ports = _get_ports_fix
        didPatch = True

    atexit.register(cleanup)
    stopJack()
    startJack()

 

    for i in range(10):
        try:
            #Close any existing stuff
            if jackclient:
                jackclient.close()
                jackclient=None
            jackclient = jack.Client("Overseer",no_start_server=True)
            break
        except:
            time.sleep(1)
            #If we couldn't get it working, try shutting down some possible conflicts with -9
            if i==8:
                try:
                    subprocess.check_call(['killall', '-9', 'jackd'])
                except:
                    log.exception("err")
                try:
                    subprocess.check_call(['pulseaudio', '-k'])
                    time.sleep(2)
                except:
                    log.exception("err")
                try:
                    subprocess.check_call(['killall', '-9', 'pulseaudio'])
                except:
                    log.exception("err")
                time.sleep(3)
                startJack()

            if i<9:
                continue
            raise
    with lock:
        jackclient.set_port_registration_callback(onPortRegistered)
        jackclient.set_port_connect_callback(onPortConnect)
    jackclient.activate()
    setupPulse()
    log.debug("Set up pulse")
    t = threading.Thread(target=work)
    t.name="JackReconnector"
    t.daemon=True
    t.start()



def checkJack():
    global jackp
    if jackp and jackp.poll() !=None:
        startJack()

def checkJackClient():
    global jackclient
    import jack
    with lock:
        if not jackclient:
            return []
        ports =[]
        try:
            return jackclient.get_ports()
        except:
            try:
                jackclient.close()
            except:
                pass
            try:
                jackclient=jack.Client("Overseer")
            except:
                log.exception("Error creating JACK client")
def getPorts(*a,**k):
    with lock:
        if not jackclient:
            return []
        ports =[]
        return jackclient.get_ports(*a,**k)


def getPortNamesWithAliases(*a,**k):
    with lock:
        if not jackclient:
            return []
        ports =[]
        x= jackclient.get_ports(*a,**k)
        for i in x:
            for j in i.aliases:
                if not j in ports:
                    ports.append(j)
            if not i.name in ports:
                ports.append(i.name)
        return ports


def getConnections(name,*a,**k):
    with lock:
        if not jackclient:
            return []
        return jackclient.get_all_connections(name)

def connect(f,t):
      with lock:
        if not jackclient:
            return 
        if  isinstance(f,str):
            f = jackclient.get_port_by_name(f)
        if  isinstance(t,str):
            t = jackclient.get_port_by_name(t)
        
        f_input =  f.is_input

        if f.is_input:
            if not t.is_output:
                #Do a retry, there seems to be a bug somewhere
                f = jackclient.get_port_by_name(f.name)
                t = jackclient.get_port_by_name(t.name)
                if f.is_input:
                    if not t.is_output:
                         raise ValueError("Cannot connect two inputs",str((f,t)))
        else:
            if t.is_output:
                raise ValueError("Cannot connect two outputs",str((f,t)))
        f=f.name
        t=t.name
        try:
            if f_input:
                return jackclient.connect(t,f)    
            else:
                return jackclient.connect(f,t)
        except:
            pass
            
#startManagingJack()


