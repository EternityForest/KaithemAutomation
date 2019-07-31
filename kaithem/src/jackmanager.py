#This code runs once when the event loads. It also runs when you save the event during the test compile
#and may run multiple times when kaithem boots due to dependancy resolution
__doc__=''




import jack
import weakref
import threading
import base64

import os,re,time,subprocess,hashlib,struct,threading,atexit,select,traceback

import logging

log = logging.getLogger("system.jack")

jackclient =None
#from, to pairs.
connections=[]

#Currently we only support using the default system card as the
#JACK backend. We prefer this because it's easy to get Pulse working right.
usingDefaultCard = True

def setupPulse():
    try:
        subprocess.check_call("pulseaudio -k",shell=True)
        subprocess.check_call("pactl load-module module-jack-sink channels=2; pactl load-module module-jack-source channels=2; pacmd set-default-sink jack_out",shell=True)
    except:
        log.exception("Error configuring pulseaudio")

def ensureConnections():
    "Auto restore connections in the connection list"
    for i in allConnections:
        try:
           allConnections[i].reconnect()
        except:
            print(traceback.format_exc)

import weakref
allConnections=weakref.WeakValueDictionary()

activeConnections=weakref.WeakValueDictionary()


class MonoAirwire():
    """Represents a connection that should always exist as long as there
    is a reference to this object. You can also enable and disable it with 
    the connect() and disconnect() functions.
    
    They start out in the connected state
    """
    def __init__(self, name, orig, to):
        self.orig=orig
        self.to = to
        self.name = name
        self.active = True

    def disconnect(self):
        self.disconnected = True
        try:
            del allConnections[self.name]
        except:
            pass
        try:
            x = jackclient.get_port_by_name(self.orig)
            if x.is_connected_to(self.to):
                x.disconnect(self.to)
                del activeConnections[self.orig,self.to]
        except:
            pass

    def __del__(self):
        x = jackclient.get_port_by_name(self.orig)
        if x.is_connected_to(self.to):
            x.disconnect(self.to)

    def connect(self):
        allConnections[self.name]= self
        self.connected=True
        self.reconnect()

    def reconnect(self):
        try:
            x = jackclient.get_port_by_name(self.orig)
            if not x.is_connected_to(self.to):
                x.connect(self.to)
                activeConnections[self.orig, self.to]=self
        except:
            pass

class Effect():
    def __init__(self, effectype):
        pass
        #Todo, create the gstreamer element 

class MultichannelAirwire(MonoAirwire):

    def __init__(self, f,t):
        if isinstance(f,ChannelStrip):
            self.orig = weakref.ref(f)
        else:
            self.orig = f
        if isinstance(t,ChannelStrip):
            self.to = weakref.ref(to)
        else:
            self.to = to

    def _getEndpoints(self):
        if isinstance(self.orig,weakref.ref):
            f =self.orig()
        else:
            f = self.orig
        if not f:
            return None,None
        
        if isinstance(self.to,weakref.ref):
            t =self.to()
        else:
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

        if isinstance(f,ChannelStrip):
            outPorts = jackclient.get_ports(f.name+":output*",is_output=True,is_audio=True)
        else:
            outPorts = jackclient.get_ports(f+":*",is_output=True,is_audio=True)
        
        if isinstance(t,ChannelStrip):
            t=t.name
        inPorts = jackclient.get_ports(t+":*",is_input=True,is_audio=True)

        #Connect all the ports
        for i in zip(outPorts,inPorts):
            if not i[0].is_connected_to(i[1]):
                i[0].connect(i[1])
                activeConnections[i[0],i[1]]=self

    def disconnect(self):
        f,t=self._getEndpoints()
        if not f:
            return

        if isinstance(f,ChannelStrip):
            outPorts = jackclient.get_ports(f.name+":output*",is_output=True,is_audio=True)
        else:
            outPorts = jackclient.get_ports(f+":*",is_output=True,is_audio=True)
        
        if isinstance(t,ChannelStrip):
            t=t.name
        inPorts = jackclient.get_ports(t+":*",is_input=True,is_audio=True)

        #Connect all the ports
        for i in zip(outPorts,inPorts):
            if i[0].is_connected_to(i[1]):
                i[0].disconnect(i[1])
                try:
                    del activeConnections[i[0],i[1]]
                except KeyError:
                    pass

    def __del__(self):
        self.disconnect()


def CombiningAirwire(MultichannelAirwire):
    def reconnect(self):
        """Connects the outputs of channel strip f to the inputs of t, one to one, until
        you run out of ports. 
        
        Note that channel strips only have the main inputs but can have sends,
        so we have to distinguish them in the regex.
        """
        if not self.active:
            return
        f,t=self._getEndpoints()
        if not f:
            return

        if isinstance(f,ChannelStrip):
            outPorts = jackclient.get_ports(f.name+":output*",is_output=True,is_audio=True)
        else:
            outPorts = jackclient.get_ports(f+":*",is_output=True,is_audio=True)
    

        inPort = jackclient.get_port(t)
        if not inPort:
            return


        #Connect all the ports
        for i in outPorts:
            if i.is_connected_to(inPort):
                i.disconnect(inPort)
                try:
                    del activeConnections[i,inPort]
                except KeyError:
                    pass


    def disconnect(self):
        f,t=self._getEndpoints()
        if not f:
            return

        if isinstance(f,ChannelStrip):
            outPorts = jackclient.get_ports(f.name+":output*",is_output=True,is_audio=True)
        else:
            outPorts = jackclient.get_ports(f+":*",is_output=True,is_audio=True)
    

        inPort = jackclient.get_port(t)
        if not inPort:
            return


        #Disconnect all the ports
        for i in outPorts:
            if i.is_connected_to(inPort):
                i.disconnect(inPort)
                try:
                    del activeConnections[i,inPort]
                except KeyError:
                    pass

def Airwire(f,t):
    if ":" in f:
        if not ":" in t:
            raise ValueError("MultichannelAirwire to single channel makes no sense")
            #Can't connect multichannel to single channel
        return MultichannelAirwire(f,t)
    else:
        return MonoAirwire(f,t)

def onPortConnect(a,b,disconnected):
    #Whem things are manually disconnected we don't
    #Want to always reconnect every time
    if disconnected:
        i = (a.name,b.name)
        #Try to stop whatever airwire or set therof
        #from remaking the connection
        if i in activeConnections:
            try:
                activeConnections[i].active=False
                del allConnections[i]
                del activeConnections[i]
            except:
                pass

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

oldi,oldo,oldnames  = None,None,{}



alsa_in_instances={}
alsa_out_instances ={}

failcards = {}

#The options we use to tune alsa_in and alsa_out
#so they don't sound horrid
iooptions=["-p", "128","-m:", "64", "-q","1"]

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

  

lock=threading.Lock()

def try_stop(p):
    try:
        p.terminate()
    except:
        pass
def closeAlsaProcess(i, x):
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
    x=x.replace("Lpe","").replace("-","")
    return x

def cardsfromregex(m, cards,usednames = []):
    """Given the regex matches from arecord or aplay, match them up to the actual 
    devices and give them memorable aliases"""

    d = {}

    #Why sort? We need consistent ordering so that our conflict resolution
    #has the absolute most possible consistency
    m= sorted(m)
    for i in m:
        #We generate a name that contains both the device path and subdevice
        generatedName = cards[i[0]]+"."+i[2]

        numberstring = compressnumbers(cards[i[0]])

        h = memorableHash(cards[i[0]]+":"+i[2])[:12]

        n = cleanupstring(i[3])
        jackname =n+'_'+h
        jackname+=numberstring
        jackname=jackname[:28]

        #If there's a collision, we're going to redo everything
        #This of course will mean we're going back to 
        while (jackname in d) or jackname in usednames:
            h = memorableHash(jackname+cards[i[0]]+":"+i[2])[:12]
            n = cleanupstring(i[3])
            jackname =n+'_'+h
            jackname+=numberstring
            jackname=jackname[:28]
        
        jackname=jackname.replace('Generic','')
        jackname=jackname.replace('Device','')

    
        longname = n.replace('Generic','')+"_"+memorableHash(cards[i[0]]+":"+i[2],num=4,caps=True)+"_"+cards[i[0]]
        
        try:
            d[jackname]  = ("hw:"+i[0]+","+i[2], cards[i[0]], (int(i[0]), int(i[2])), longname)
        except KeyError:
            d[jackname] = ("hw:"+i[0]+","+i[2], cards[i[0]], (int(i[0]), int(i[2])), longname)
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


    x = subprocess.check_output(['aplay','-l'],stderr=subprocess.DEVNULL).decode("utf8")
    #Groups are cardnumber, cardname, subdevice, longname
    sd = re.findall(r"card (\d+): (\w*)\s\[.*?\], device (\d*): (.*?)\s+\[.*?]",x)

    outputs= cardsfromregex(sd,cards)
   

    x = subprocess.check_output(['arecord','-l'],stderr=subprocess.DEVNULL).decode("utf8")
    #Groups are cardnumber, cardname, subdevice, longname
    sd = re.findall(r"card (\d+): (\w*)\s\[.*?\], device (\d*): (.*?)\s+\[.*?]",x)
    inputs=cardsfromregex(sd,cards)

    names_to_jacknames = {}

    for i in inputs:
        names_to_jacknames[inputs[i][3]] = i+"i"
    for i in outputs:
        names_to_jacknames[outputs[i][3]] = i+"o"
    return inputs,outputs,names_to_jacknames


import util 
eff_wordlist = util.eff_wordlist

def memorableHash(x, num=1, separator="",caps=False):
    "Use the diceware list to encode a hash. Not meant to be secure."
    o = ""

    if isinstance(x, str):
        x = x.encode("utf8")
    for i in range(num):
        while 1:
            x = hashlib.sha256(x).digest()
            n = struct.unpack("<Q",x[:8])[0]%len(eff_wordlist)
            e = eff_wordlist[n]
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
    try:
        subprocess.check_call(['killall','jackd'])
    except:
        pass
    try:
        subprocess.check_call(['killall','alsa_in'])
    except:
        pass
    try:
        subprocess.check_call(['killall','alsa_out'])
    except:
        pass

jackp = None
def startJack():
    #Start the JACK server.
    global jackp

    if not jackp or not jackp.poll()==None:
        try:
            subprocess.check_call(['pulseaudio','-k'])
        except:
            pass
        jackp =subprocess.Popen("jackd --realtime -d alsa -d hw:0,0 -p 256 -n 3",shell=True,stdin=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdout=subprocess.DEVNULL)    



def startManagingJack():
    global jackclient
    atexit.register(cleanup)
    stopJack()
    startJack()
    for i in range(10):
        try:
            jackclient = jack.Client("Overseer")
        except:
            if i>9:
                continue
            raise
    setupPulse()



portDisplayNames = {}
portJackNames = {}

def handleManagedSoundcards():
    "Make sure that all of our alsa_in and out instances are working as they should be."
    global oldi
    global oldo
    global portDisplayNames
    global portJackNames

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
                    log.error("Error in output "+ i +(x+e).decode("utf8"))
                    closeAlsaProcess(i, alsa_out_instances[i])
                    tr.append(i)
                    #We have to delete the busy stuff but we can
                    #retry later
                    if b"busy" in (x+e):
                        toretry_out[i]=time.monotonic()
                    
                    if b"No such" in (x+e):
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
                    log.error("Error in "+ i +(x+e).decode("utf8"))
                    closeAlsaProcess(i, alsa_in_instances[i])   
                    tr.append(i)
                    if b"busy" in (x+e):
                        toretry_in[i]=time.monotonic()
                    
                    if b"No such" in (x+e):
                        toretry_in[i]=time.monotonic()  
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
        inp,op,names = listSoundCardsByPersistentName()
        #This is how we avoid constantky retrying to connect the same few
        #clients that fail, which might make a bad periodic click that nobody
        #wants to hear.
        if (inp,op)==(oldi,oldo):

            #However some things we need to retry.
            #Device or resource busy being the main one
            for i in inp:
                if i in toretry_in:
                    if time.monotonic() < toretry_in[i]+5:
                        continue
                    del toretry_in[i]
                    if not i in alsa_in_instances:
                        x = subprocess.Popen(["alsa_in"]+iooptions+["-d", inp[i][0], "-j",i+"i"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                        alsa_in_instances[i]=x
                        log.info("Added "+i+"i at"+inp[i][1])

            for i in op:
                if i in toretry_out:
                    if time.monotonic() < toretry_out[i]+5:
                        continue
                    del toretry_out[i]
                    if not i in alsa_out_instances:
                        x = subprocess.Popen(["alsa_out"]+iooptions+["-d", op[i][0], "-j",i+"o"]+iooptions,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                        alsa_out_instances[i]=x
                        log.info("Added "+i+"o")
            return
            
        oldi,oldo,oldnames =inp,op,names
        portDisplayNames = names
        portJackNames = {names[i]:i for i in names}

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
                del alsa_out_instances[i]

            tr =[]
            for i in alsa_in_instances:
                if not i in inp:
                    tr.append(i)
            for i in tr:
                log.warning("Removed "+i+"i because the card was removed")
                del alsa_in_instances[i]
        except:
            log.exception("Exception in loop")






startManagingJack()

while 1:
    handleManagedSoundcards()
    ensureConnections()
