## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code through the web UI
__data__="""
continual: true
disabled: false
enable: true
once: true
priority: realtime
rate-limit: 0.0
resource-timestamp: 1566264981246449
resource-type: event
versions: {}

"""

__trigger__='True'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolutio n
    __doc__=''
    import time,array,random,weakref, os,threading,uuid,logging,serial,traceback,yaml,copy,json,math,struct,socket,src
    from decimal import Decimal
    from tinytag import TinyTag
    
    
    
    logger = logging.getLogger("system.chandler")
    
    import numpy
    import hashlib
    import base64
    float=float
    abs=abs
    int=int
    max=max
    min=min
    
    allowedCueNameSpecials = '_~.'
    
    from src.scriptbindings import ChandlerScriptContext,getFunctionInfo
    
    rootContext = ChandlerScriptContext()
    
    def mapUniverse(u):
        if not u.startswith("@"):
            return u
        
        try:
            x = module.fixtures[u[1:]]()
            if not x:
                return None
        except KeyError:
            return None
        return x.universe
    
    def mapChannel(u,c):
        if not u.startswith("@"):
            if isinstance(c,str):
                universe=module.universes.get(u,None)
                if universe:
                    c= universe.channelNames.get(c,None)
                    if not c:
                        return None
                    else:
                        return universe,c
            else:
                return u,c
        try:
            f = module.fixtures[u[1:]]()
            if not f:
                return None
        except KeyError:
            return None
        x=f.assignment
        if not x:
            return
        return x[0], x[1]+f.nameToOffset[c]
    
    
    def fnToCueName(fn):
        fn=fn.split(".")[0]
        fn=fn.replace("-","_")
        fn=fn.replace("_"," ")
        fn = fn.replace(":"," ")
        for i in r"""\~!@#$%^&*()+`-=[]\{}|;':"./,<>?""":
            if not i in allowedCueNameSpecials:
                fn=fn.replace(i,"")
        return fn
    
    
    #when the last time we logged an error, so we can ratelimit
    lastSysloggedError =0
    
    def rl_log_exc(m):
        print(m)
        global lastSysloggedError
        if lastSysloggedError< time.monotonic()-5*60:
            logging.exception(m)
        lastSysloggedError= time.monotonic()
    
    module.boards = []
    
    universesLock = threading.RLock()
    #in the del and init we copy data from this slow weakrefd thing to a fast not-weakref thing.
    module.universes=weakref.WeakValueDictionary()
    module.fastUniverses = {}
    module.lock = threading.RLock()
    boardsListLock = threading.Lock()
    
    module._activeScenes = []
    module.activeScenes = []
    
    #Index Cues by codes that we use to jump to them. This is a dict of lists of cues with that short code,
    shortcut_codes = {}
    
    module.runningTracks = weakref.WeakValueDictionary()
    
    module.scenes = weakref.WeakValueDictionary()
    module.scenes_by_name = weakref.WeakValueDictionary()
    
    try:
        import pavillion
    except:
        pass
    
    
    def parseBinding(b):
        """
        Parse a binding like foo: bar, baz, "baz bar" into (foo,(bar,baz,baz bar))
        Quote marks and escapes work like unix shell.
        """
        b=b.replace("\t"," ")
        trigger, binding = b.split(":",1)
        c =''
        x = []
        esc = False
        q = False
        for i in binding:
            if esc:
                esc = False
                c+=i
            elif i=='\\':
                esc = True
            elif q and not i=='"':
                c+=i
            elif i==' ':
                x.append(c)
                c = ''
            elif i=='"':
                q = not q
            else:
                c+=i
        z = [i for i in x if i]
        return trigger.strip(), [i.strip() for i in (z+([c] if c else []))]
    
    
    def parseCommandBindings(cmd):
        l = []
        for i in cmd.split("\n"):
            if not i:
                continue
            x = parseBinding(i)
    
            l.append([x[0],x[1]])
        return l
    
    
    
    def gotoCommand(scene, cue):
        "Triggers a scene to go to a cue"
        module.scenes_by_name[scene].gotoCue(cue)
        return True
    
    
    def setAlphaCommand(scene, alpha):
        "Set the alpha value of a scene"
        module.scenes_by_name[scene].setAlpha(float(alpha))
        return True
    
    def ifCueCommand(scene, cue):
        "True if the scene is running that cue"
        return True if module.scenes_by_name[scene].active and module.scenes_by_name[scene].cue.name == cue else None
    
    
    def eventCommand(scene="=$scene", ev="DummyEvent", value=True):
        "Send an event to a scene"
        module.scenes_by_name[scene].event(ev,value)
        return True
    
    
    rootContext.commands['goto']=gotoCommand
    rootContext.commands['setAlpha']=setAlphaCommand
    rootContext.commands['ifCue']=ifCueCommand
    rootContext.commands['sendEvent']=eventCommand
    
    
    def listsoundfolder(path):
        soundfolders = getSoundFolders()
    
        if not path.endswith("/"):
            path = path+"/"
            
        if not path and not name:
            return [[i+('/' if not i.endswith('/') else '') for i in soundfolders],[]]
    
        #If it's not one of the sound folders return for security reasons
        match = False
        for i in soundfolders:
            if not i.endswith("/"):
                i = i+"/"
            if path.startswith(i):
                match =True
        if not match:
            return [[i+('/' if not i.endswith('/') else '') for i in soundfolders],[]]
            
        if not os.path.exists(path):
            return [[],[]]
    
        x = os.listdir(path)
        return(
            sorted([ os.path.join(path,i)+'/' for i in x if os.path.isdir(os.path.join(path,i))]),
            sorted([i for i in x if os.path.isfile(os.path.join(path,i))])
        ) 
    
    musicLocation = os.path.join(kaithem.misc.vardir,"chandler", "music")
    
    if not os.path.exists(musicLocation):
        try:
            os.mkdir(musicLocation)
        except:
            pass
    
    def searchPaths(s, paths):
        if not len(s)>2:
            return []
    
        words = [i.strip() for i in s.lower().split(" ")]
    
        results = []
        path = paths[:]
        paths.append(musicLocation)
    
        for path in paths:
            if not path[-1]=="/":
                path=path+'/'
    
            for dir, dirs, files in os.walk(path):
                relpath = dir[len(path):]
                for i in files:
                    match = True
                    for j in words:
                        if not j in i.lower():
                            if not j in relpath.lower():
                                match=False
                    if not match:
                        continue
                    results.append((path,os.path.join(relpath,i)))
        return results
    
    
    
    def getSerPorts():
        try:
            import serial.tools.list_ports
            if os.path.exists("/dev/serial/by-id"):
                return [os.path.join('/dev/serial/by-id',i) for i in os.listdir("/dev/serial/by-id")]
            else:
                return [i.device for i in serial.tools.list_ports.comports()]
        except Exception as e:
            return [str(e)]
    
    
    
       
    def getSoundFolders():
        soundfolders = [i.strip() for i in kaithem.registry.get("lighting/soundfolders",[])]
        soundfolders.append(os.path.join(src.directories.datadir,"sounds"))
        soundfolders.append(musicLocation)
        soundfolders+=[i for i in kaithem.sound.directories if not i.startswith("__")]
        return soundfolders
    
    
    
    def disallow_special(s,allow=''):
        for i in '[]{}()!@#$%^&*()<>,./;\':"-=_+\\|`~?\r\n\t':
            if i in s and not i in allow:
                raise ValueError("Special char "+i+" not allowed in this context(full str starts with "+s[:100]+")")
    
    #These aren't used or tested yet, but should be enabled soon so we can save large amounts of data
    def writeCue(fobj, cue):
        num = s = str((Decimal(cue.number)/1000).quantize(Decimal("0.001")))
        fobj.write("\n[cue "+num+']\n')
        fobj.write("name= "+str(cue.name)+'\n')
        fobj.write("length= "+str(cue.length)+'\n')
        fobj.write("fadein= "+str(cue.fadein)+'\n')
        fobj.write("shortcut= "+ shortcut+'\n')
        fobj.write("track= "+('1' if cue.track else '0')+'\n')
    
        for i in cue.values:
            x = sorted(list[cue.values[i].keys()])
            while x:
                fobj.write("\nchannels."+i+"= ")
                l = None
                ls = []
                for j in x[:100]:
                    if j==l:
                        ls.append(str(cue.values[i][j])[:6])
                    else:
                        ls.append(j+':'+str(cue.values[i][j])[:6])
                fobj.write(','.join(ls))
                x=x[100:]
        fobj.write("\n")
    
    def writeScene(fobj, scene):
        fobj.write("\n[scene "+str(scene.name)+']\n')
        fobj.write("priority= "+str(scene.priority)+'\n')
        fobj.write("blend= "+str(scene.blend)+'\n')
        fobj.write("blend= "+str(id)+'\n')
        fobj.write("alpha= "+('1' if scene.defaultalpha else '0')+'\n')
        fobj.write("active= "+('1' if scene.defaultActive else '0')+'\n')
        fobj.write("backtrack= "+('1' if scene.backtrack else '0')+'\n')
    
        for i in scene.blendArgs:
            fobj.write('\n'+'blend.'+i+"= "+json.dumps(scene.blendArgs[i]))
    
        for i in scene.cues:
            writeCue(fobj,scene.cues[i])
    
    
    
    
    
    
    def pollsounds():
        for i in module.activeScenes:
            #If the cuelen isn't 0 it means we are using the newer version that supports randomizing lengths.
            #We keep this in case we get a sound format we can'r read the length of in advance
            if i.cuelen == 0:
                if i.cue.sound and i.cue.rel_length:
                    if not kaithem.sound.isPlaying(str(i.id)) and not i.sound_end:
                        i.sound_end = module.timefunc()
                    if i.sound_end and (module.timefunc()-i.sound_end>(i.cue.length*i.bpm)):
                        i.nextCue()
    
    class ObjPlugin():
        pass
    kaithem.chandler = ObjPlugin()
    
    module.controlValues = weakref.WeakValueDictionary()
    
    
    
    
    
    def number_to_shortcut(number):
        s = str((Decimal(number)/1000).quantize(Decimal("0.001")))
        #https://stackoverflow.com/questions/11227620/drop-trailing-zeros-from-decimal
        s = s.rstrip('0').rstrip('.') if '.' in s else s
        return s
    
    
    
    def getControlValue(cv,default=None):
        "Return numbers as is, or resolve values in the form of Universe:3 to the current value from that universe "
        if isinstance(cv,(float,int)):
            return cv
        else:
            try:
                cv = cv.split(":")
                x = cv[1].split("*")
                if len(x)> 1:
                    multiplier = float(x[1])
                else:
                    multiplier = 1.0
                return module.universes[cv[0]].values[int(x[0])]*multiplier
            except Exception as e:
                if not default is None:
                    return default
                raise
    
    fixtureslock = threading.Lock()
    module.fixtures ={}
    fixtureschanged = {}
    
    def unpack_np_vals(v):
        "Given a set of dicts that might contain either lists or np arrays, convert to normal lists of numbers"
        return {j:[float(k) for k in v[j]] for j in v}
    
    class Fixture():
        def __init__(self,name,channels=None):
            """Represents a contiguous range of channels each with a defined role in one universe.
               Each channel must be described by a [name, type, [arguments]] list, where type is one of:
    
               red
               green
               blue
               value
               dim
               custom
               fine
    
               The name must be unique per-fixture.
               If a channel has the type "fine" it will be interpreted as the fine value of
               the immediately preceding coarse channel, and should automatically get its value from the fractional part.
               If the coarse channel is not the immediate preceding channel, use the first argument to specify the number of the coarse channel,
               with 0 being the fixture's first channel.        
            """
            if channels:
                self.channels = json.loads(json.dumps(channels))
            else:
                self.channels = None
            self.universe = None
            self.startAddress = 0
            self.assignment = None
            disallow_special(name)
    
            self.nameToOffset = {}
    
            #Used for looking up channel by name
            for i in range(len(channels)):
                self.nameToOffset[channels[i][0]]= i
    
    
            with module.lock:
                with fixtureslock:
                    if name in module.fixtures:
                        raise ValueError("Name in Use")
                    else:
                        module.fixtures[name]=weakref.ref(self)
                        self.name=name
        
        def getChannelByName(self,name):
            if self.startAddress:
                return self
                        
        def __del__(self):
            with fixtureslock:
                del module.fixtures[self.name]
                
            ID=id(self)
            def f():
                try:
                    if id(module.fixtures[self.name]())==id(ID):
                        self.assign(None,None)
                        self.rm()
                except:
                    pass
            kaithem.misc.do(f)
    
        def rm(self):
            try:
                del module.fixtures[self.name]
            except:
                pass
    
        def assign(self,universe, channel):
            with module.lock:
                self.assignment=universe, channel
    
                if self.universe and self.startAddress and (self.universe in module.universes):
                    #Delete current assignments
                    for i in range(self.startAddress,self.startAddress+len(self.channels)):
                        if i in module.universes[self.universe].channels:
                            if module.universes[self.universe].channels[i] is self:
                                del module.universes[self.universe].channels[i]
                            else:
                                print("Unexpected channel data corruption",universe, i, module.universes[self.universe].channels[i])
    
                self.universe = universe
                self.startAddress= channel
    
                global fixtureschanged
                fixtureschanged = {}
    
                if not universe in module.universes:
                        return
                module.universes[universe].channelsChanged()
    
                if not channel:
                    return
                #2 separate loops, first is just to check, so that we don't have half-completed stuff
                for i in range(channel,channel+len(self.channels)):
                    if i in module.universes[universe].channels:
                        if module.universes[universe].channels[i]:
                            raise ValueError("channel " +str(i)+ " of " +self.name+ " would overlap with "+module.universes[universe].channels[i].name)
    
                for i in range(channel,channel+len(self.channels)):
                    module.universes[universe].channels[i]= self
    
    
    class Universe():
        "Represents a lighting universe, similar to a DMX universe, but is not limited to DMX. "
        def __init__(self, name,count=512,number=0):
            for i in ":/[]()*\\`~!@#$%^&*=+|{}'\";<>.,":
                if i in name:
                    raise ValueError("Name cannot contain special characters except _")
            self.name = name
    
            #Let subclasses set these
            if not hasattr(self,"status"):
                self.status = "normal"
            if not hasattr(self,"ok"):
                self.ok = True
    
            #Represents the telemetry data back from the physical device of this universe.
            self.telemetry = {}
    
            #Dict of all board ids that have already pushed a status update
            self.statusChanged = {}
            self.channels = {}
    
            #Maps names to numbers, mostly for tagpoint universes.
            self.channelNames={}
    
            self.groups ={}
            self.values = numpy.array([0.0]*count,dtype="f4")
            self.count = count
            #Maps fine channel numbers to coarse channel numbers
            self.fine_channels = {}
            #Used for the caching. It's the layer we want to save as the background state before we apply.
            #Calculated as either the last scene rendered in the stack or the first scene that requests a rerender that affects the universe
            self.save_before_layer = (0,0)
            #Reset in pre_render, indicates if we've not rendered a layer that we think is going to change soon
            #so far in this frame
            self.all_static = True
            with universesLock:
                if name in module.universes:
                    logger.warning("Replacing universe "+name)
                    #Todo: just close the old one right here
                    raise ValueError("Name "+name+ " is taken")
                module.universes[name] =self
                try:
                    module.fastUniverses = {i:module.universes[i] for i in module.universes}
                except IterationError:
                    module.fastUniverses=module.universes
                        
            #flag to apply all scenes, even ones not marked as neding rerender
            self.full_rerender = False
            
            #The priority, started of the top layer layer that's been applied to this scene.
            self.top_layer= (0,0)
    
            #This is the priority, started of the "saved" layer that's been cached so we don't
            #Have to rerender it or anything below it.
            self.prerendered_layer= (0,0)
    
    
            #A copy of the state of the universe just after prerendered_layer was rendered, so we can go back
            #and start from there without rerendering lower layers.
            self.prerendered_data= [0.0]*count
            
            #Maybe there might be an iteration error. But it's just a GUI convienence that
            #A simple refresh solves, so ignore it.
            try:
                for i in module.boards:
                    i().pushUniverses()
            except Exception as e:
                print(e)
            
            #Deal with fixtures in this universe that aren't actually attached to this object yet.
            for i in range(0,5):
                try:
                    with fixtureslock:
                        for i in module.fixtures:
                            f = module.fixtures[i]()
                            if not f:
                                continue
                            if f.universe==self.name:
                                f.assign(f.universe,f.startAddress)
                except RuntimeError:
                    #Should there be some kind of dict changed size problem, retry
                    time.sleep(0.1)
    
            self.refresh_scenes()
    
    
        def __del__(self):
            self.close()
    
        def close(self):
            with universesLock:
                #Don't delete the object that replaced this
                if self.name in module.universes and (module.universes[self.name] is self):
                    del module.universes[self.name]
    
                try:
                    module.fastUniverses = {i:module.universes[i] for i in module.universes}
                except IterationError:
                    module.fastUniverses=module.universes
                
                def alreadyClosed(*a,**k):
                    raise RuntimeError("This universe has been stopped, possibly because it was replaced wih a newer one")
    
                self.onFrame = alreadyClosed
                self.setStatus= alreadyClosed
                self.refresh_scenes=alreadyClosed
                self.reset_to_cache = alreadyClosed
                self.reset = alreadyClosed
                self.preFrame= alreadyClosed
                self.save_prerendered=alreadyClosed
    
        def setStatus(self,s,ok):
            "Set the status shown in the gui. ok is a bool value that indicates if the object is able to transmit data to the fixtures"
            #avoid pushing unneded statuses
            if (self.status == s) and (self.ok == ok):
                return
            self.status = s
            self.ok = ok
            self.statusChanged = {}
    
        def refresh_scenes(self):
            """Stop and restart all active scenes, because some caches might need to be updated
                when a new universes is added
            """
            with module.lock:
                for i in module.activeScenes:
                    #Attempt to restart all scenes.
                    #Try to put them back in the same state
                    #A lot of things are written assuming the list stays constant,
                    #this is needed for refreshing.
                    x = i.started
                    y = i.enteredCue
                    i.stop()
                    i.go()
                    i.render()
                    i.started = x
                    i.enteredCue = y
    
        def __del__(self):
            #Do as little as possible in the undefined __del__ thread
            try:
                kaithem.misc.do(self.refresh_scenes)
            #Eliminate the nuisance error
            except NameError:
                pass
        def channelsChanged(self):
            "Call this when fixtures are added, moved, or modified."
            with module.lock:
                self.fine_channels = {}
                for i in self.channels:
                    fixture = self.channels[i]
                    if not fixture.startAddress:
                        continue
                    data = fixture.channels[i-fixture.startAddress]
                    if (data[1]== "fine") and (i>1):
                        if len(data==2):
                            self.fine_channels[i]= i-1
                        else:
                            self.fine_channels[i]= fixture.startAddress+data[2]
        
        def reset_to_cache(self):
            "Remove all changes since the prerendered layer."
            self.values = copy.deepcopy(self.prerendered_data)
            self.top_layer = self.prerendered_layer
        
        def save_prerendered(self, p, s):
            "Save this layer as the cached layer. Called in the render functions"
            self.prerendered_layer = (p,s)
            self.prerendered_data  = copy.deepcopy(self.values)
        
        def reset(self):
            "Reset all values to 0 including the prerendered data"
            self.prerendered_layer = (0,0)
            self.values = numpy.array([0.0]*self.count,dtype="f4")
            self.top_layer = (0,0)
    
        
        def preFrame(self):
            "Frame preprocessor, uses fixture-specific info, generally only called under lock"
            #Assign fine channels their value based on the coarse channel
            for i in self.fine_channels:
                self.values[i] = (self.values[self.fine_channels[i]]%1)*255
    
    
        def onFrame(self):
            pass
    
    def message(data):
        "An enttec DMX message from a set of values"
        data = numpy.maximum(numpy.minimum(data,255),0)
        data = data.astype(numpy.uint8)
        data = data.tobytes()[:512]
        return (b'\x7e\x06'+struct.pack('<H',len(data))+data+b'\xe7')
    
    module.Universe = Universe
    
    class EnttecUniverse(Universe):
        #Thanks to https://github.com/c0z3n/pySimpleDMX
        #I didn't actually use the code, but it was a very useful resouurce
        #For protocol documentation.
        def __init__(self,name,channels=128,portname="",framerate=44,number=0):
            self.ok = False
            self.number=number
            self.status = "Disconnect"
            self.statusChanged = {}
            #Sender needs the values to be there for setup
            self.values = numpy.array([0.0]*channels,dtype="f4")
            self.sender = DMXSender(self,portname,framerate)
            self.sender.connect()
            
            Universe.__init__(self,name,channels)
    
    
        def onFrame(self):
            data = message(self.values)
            self.sender.onFrame(data)
    
        def __del__(self):
            #Stop the thread when this gets deleted
            self.sender.onFrame(None)
    
    module.EnttecUniverse_dbg= weakref.WeakValueDictionary()
    
    class DMXSender():
        """This object is used by the universe object to send data to the enttec adapter.
            It runs in it's own thread because the frame rate might have nothing to do with
            the rate at which the data actually gets rendered.
        """
        def __init__(self,universe,port,framerate):
            module.EnttecUniverse_dbg[str(module.timefunc())]= self
            self.frame = threading.Event()
            self.universe= weakref.ref(universe)
            self.data = message(universe.values)
            self.thread = threading.Thread(target =self.run)
            self.thread.daemon = True
            self.thread.name = "DMXSenderThread_"+self.thread.name
            self.portname = port
            self.framerate = float(framerate)
            self.lock = threading.Lock()
            self.port = None
            self.connect()
            self.thread.start()
    
    
        def setStatus(self,s,ok):
            try:
                self.universe().setStatus(s,ok)
            except:
                pass
                
        def connect(self):
            #Different status message first time
            try:
                self.reconnect()
            except Exception as e:
                self.setStatus('Could not connect, '+str(e)[:100]+'...',False)
    
    
        def reconnect(self):
            "Try to reconnect to the adapter"
            try:
                import serial
                if not self.portname:
                    import serial.tools.list_ports
    
                    p = serial.tools.list_ports.comports()
                    if p:
                        if len(p)>1:
                            self.setStatus('More than one device found, refusing to guess. Please specify a device.',False)
                            return
                        else:
                            p =p[0].device
                    else:
                        self.setStatus('No device found',False)
                        return
                else:
                    p = self.portname
                time.sleep(0.1)
                try:
                    self.port.close()
                except:
                    pass
                self.port = serial.Serial(p,57600, timeout=1.0, write_timeout=1.0)
    
                #This is a flush to try to re-sync recievers that don't have any kind of time out detection
                #We do this by sending a frame where each value is the packet end code,
                #Hoping that it lines up with the end of whatever unfinished data we don't know about.
                self.setStatus('Found port, writing sync data',True)
    
                for i in range(0,8):
                    self.port.write(message(numpy.array([231]*120)))
                    time.sleep(0.05)
                self.port.write(message(numpy.zeros(max(128,len(self.universe().values)))))
                time.sleep(0.1)
                self.port.read(self.port.inWaiting())
                time.sleep(0.05)
                self.port.write(self.data)
                self.setStatus('connected to '+p,True)
            except Exception as e:
                try:
                    self.setStatus('disconnected, '+str(e)[:100]+'...',False)
                except:
                    pass
    
        def run(self):
            while 1:
                try:
                    s = module.timefunc()
                    self.port.read(self.port.inWaiting())
                    x =self.frame.wait(1)
                    if not x:
                        continue
                    with self.lock:
                        if self.data is None:
                            try:
                                self.port.close()
                            except:
                                pass
                            return
                        self.port.write(self.data)
                        self.frame.clear()
                    time.sleep(max(((1.0/self.framerate)-(module.timefunc()-s)), 0))
                except Exception as e:
                    try:
                        self.port.close()
                    except:
                        pass
                    try:
                        if self.data is None:
                            return
                        if self.port:
                            self.setStatus('disconnected, '+str(e)[:100]+'...',False)
                        self.port=None
                        #reconnect is designed not to raise Exceptions, so if there's0
                        #an error here it's probably because the whole scope is being cleaned
                        time.sleep(1)
                        self.reconnect()
                        time.sleep(1)
                        self.reconnect()
                        time.sleep(1)
                    except:
                        return
    
    
        def onFrame(self,data):
            with self.lock:
                self.data = data
                self.frame.set()
    
    class ArtNetUniverse(Universe):
        def __init__(self,name,channels=128,address="255.255.255.255:6454",framerate=44,number=0):
            self.ok = True
            self.status = "OK"
            self.number=number
            self.statusChanged = {}
    
            x = address.split("://")
            if len(x)>1:
                scheme = x[0]
            else:
                scheme=''
            
            addr,port = x[-1].split(":")
            port = int(port)
    
           
    
            #Sender needs the values to be there for setup
    
            #Channel 0 is a dummy to make math easier.
            self.values = numpy.array([0.0]*(channels+1),dtype="f4")
            self.sender = ArtNetSender(self,addr,port,framerate,scheme)
            
            Universe.__init__(self,name,channels)
    
    
        def onFrame(self):
            data = (self.values)
            self.sender.onFrame(data,None,self.number)
    
        def __del__(self):
            #Stop the thread when this gets deleted
            self.sender.onFrame(None)
    
    
    
    class TagpointUniverse(Universe):
        "Used for outputting lighting to Kaithem's internal Tagpoint system"
        def __init__(self,name,channels=128,tagpoints={},framerate=44,number=0):
            self.ok = True
            self.status = "OK"
            self.number=number
            self.statusChanged = {}
            self.tagpoints=tagpoints
            self.channelCount=channels
            
            self.claims = {}
    
            #Put a claim on all the tags
            for i in self.tagpoints:
                #One higher than default
                try:
                    self.claims[int(i)]= kaithem.tags[self.tagpoints[i]].claim(0,"Chandler_"+name, 51)
                except Exception as e:
                    self.status="error, "+i+" "+ str(e)
                    logger.exception("Error related to tag point "+i)
                    print(traceback.format_exc())
                    event("board.error",traceback.format_exc())
    
            #Sender needs the values to be there for setup
            self.values = numpy.array([0.0]*channels,dtype="f4")
            
            Universe.__init__(self,name,channels)
    
    
        def onFrame(self):
            for i in range(self.channelCount):
                if i in self.claims:
                    try:
                        x = float(self.values[i])
                        if x>-1:
                            self.claims[i].set(x)
                    except:
                        rl_log_exc("Error in tagpoint universe")
                        print(traceback.format_exc())
    
    
    
    
    module.EnttecUniverse_dbg= weakref.WeakValueDictionary()
    
    class ArtNetSender():
        """This object is used by the universe object to send data to the enttec adapter.
            It runs in it's own thread because the frame rate might have nothing to do with
            the rate at which the data actually gets rendered.
        """
        def __init__(self,universe,addr,port,framerate,scheme):
            module.EnttecUniverse_dbg[str(module.timefunc())]= self
            self.frame = threading.Event()
            self.scheme=scheme
    
    
            self.universe= weakref.ref(universe)
            self.data = False
            self.running = 1
            #The last telemetry we didn't ignore
            self.lastTelemetry = 0
            if self.scheme == "pavillion":
                def onBatteryStatus(v):
                    self.universe().telemetry['battery']=v
                    if self.lastTelemetry<(time.time()-10):
                        self.universe().statusChanged={}
                
                def onConnectionStatus(v):
                    self.universe().telemetry['rssi']=v
                    if self.lastTelemetry<(time.time()-10):
                        self.universe().statusChanged={}
                
                self.connectionTag = kaithem.tags["/devices/"+addr+".rssi"]
                self._oncs = onConnectionStatus
                self.connectionTag.subscribe(onConnectionStatus)
    
                self.batteryTag = kaithem.tags["/devices/"+addr+".battery"]
                self._onb = onBatteryStatus
                self.batteryTag.subscribe(onBatteryStatus)
                
            def run():
                import time, traceback
                interval = 1.1/self.framerate
    
                while self.running:
                    try:
                        s = time.time()
                        x =self.frame.wait(interval)
                        if not x:
                            interval= min(60, interval*1.3)
                        else:
                            interval = 1.5/self.framerate
                        if self.data is False:
                            continue
                        with self.lock:
                            if self.data is None:
                                print("Stopping ArtNet Sender for "+self.addr)
                                return
                            #Here we have the option to use a Pavillion device
                            if self.scheme=="pavillion":
                                try:
                                    addr=kaithem.devices[self.addr].data['address']
                                except:
                                    time.sleep(3)
                                    continue
                            else:
                                addr=self.addr
    
                            self.frame.clear()
                        try:
                            self.sock.sendto(self.data, (addr, self.port))
                        except:
                            time.sleep(5)
                            raise
    
                        time.sleep(max(((1.0/self.framerate)-(time.time()-s)), 0))
                    except Exception as e:
                        rl_log_exc("Error in artnet universe")
                        print(traceback.format_exc())
            self.thread = threading.Thread(target =run)
            self.thread.name = "ArtnetSenderThread_"+self.thread.name
    
            self.thread.daemon = True
            self.framerate = float(framerate)
            self.lock = threading.Lock()
    
    
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) 
            # Bind to the server address
            self.sock.bind(('',0))
            self.sock.settimeout(1)
    
            self.addr = addr
            self.port = port
            self.thread.start()
        
        def __del__(self):
            self.running=0
    
        def setStatus(self,s,ok):
            try:
                self.universe().setStatus(s,ok)
            except:
                pass
    
        def onFrame(self,data,physical = None, universe=0):
            with self.lock:
                if not (data is None):
                    #DMX starts at 1, don't send element 0 even though it exists.
                    p = b'Art-Net\x00\x00\x50\x00\x0E\0' + struct.pack("<BH", physical if not physical is None else universe, universe) +struct.pack(">H",len(data)) + (data.astype(numpy.uint8).tobytes()[1:])
                    self.data = p
                else:
                    self.data =data
                self.frame.set()
    
    def fixturesFromOldListStyle(l):
        "Convert fixtures from the older list of tuples style to the new dict style"
        return {i[0]:{'name':i[0],'type':i[1],'universe':i[2],'addr':i[3]} for i in l if len(i)==4}
    
    
    class DebugScriptContext(ChandlerScriptContext):
        def onVarSet(self,k, v):
            try:
                if k.startswith("pagevars."):
                    if isinstance(v, (str, int,float,bool)):
                        self.sceneObj().pageLink.send(["var", k.split(".",1)[1],v])
                else:
                    if not k=="_" and self.sceneObj().rerenderOnVarChange:
                        self.sceneObj().recalcCueVals()
                        self.sceneObj().rerender=True
    
            except:
                rl_log_exc("Error handling var set notification")
                print(traceback.format_exc())
    
            try:
                if not k.startswith("_"):
                    for i in module.boards:
                        if isinstance(v, (str, int,float,bool)):
                            i().link.send(['varchange',self.scene, k, v])
                        else:
                            i().link.send(['varchange',self.scene, k, "__PYTHONDATA__"])        
            except:
                rl_log_exc("Error handling var set notification")
                print(traceback.format_exc())
    
        def event(self,e,v=None):
            ChandlerScriptContext.event(self,e,v)
            try:
                for i in module.boards:
                    i().pushEv(e, self.sceneName,module.timefunc(),value=v)
            except:
                rl_log_exc("error handling event")
                print(traceback.format_exc())
            try:
                if not e=='poll':
                    if isinstance(v, (str, int,float,bool)):
                        self.sceneObj().pageLink.send(["evt", e,v])
            except:
                rl_log_exc("error handling event")
                print(traceback.format_exc())
        
        def onTimerChange(self,timer, run):
            self.sceneObj().runningTimers[timer]=run
            try:
                for i in module.boards:
                    i().link.send(['scenetimers',self.scene, self.sceneObj().runningTimers])
            except:
                rl_log_exc("Error handling timer set notification")
                print(traceback.format_exc())
    
    
    class ChandlerConsole():
        "Represents a web GUI board. Pretty much the whole GUI app is part of this class"
        def __init__(self, count=65536):
    
            self.newDataFunctions = []
    
            self.id = uuid.uuid4().hex
            self.link = kaithem.widget.APIWidget("api_link")
            self.link.require("users.chandler.admin")
            self.link.echo=False
            #mutable and immutable versions of the active scenes list.
            self._activeScenes = []
            self.activeScenes = []
            
            #This light board's scene memory, or the set of scenes 'owned' by this board.
            self.scenememory = {}
            
            self.ext_scenes = {}          
            
            self.count = count
            #Bound method weakref nonsense prevention
            self.onmsg = lambda x,y: self._onmsg(x,y)
            self.link.attach(self.onmsg)
            self.lock = threading.RLock()
            
            self.configuredUniverses = kaithem.registry.get("lighting/universes",{})
            self.universeObjs = {}
    
            self.fixtureClasses =kaithem.registry.get("lighting/fixturetypes",{})
            self.fixtureAssignments = {}
            self.fixtures ={}
            
            self.fixtureAssignments = kaithem.registry.get("lighting/fixtures",{})
    
            #This used to be a list of [name, fixturetype, startAddress] triples
            if not isinstance(self.fixtureAssignments,dict):
                self.fixtureAssignments = fixturesFromOldListStyle(self.fixtureAssignments)
            try:
                self.createUniverses()
            except Exception as e:
                logger.exception("Error creating universes")
                print(traceback.format_exc(6))
    
    
            #Old legacy scenes
            d = kaithem.registry.get("lighting/scenes",{})
    
    
            saveLocation = os.path.join(kaithem.misc.vardir,"chandler", "scenes")
            if os.path.isdir(saveLocation):
                for i in os.listdir(saveLocation):
                    fn = os.path.join(saveLocation,i)
    
                    if os.path.isfile(fn) and fn.endswith(".yaml"):
                        d[i[:-len('.yaml')]] = kaithem.persist.load(fn)
    
            self.loadDict(d)
            self.refreshFixtures()
            def f(self,*dummy):
                self.link.send(['soundoutputs',[i for i in kaithem.sound.outputs()]])
    
            self.callback_jackports = f
            kaithem.message.subscribe("/system/jack/newport/",f)
            kaithem.message.subscribe("/system/jack/delport/",f)
            
            #Use only for stuff in background threads, to avoid pileups that clog the
            #Whole worker pool
            self.guiSendLock = threading.Lock()
    
            #For logging ratelimiting
            self.lastLoggedGuiSendError =0
        
        def refreshFixtures(self):
            with module.lock:
                self.ferrs=''
                try:
                    for i in self.fixtures:
                        self.fixtures[i].assign(None,None)
                        self.fixtures[i].rm()
                except:
                   self.ferrs+= 'Error deleting old assignments:\n'+traceback.format_exc(2)
                try:
                    del i
                except:
                    pass
                    
                self.fixtures = {}
    
                for i in self.fixtureAssignments.values():
                    try:
                        x = Fixture(i['name'],self.fixtureClasses[i['type']])
                        self.fixtures[i['name']] = x
                        self.fixtures[i['name']].assign(i['universe'],  int(i['addr']))
                        module.fixtures[i['name']]= weakref.ref(x)                    
                    except:
                        logger.exception("Error setting up fixture")
                        print(traceback.format_exc(4))
                        self.ferrs += str(i)+'\n'+traceback.format_exc(2)
    
    
                with universesLock:
                    for u in module.universes:
                        self.pushChannelNames(u)
    
                with fixtureslock:
                    for f in module.fixtures:
                        if f:
                            self.pushChannelNames("@"+f)
    
                self.ferrs = self.ferrs or 'No Errors!'
                self.pushfixtures()
    
            
        def createUniverses(self):
            for i in self.universeObjs:
                self.universeObjs[i].close()
                
            self.universeObjs = {}
            import gc 
            gc.collect()
            l ={}
            u = self.configuredUniverses
            for i in u:
                if u[i]['type'] == 'enttec':
                    l[i] = EnttecUniverse(i,channels=int(u[i].get('channels',128)),portname=u[i].get('interface',None),framerate=float(u[i].get('framerate',44)))
                if u[i]['type'] == 'artnet':
                    l[i] = ArtNetUniverse(i,channels=int(u[i].get('channels',128)),address=u[i].get('interface',"255.255.255.255:6454"),framerate=float(u[i].get('framerate',44)),number=int(u[i].get('number',0)))
                if u[i]['type']=='tagpoints':
                   l[i]=TagpointUniverse(i,channels=int(u[i].get('channels',128)),tagpoints=u[i].get('channelConfig',{}),framerate=float(u[i].get('framerate',44)),number=int(u[i].get('number',0)))
    
            self.universeObjs = l
            self.pushUniverses()
    
    
        def loadSceneFile(self,data,_asuser=False, filename=None,errs=False):
    
            data=yaml.load(data)
    
            #Detect if the user is trying to upload a single scenefile, if so, wrap it in a multi-dict of scenes to keep the reading code
            #The same for both
            if 'uuid' in data and isinstance(data['uuid'],str):
                #Remove the .yaml
                data = {filename[:-5]: data}
            
    
            for i in data:
                if 'page' in data[i] and data[i]['page']['html'].strip() or data[i]['page']['js'].strip():
                    if not kaithem.users.checkPermission(kaithem.web.user(),"/admin/modules.edit"):
                        raise ValueError("You cannot upload this scene without /admin/modules.edit, because it uses advanced features: pages" )
    
            self.loadDict(data,errs)
        
        def loadDict(self,data,errs=False):
            with module.lock:
                for i in data:
    
                         #New versions don't have a name key at all, the name is the key
                        if 'name' in data[i]:
                            pass
                        else:
                            data[i]['name'] = i
                        n = data[i]['name']
    
                        #Delete existing scenes we own
                        if n in module.scenes_by_name:
                            if module.scenes_by_name[n].id in self.scenememory:
                                self.scenememory[module.scenes_by_name[n].id].stop()
                                del self.scenememory[module.scenes_by_name[n].id]
                                del module.scenes_by_name[n]
                            else:
                                raise ValueError("Scene "+i+" already exists. We cannot overwrite, because it was not created through this board")
                        try:
                            #Kinda brittle and hacky, because loadinga new default scene isn't well
                            #supported
                            cues = data[i]['cues']
                            print(cues)
                            del data[i]['cues']
                            x = False
                            if 'defaultActive' in data[i]:
                                x =  data[i]['defaultActive']
                                del data[i]['defaultActive']
                            if 'active' in data[i]:
                                x =  data[i]['active']
                                del data[i]['active']
    
                            #Older versions indexed by UUID
                            if 'uuid' in data[i]:
                                uuid = data[i]['uuid']
                                del data[i]['uuid']
                            else:
                                uuid = i
                            
                           
    
                            s=Scene(id=uuid,defaultCue=False,defaultActive=x,**data[i])
                            for j in cues:
                                Cue(s,f=True,name=j,**cues[j])
                            s.cue = s.cues['default']
                            s.gotoCue("default")
    
                            self.scenememory[uuid] = s
                            if x:
                                s.go()
                                s.rerender=True
                        except Exception as e:
                            if not errs:
                                logger.exception("Failed to load scene "+str(i)+" "+str(data[i].get('name','')))
                                print("Failed to load scene "+str(i)+" "+str(data[i].get('name',''))+": "+traceback.format_exc(3))
                            else:
                                raise
                
        def addScene(self,scene):
            if not isinstance(scene, Scene):
                raise ValueError("Arg must be a Scene")
            self.scenememory[scene.id] = scene
            
        def rmScene(self,scene):
            try:
                del self.scenememory[scene.id]
            except:
                pass
    
            
        def pushEv(self,event,target,t=None, value=None,info=""):
    
           
            #TODO: Do we want a better way of handling this? We don't want to clog up the semi-re
            def f():
                if self.guiSendLock.acquire(timeout=5):
                    try:
                        self.link.send(['event',[event, target,kaithem.time.strftime(t or time.time() ),value, info]])
                    except:
                        if time.monotonic()-self.lastLoggedGuiSendError< 60:
                            logger.exception("Error when reporting event. (Log ratelimit: 30)")
                            self.lastLoggedGuiSendError = time.monotonic()
                    finally:
                        self.guiSendLock.release()
                else:
                    if time.monotonic()-self.lastLoggedGuiSendError< 60:
                        logger.error("Timeout getting lock to push event. (Log ratelimit: 60)")
                        self.lastLoggedGuiSendError = time.monotonic()
    
            kaithem.misc.do(f)
    
        def pushfixtures(self):
            "Errors in fixture list"
            self.link.send(["ferrs",self.ferrs])   
            try:
                self.link.send(['fixtures', {i:[module.fixtures[i]().universe,module.fixtures[i]().startAddress, module.fixtures[i]().channels] for i in module.fixtures} ])
            except:
                pass
                
        def pushUniverses(self):
            self.link.send(["universes",{i:{'count':len(module.universes[i].values), 
                        'status':module.universes[i].status, 
                        'ok':module.universes[i].ok,"telemetry":module.universes[i].telemetry} for i in module.universes}])   
    
        def getScenes(self):
            "Return serializable version of scenes list"
            with module.lock:
                sd = {}
                for i in self.scenememory:
                    x = self.scenememory[i]
                    sd[x.name] = {   
                                 'bpm':x.bpm,
                                 'alpha':x.defaultalpha,
                                 'cues': {j:x.cues[j].serialize() for j in x.cues},
                                 'priority'  : x.priority,
                                 'active': x.defaultActive,
                                 'blend':  x.blend,
                                 'blendArgs': x.blendArgs,
                                 'backtrack': x.backtrack,
                                 'soundOutput': x.soundOutput,
                                 'syncKey':x.syncKey, 'syncPort': x.syncPort, 'syncAddr':x.syncAddr,
                                 'uuid': i,
                                 'notes': x.notes,
                                 'page': x.page
                    }               
                    
    
                return sd
    
        def save(self):
            sd = self.getScenes()
            saveLocation = os.path.join(kaithem.misc.vardir,"chandler", "scenes")
    
            saved = {}
            with module.lock:    
                for i in sd:
                    saved[i+".yaml"]=True
                    kaithem.persist.save(sd[i], os.path.join(saveLocation,i+".yaml")  )
    
            #Delete everything not in folder
            for i in os.listdir(saveLocation):
                fn=os.path.join(saveLocation,i)
                if os.path.isfile(fn) and i.endswith(".yaml"):
                    if not i in saved:
                        os.remove(fn)
            try:
                #Remove the registry entry for the legacy way of saving things.                    
                kaithem.registry.delete("lighting/scenes")
            except KeyError:
                pass
        
        
        def pushTracks(self):
            self.link.send(['tracks',{i:module.runningTracks[i].name for i in module.runningTracks}])
    
        def pushChannelNames(self,u):
            "This has expanded to push more data than names"
            if not u[0]=='@':      
                if u in module.fastUniverses:
                    d = {}
                    for i in module.fastUniverses[u].channels:
                        fixture = module.fastUniverses[u].channels[i]
                        if not fixture.startAddress:
                            return
                        data= [fixture.name]+fixture.channels[i-fixture.startAddress]
                        d[i]=data
                    self.link.send(['cnames',u,d])
            else:
                d={}
                if u[1:] in module.fixtures:
                    f= module.fixtures[u[1:]]()
                    for i in range(0,len(f.channels)):
                        d[f.channels[i][0]] = [u[1:]]+ f.channels[i]
                self.link.send(['cnames',u,d])
    
    
    
        def pushMeta(self,sceneid, statusOnly=False):
            "Statusonly=only the stuff relevant to a cue change"
            scene = module.scenes[sceneid]
            
            try:
                if not scene.pavillionc:
                    subs=-1
                else:
                    subs=0
    
                subslist = []
                if scene.pavillionc:
                    x = scene.pavillionc.client.getServers()
    
                    subs = len(x)
                    if subs:
                        for i in x:
                            y = ""
                            try:
                                import netifaces
                                for interface in netifaces.interfaces():
                                    for link in netifaces.ifaddresses(interface)[netifaces.AF_INET]:
                                        if i[0]==link['addr']:
                                            y="[LOCALHOST]"
                                        if i[1]==scene.pavillions.server.sendsock.getsockname()[1]:
                                            y="[THIS SCENE]"
                            except:
                                pass
                            subslist.append(str(i)+y+": network: "+x[i].netType()+" "+str(x[i].rssi())+ ", battery: "+str(x[i].battery())+"%, battery state: "+x[i].batteryState()+", temperature: "+str(x[i].temperature())+"C") 
    
            except:
                subs = -1
                rl_log_exc("Error pushing metadata")
                print(traceback.format_exc())
            
            v = {}
            if scene.scriptContext:
                try:
                    for j in scene.scriptContext.variables:
                        if isinstance(scene.scriptContext.variables[j],(int,float,str, bool)):
                            v[j]=scene.scriptContext.variables[j]
                        else:
                            v[j]='__PYTHONDATA__'
                except:
                    print(traceback.format_exc())
            if not statusOnly:
                self.link.send(["scenemeta",sceneid,     
                                {
                                'ext':not sceneid in self.scenememory ,
                                'dalpha':scene.defaultalpha,
                                'alpha':scene.alpha,
                                'active': scene.isActive(),
                                'defaultActive': scene.defaultActive,
                                'name':scene.name,
                                'bpm': round(scene.bpm,6),
                                'blend':scene.blend,
                                'blendArgs': scene.blendArgs,
                                'blendDesc':module.getblenddesc(scene.blend),
                                'blendParams': scene.blendClass.parameters if hasattr(scene.blendClass,"parameters") else {},
                                'priority': scene.priority,
                                'started':  scene.started,
                                'enteredCue':  scene.enteredCue,
                                'backtrack': scene.backtrack,
                                'cue': scene.cue.id if scene.cue else scene.cues['default'].id,
                                'cuelen': scene.cuelen,
                                'syncKey': scene.syncKey,
                                'syncAddr': scene.syncAddr,
                                'syncPort': scene.syncPort,
                                'subs': subs,
                                'subslist': subslist,
                                'soundOutput': scene.soundOutput,
                                'vars':v,
                                'timers': scene.runningTimers,
                                'notes': scene.notes,
                                'page': scene.page
    
                        }])
            else:
                self.link.send(["scenemeta",sceneid,     
                                {
                                'alpha':scene.alpha,
                                'active': scene.isActive(),
                                'defaultActive': scene.defaultActive,
                        
                                'enteredCue':  scene.enteredCue,
                                'cue': scene.cue.id if scene.cue else scene.cues['default'].id,
                                'cuelen': scene.cuelen,
    
                        }])
                    
        def pushCueMeta(self,cueid):
            try:
                cue = cues[cueid]
                self.link.send(["cuemeta",cueid,     
                                { 
                                'fadein':cue.fadein, 
                                'alpha':cue.alpha,
                                'length':cue.length,
                                'lengthRandomize':cue.lengthRandomize,
                                'next':cue.nextCue if cue.nextCue else '',
                                'name': cue.name,
                                'id':cueid,
                                'sound': cue.sound,
                                'soundOutput': cue.soundOutput,
                                'rel_len': cue.rel_length,
                                'track': cue.track,
                                'scene': cue.scene().id,
                                'shortcut': cue.shortcut,
                                'number': cue.number/1000.0,
                                'defaultnext': cue.scene().getAfter(cue.name),
                                'prev': cue.scene().getParent(cue.name),
                                'script': cue.script,
                                'rules': cue.rules,
                                'reentrant': cue.reentrant,
                                'inheritRules': cue.inheritRules
                                }])
            except Exception as e:
                rl_log_exc("Error pushing cue data")
                print("cue data push error", cueid,e)
    
        def pushCueMetaAttr(self,cueid,attr):
            "Be careful with this, some attributes can't be sent directly and need preprocessing"
            try:
                cue = cues[cueid]
                self.link.send(["cuemetaattr",cueid,     
                                {attr:getattr(cue,attr)}])
            except Exception as e:
                rl_log_exc("Error pushing cue data")
                print("cue data push error", cueid,e)
    
    
        def pushCueData(self, cueid):
            self.link.send(["cuedata",cues[cueid].id,cues[cueid].values])
    
        def pushConfiguredUniverses(self):
            self.link.send(["confuniverses",self.configuredUniverses])
    
        def pushCueList(self,scene):
            s = module.scenes[scene]
            x =list(s.cues.keys())
            #split list into messages of 100 because we don't want to exceed the widget send limit
            while x:
                self.link.send(["scenecues",scene,{i:(s.cues[i].id,s.cues[i].number/1000.0) for i in x[:100] }])
                x = x[100:]
        def pushFixtureAssignmentCode(self):
            d = [[i['name'],i['type'],i['universe'],i['addr']] for i in self.fixtureAssignments.values()]
            self.link.send(['fixtureascode','\n'.join([', '.join(i) for  i in d])]  )
        def _onmsg(self,user,msg):
            #Adds a light to a scene
            try:
    
                if msg[0] == "saveAll":
                    self.save()
                    
                if msg[0] == "addscene":
                    s = Scene(msg[1].strip())
                    self.scenememory[s.id]=s
                    self.link.send(["newscene",msg[1].strip(),s.id])
    
                if msg[0] == "addmonitor":
                    s = Scene(msg[1].strip(),blend="monitor",priority=100)
                    self.scenememory[s.id]=s
                    self.link.send(["newscene",msg[1].strip(),s.id])   
    
                if msg[0] == "getserports":
                    self.link.send(["serports",getSerPorts()])   
                
                if msg[0]=="getCommands":
                    c = rootContext.commands.scriptcommands
                    l = {}
                    for i in c:
                        f = c[i]
                        l[i]=getFunctionInfo(f)
                    self.link.send(["commands",l])   
    
    
                if msg[0] == "getconfuniverses":
                    self.pushConfiguredUniverses()
    
                if msg[0] == "setconfuniverses":
                    if kaithem.users.checkPermission(user,"/admin/settings.edit"):
                        self.configuredUniverses = msg[1]
                        kaithem.registry.set("lighting/universes",msg[1])
                        self.createUniverses()
                    else:
                        raise RuntimeError("User does not have permission")
    
                if msg[0] == "setfixtureclass":
                    l =[]
                    for i in msg[2]:
                        if i[1] not in ['custom', 'fine']:
                            l.append(i[:2])
                        else:
                            l.append(i)
                    self.fixtureClasses[msg[1]] =l
                    kaithem.registry.set("lighting/fixturetypes", self.fixtureClasses)
                    self.refreshFixtures()
    
                if msg[0] == "setfixturesfromcode":
                    self.fixtureAssignments = fixturesFromOldListStyle([[j.strip() for j in i.split(',')] for i in msg[1].split("\n") if len(i)])
                    kaithem.registry.set("lighting/fixtures", self.fixtureAssignments)
                    self.link.send(['fixtureAssignments', self.fixtureAssignments])
                    self.pushFixtureAssignmentCode()
                    self.refreshFixtures()
    
    
                if msg[0] == "setFixtureAssignment":
                    self.fixtureAssignments[msg[1]]=msg[2]
                    kaithem.registry.set("lighting/fixtures", self.fixtureAssignments)
                    self.link.send(['fixtureAssignments', self.fixtureAssignments])
                    self.pushFixtureAssignmentCode()
                    self.refreshFixtures()
    
                if msg[0] == "rmFixtureAssignment":
                    del self.fixtureAssignments[msg[1]]
    
                    self.link.send(['fixtureAssignments', self.fixtureAssignments])
                    self.pushFixtureAssignmentCode()
                    kaithem.registry.set("lighting/fixtures", self.fixtureAssignments)
                    self.link.send(['fixtureAssignments', self.fixtureAssignments])
    
                   
                    
                    self.refreshFixtures()
    
    
    
                if msg[0] == "getfixtureassg":
                    self.link.send(['fixtureAssignments', self.fixtureAssignments])
                    self.pushFixtureAssignmentCode()
                    self.pushfixtures()
                    
                if msg[0] == "clonecue":
                    cues[msg[1]].clone(msg[2])
    
                if msg[0] == "jumptocue":
                    cues[msg[1]].scene().gotoCue(cues[msg[1]].name)
    
                if msg[0] == "jumpbyname":
                   module.scenes_by_name[msg[1]].gotoCue(msg[2])
                                   
                if msg[0] == "nextcue":
                    module.scenes[msg[1]].nextCue()
    
                if msg[0] == "nextcuebyname":
                    module.scenes_by_name[msg[1]].nextCue()
    
                if msg[0] == "shortcut":
                    shortcutCode(msg[1])
    
                if msg[0]=="event":
                    event(msg[1])
                    
                if msg[0] == "setshortcut":
                    cues[msg[1]].setShortcut(msg[2][:128])      
                if msg[0] == "setnumber":
                    cues[msg[1]].setNumber(msg[2])
    
                if msg[0] == "setrellen":
                    cues[msg[1]].rel_length=msg[2]
                    self.pushCueMeta(msg[1])
                
                if msg[0] == "setsoundout":
                    cues[msg[1]].soundOutput=msg[2]
                    self.pushCueMeta(msg[1])
    
                if msg[0] == "setNotes":
                    module.scenes[msg[1]].notes=msg[2]
                    self.pushMeta(msg[1])
    
    
                if msg[0] == "setPage":
                    if kaithem.users.checkPermission(user,"/admin/modules.edit"):
                        module.scenes[msg[1]].setPage(msg[2],msg[3],msg[4])
                        self.pushMeta(msg[1])
    
    
                if msg[0] == "clonescene":
                    s = Scene(msg[2])
                    self.scenememory[s.id]=s
                    s0 =module.scenes[msg[1]]
                    s.values = copy.deepcopy(s0.values)
                    s.fadein = s0.fadein
                    s.length = s0.length
                    s.defaultalpha = s0.defaultalpha
                    s.alpha = s0.alpha
                    s.track = s0.track
                    s.setBlend(s0.blend)
                    s.blendArgs = s0.blendArgs.copy()
    
                    self.link.send(["newscene",msg[1],s.id])
    
                if msg[0] == "getcnames":
                    self.pushChannelNames(msg[1])
    
                if msg[0] == "namechannel":
                    if msg[3]:
                        module.universes[msg[1]].channels[msg[2]] = msg[3]
                    else:
                        del module.universes[msg[1]].channels[msg[2]]
    
                    
                if msg[0] == "addcueval":
                    if hasattr(cues[msg[1]].scene().blendClass,'default_channel_value'):
                        val = cues[msg[1]].scene().blendClass.default_channel_value
                    else:
                        val = 0
                    cues[msg[1]].setValue(msg[2],msg[3],val)
    
                if msg[0] == "setcuevaldata":
                    
                    #Verify correct data
                    for i in msg[2]:
                        for j in msg[2][i]:
                            float(msg[2][i][j])
                    
                    cues[msg[1]].clearValues()
                    
                    for i in msg[2]:
                        for j in msg[2][i]:
                            try:
                                ch = int(j)
                            except:
                                ch = j
                            #Hack. because JSON and yaml are giving us strings
                            cues[msg[1]].setValue(i,j,msg[2][i][j])
    
                if msg[0] == "addcuef":
                    cue = cues[msg[1]]
    
                    x = module.fixtures[msg[2]]()
                    #Add every non-unused channel.  Fixtures
                    #Are stored as if they are their own universe, starting with an @ sign.
                    #Channels are stored by name and not by number.
                    for i in x.channels:
                        if not i[1]=="unused":
                            if hasattr(cue.scene().blendClass,'default_channel_value'):
                                val = cue.scene().blendClass.default_channel_value
                            else:
                                val = 0
                            #i[0] is the name of the channel
                            cue.setValue("@"+msg[2],i[0],val)
    
                    self.link.send(["cuedata",msg[1],cue.values])
    
                if msg[0] == "rmcuef":
                    s = cues[msg[1]]
                    
    
                    x = list(s.values[msg[2]].keys())
                    
                    for i in x:
                        s.setValue(msg[2],i,None)
                    self.link.send(["cuedata",msg[1],s.values])
    
    
                if msg[0] == "rmsceneval":
                    s = scenes[msg[1]]
                    s.setValue(msg[2],None)
    
                if msg[0] == "setscenelight":
                    module.universes[msg[1]][msg[2]]=float(msg[3])
    
                if msg[0] == "gsd":
                    #Could be long-running, so we offload to a workerthread
                    #Used to be get scene data, Now its a general get everything to show pags thing
                    def f():
                        s = module.scenes[msg[1]]
                        self.pushCueList(s.id)
                        self.pushMeta(msg[1])
                        self.pushfixtures()
                    kaithem.misc.do(f)
                
    
                if msg[0] == "getSceneMeta":
                    #Could be long-running, so we offload to a workerthread
                    #Used to be get scene data, Now its a general get everything to show pags thing
                    def f():
                        s = module.scenes[msg[1]]
                        self.pushMeta(msg[1])
                    kaithem.misc.do(f)
                
                if msg[0] == "getallcuemeta":
                    def f():
                        for i in module.scenes[msg[1]].cues:
                            self.pushCueMeta(module.scenes[msg[1]].cues[i].id)
                    kaithem.misc.do(f)
    
                if msg[0] == "getcuedata":
                    s = cues[msg[1]]
                    self.link.send(["cuedata",msg[1],s.values])
                    self.pushCueMeta(msg[1])
    
                if msg[0] == "getfixtureclass":
                    self.link.send(["fixtureclass",msg[1],self.fixtureClasses[msg[1]]])
                    
                if msg[0] == "getfixtureclasses":
                    #Send placeholder lists
                    self.link.send(["fixtureclasses",{i:[] for i in self.fixtureClasses.keys()}])
                
                if msg[0] == 'listsoundfolder':
                    self.link.send(["soundfolderlisting",msg[1],listsoundfolder(msg[1])])
    
    
    
                if msg[0] == "getcuemeta":
                    s = cues[msg[1]]
                    self.pushCueMeta(msg[1])
    
                if msg[0] == "gasd":
                    with module.lock:
                        self.pushUniverses()
                        self.pushfixtures()
                        for i in self.scenememory:
                            s = self.scenememory[i]
                            self.pushCueList(s.id)
                            self.pushMeta(i)
                            try:
                                self.pushCueMeta(self.scenememory[i].cue.id)
                            except:
                                print(traceback.format_exc())
                            try:
                                self.pushCueMeta(self.scenememory[i].cues['default'].id)
                            except:
                                print(traceback.format_exc())
    
                            try:
                                for j in self.scenememory[i].cues:
                                    self.pushCueMeta(self.scenememory[i].cues[j].id)
                            except:
                                print(traceback.format_exc())
    
                        for i in module.activeScenes:
                            #Tell clients about any changed alpha values and stuff.
                            if not i.id in self.scenememory:
                                self.pushMeta(i.id)
                        self.pushConfiguredUniverses()
                    self.link.send(["serports",getSerPorts()])   
    
    
    
                #There's such a possibility for an iteration error if universes changes.
                #I'm not going to worry about it, this is only for the GUI list of universes.
                if msg[0] == "getuniverses":
                    self.pushUniverses()
    
    
                if msg[0] == "scv":
                    ch = msg[3]
                    #If it looks like an int, it should be an int.
                    if isinstance(ch, str):
                        try:
                            ch=int(ch)
                        except:
                            pass
                    cues[msg[1]].setValue(msg[2],ch,msg[4])
                    self.link.send(["scv",msg[1],msg[2],ch,msg[4]])
    
                
                if msg[0]=="generatesynckey":
                    module.scenes[msg[1]].setSyncKey(base64.b64encode(os.urandom(32)).decode("utf8"))
                    
                if msg[0] == "setsynckey":
                    module.scenes[msg[1]].setSyncKey(msg[2])
                
                if msg[0] == "setsyncaddr":
                    module.scenes[msg[1]].setSyncAddress(msg[2])
                
                if msg[0] == "setsyncport":
                    module.scenes[msg[1]].setSyncPort(int(msg[2]))
    
                if msg[0] == "tap":
                    module.scenes[msg[1]].tap(msg[2])
                if msg[0] == "setbpm":
                    module.scenes[msg[1]].setBPM(msg[2])
    
                if msg[0] == "setalpha":
                    module.scenes[msg[1]].setAlpha(msg[2])
    
                    
                if msg[0] == "setdalpha":
                    module.scenes[msg[1]].setAlpha(msg[2],sd=True)
    
                if msg[0] == "addcue":
                    n = msg[2].strip()
                    if not msg[2] in module.scenes[msg[1]].cues:
                        module.scenes[msg[1]].addCue(n)
                
                if msg[0]=="searchsounds":
                    self.link.send(['soundsearchresults', msg[1], searchPaths(msg[1], getSoundFolders()) ])
                if msg[0]=="newFromSound":
                    bn = os.path.basename(msg[2])
                    bn=fnToCueName(bn)
                    try:
                        tags = TinyTag.get(msg[2])
                        if tags.artist and tags.title:
                            bn = tags.title +" ~ "+ tags.artist
                    except:
                        pass
                    if not bn in module.scenes[msg[1]].cues:
                        module.scenes[msg[1]].addCue(bn)
                        module.scenes[msg[1]].cues[bn].rel_length=True
                        module.scenes[msg[1]].cues[bn].length=0.01
    
                        soundfolders = getSoundFolders()
    
                        for i in soundfolders:
                            s = msg[2]
                            #Make paths relative.
                            if not i.endswith("/"):
                                i = i+"/"
                            if s.startswith(i):
                                s= s[len(i):]
                                break
                        module.scenes[msg[1]].cues[bn].sound = s
                        self.pushCueMeta(module.scenes[msg[1]].cues[bn].id)
                
    
                if msg[0] == "gotonext":
                    if cues[msg[1]].nextCue:
                        try:
                            cues[msg[1]].scene().nextCue()
                        except:
                            pass
    
    
                if msg[0] == "rmcue":
                    c = cues[msg[1]]
                    c.scene().rmCue(c.id)
                             
                if msg[0] == "setfadein":
                    try:
                        v=float(msg[2])
                    except:
                        v=msg[2]
                    cues[msg[1]].fadein=v
                    self.pushCueMeta(msg[1])
                             
                if msg[0] == "setreentrant":
                    v=bool(msg[2])
       
                    cues[msg[1]].reentrant=v
                    self.pushCueMeta(msg[1])
    
    
                if msg[0] == "setCueRules":
                    cues[msg[1]].setRules(msg[2])
                    self.pushCueMeta(msg[1])
    
                if msg[0] == "setCueInheritRules":
                    cues[msg[1]].setInheritRules(msg[2])
                    self.pushCueMeta(msg[1])
    
                if msg[0]=="setcuesound":
             
                    soundfolders = getSoundFolders()
    
                    for i in soundfolders:
                        s = msg[2]
                        #Make paths relative.
                        if not i.endswith("/"):
                            i = i+"/"
                        if s.startswith(i):
                            s= s[len(i):]
                            break
    
                    cues[msg[1]].sound=s
                    self.pushCueMeta(msg[1])
    
                if msg[0]=="setcuesoundoutput":
                    cues[msg[1]].soundOutput=msg[2]
                    self.pushCueMeta(msg[1])
    
                if msg[0]=="setlninfluences":
                    cues[msg[1]].setLivingNightInfluences(msg[2])
                    self.pushCueMeta(msg[1])
    
                if msg[0]=="setlnassosiations":
                    cues[msg[1]].setLivingNightAssociatoind(msg[2])
                    self.pushCueMeta(msg[1])
    
    
    
                if msg[0] == "settrack":
                    cues[msg[1]].setTrack(msg[2])
                    self.pushCueMeta(msg[1])
    
    
                if msg[0] == "setdefaultactive":
                    module.scenes[msg[1]].defaultActive=bool(msg[2])
                    self.pushMeta(msg[1])
                    
                if msg[0] == "setbacktrack":
                    module.scenes[msg[1]].setBacktrack(bool(msg[2]))
                    self.pushMeta(msg[1])
                
                if msg[0] == "setscenesoundout":
                    module.scenes[msg[1]].soundOutput=msg[2]
                    self.pushMeta(msg[1])
    
                if msg[0] == "setlength":
                    try:
                        v=float(msg[2])
                    except:
                        v=msg[2][:256]
                    cues[msg[1]].length=v
                    cues[msg[1]].scene().recalcCueLen()
                    self.pushCueMeta(msg[1])
    
                if msg[0] == "setrandomize":
                    try:
                        v=float(msg[2])
                    except:
                        v=msg[2][:256]
                    cues[msg[1]].lengthRandomize=v
                    cues[msg[1]].scene().recalcRandomizeModifier()
                    self.pushCueMeta(msg[1])
    
                if msg[0] == "setnext":
                    disallow_special( msg[2][:1024],allow=allowedCueNameSpecials+"*|")
                    if msg[2][:1024]:
                        c = msg[2][:1024]
                    else:
                        c = None
                    cues[msg[1]].nextCue= c
                    self.pushCueMeta(msg[1])
    
                if msg[0] == "setscript":
                    cues[msg[1]].setScript(msg[2][:2048],allow_bad=False)
                    self.pushCueMeta(msg[1])
    
                if msg[0] == "setblend":
                    module.scenes[msg[1]].setBlend(msg[2])
                if msg[0] == "setblendarg":
                    module.scenes[msg[1]].setBlendArg(msg[2],msg[3])
                    
                if msg[0] == "setpriority":
                    module.scenes[msg[1]].setPriority(msg[2])  
    
                if msg[0] == "setscenename":
                    module.scenes[msg[1]].setName(msg[2])  
                       
                if msg[0] == "del":
                    #X is there in case the activeScenes listing was the last string reference, we want to be able to push the data still
                    x = module.scenes[msg[1]]
                    if x.page['html'].strip() or x.page['css'].strip() or x.page['js'].strip():
                        if not kaithem.users.checkPermission(user,"/admin/modules.edit"):
                            raise ValueError("You cannot delete this scene without /admin/modules.edit, because it uses advanced features: pages" )
                    x.stop()
                    self.delscene(msg[1])
                    
                if msg[0] == "go":
                    module.scenes[msg[1]].go()
                    self.pushMeta(msg[1])
                    
                if msg[0] == "gobyname":
                    module.scenes_by_name[msg[1]].go()
                    self.pushMeta(module.scenes_by_name[msg[1]].id)
                    
                if msg[0] == "stopbyname":
                    module.scenes_by_name[msg[1]].stop()
                    self.pushMeta(msg[1])
                    
                if msg[0] == "togglebyname":
                    if module.scenes_by_name[msg[1]].isActive():
                        module.scenes_by_name[msg[1]].stop()
                    else:
                        module.scenes_by_name[msg[1]].go()
                    self.pushMeta(msg[1])
                    
                if msg[0] == "stop":
                    x = module.scenes[msg[1]]
                    x.stop()
                    self.pushMeta(msg[1])
    
                    
                if msg[0] == "next":
                    try:
                        module.runningTracks[msg[1]].end()
                    except:
                        pass           
    
                if msg[0] == "testSoundCard":
                    kaithem.sound.play("alert.ogg",output=msg[1], handle="lightboard_soundtest")
        
    
            except Exception as e:
                rl_log_exc("Error handling command")
                self.pushEv('board.error', "__this_lightboard__",module.timefunc(), "", traceback.format_exc(8))
                print(msg,traceback.format_exc(8))
                
        def setChannelName(self,id,name="Untitled"):
            self.channelNames[id]=name
            
        def delscene(self,sc):
            i=None
            with module.lock:
                if sc in self.scenememory:
                    i = self.scenememory.pop(sc)
            if i:
                i.stop()
                module.scenes_by_name.pop(i.name)
                self.link.send(["del",i.id])  
    
    
        def guiPush(self):
            with module.lock:
                for i in self.newDataFunctions:
                    i(self)
                self.newDataFunctions = []
                for i in module.universes:
                    if not self.id in module.universes[i].statusChanged:
                        self.link.send(["universe_status",i,module.universes[i].status,module.universes[i].ok,module.universes[i].telemetry])
                        module.universes[i].statusChanged[self.id]=True
    
                for i in self.scenememory:
                    #Tell clients about any changed alpha values and stuff.
                    if not self.id in self.scenememory[i].hasNewInfo:
                        self.pushMeta(i)
                        self.scenememory[i].hasNewInfo[self.id]=False
    
                    #special case the monitor scenes.
                    if self.scenememory[i].blend=="monitor" and self.scenememory[i].isActive() and self.id not in self.scenememory[i].valueschanged:
                        self.scenememory[i].valueschanged[self.id]=True
                        #Numpy scalars aren't serializable, so we have to un-numpy them in case
                        self.link.send(["cuedata",self.scenememory[i].cue.id,self.scenememory[i].cue.values])
                        
                for i in module.activeScenes:
                    #Tell clients about any changed alpha values and stuff.
                    if not self.id in i.hasNewInfo:
                        self.pushMeta(i.id)
                        i.hasNewInfo[self.id]=False
    
    
    def composite(background,values,alphas,alpha):
        "In place compositing of one universe as a numpy array on a background.  Returns background."
        background= background*(1-(alphas*alpha)) + values*alphas*alpha
        return background
            
    
    def applyLayer(universe, uvalues,scene):
        "May happen in place, or not, but always returns the new version"
    
        if not universe in scene.canvas.v2:
            return uvalues
        vals = scene.canvas.v2[universe]
        alphas = scene.canvas.a2[universe]
    
    
        if scene.blend =="normal":
            uvalues = composite(uvalues,vals,alphas,scene.alpha)
    
    
        elif scene.blend == "HTP":
            uvalues = numpy.maximum(uvalues, vals*(alphas*scene.alpha))
    
        elif scene.blend == "inhibit":
            uvalues = numpy.minimum(uvalues, vals*(alphas*scene.alpha))
    
        elif scene.blend == "gel" or scene.blend=="multiply":
            if scene.alpha:
                #precompute constants
                c= 255/scene.alpha
                uvalues = (uvalues*(1-alphas*scene.alpha)) + (uvalues*vals)/c
    
    
        elif scene._blend:
            try:
                uvalues = scene._blend.frame(universe,uvalues,vals,alphas,scene.alpha)
            except:
                print("Error in blend function")
                print(traceback.format_exc())
        return uvalues
    
    
    def pre_render():
        "Reset all universes to either the all 0s background or the cached layer, depending on if the cache layer is still valid"
        #Here we find out what universes can be reset to a cached layer and which need to be fully rerendered.
        changedUniverses = {}
        to_reset ={}
        universes = module.fastUniverses
        #Important to reverse, that way scenes that need a full reset come after and don't get overwritten
        for i in reversed(module.activeScenes):
            for u in i.affect:
                if u in universes:
                    universe = universes[u]
                    universe.all_static = True
                    if i.rerender:
                        changedUniverses[u] =(0,0)
    
                        #We are below the cached layer, we need to fully reset
                        if ((i.priority,i.started) <= universe.prerendered_layer):
                            to_reset[u]=1
                        else:
                            #We are stacking on another layer or changing the top layer. We don't need
                            #To rerender the entire stack, we just start from the prerendered_layer
                            #Set the universe to the state it was in just after the prerendered layer was rendered.
                            #Since the values are mutable, we need to set this back every frame
    
                            #Don't overwrite a request to reset the entire thing
                            if not to_reset.get(u,0)==1:
                                to_reset[u]=2
        for u in universes:
            if universes[u].full_rerender:
                to_reset[u]=1
    
        for u in to_reset:
            if to_reset[u]==1 or not universes[u].prerendered_layer[1]:
                universes[u].reset()
                changedUniverses[u]=(0,0)
            else:
                universes[u].reset_to_cache()
                changedUniverses[u]=(0,0)        
        return changedUniverses
    
    def render(t=None):
        "This is the primary rendering function"
        changedUniverses = pre_render()
      
        t = t or module.timefunc()
        
        #Remember that scenes get rendered in ascending priority order here
        for i in module.activeScenes:
    
    
            #We don't need to call render() if the frame is a static scene and the opacity
            #and all that is the same, we can just re-layer it on top of the values
            if i.rerender or (i.cue.length and ((module.timefunc()-i.enteredCue)>i.cuelen*(60/i.bpm))):
                i.rerender = False
                i.render()
    
            if i.blend=="monitor":
                i.updateMonitorValues()
                continue
    
            data =i.affect
    
            #Loop over universes the scene affects
            for u in data:
                if u.startswith("__") and u.endswith("__"):
                    continue
    
                if not u in module.universes:
                    continue
                if (i.priority,i.started) > module.fastUniverses[u].top_layer:
                    #If this layer we are about to render was found to be the highest layer that won't need rerendering,
                    #Save the state just befor we apply that layer.
                    if (module.fastUniverses[u].save_before_layer==(i.priority,i.started)) and not((i.priority,i.started)==(0,0)):
                        module.fastUniverses[u].save_prerendered(module.fastUniverses[u].top_layer[0], module.fastUniverses[u].top_layer[1])
    
                    changedUniverses[u]=(i.priority, i.started)
                    if not u in module.universes:
                        continue
                    
                    universe = module.fastUniverses[u]
                    universe.values = applyLayer(u, universe.values, i)
                    universe.top_layer = (i.priority, i.started)
    
                    #If this is the first nonstatic layer, meaning it's render function requested a rerender next frame
                    #or if this is the last one, mark it as the one we should save just before
                    if i.rerender or (i is module.activeScenes[-1]):
                        if module.fastUniverses[u].all_static:
                            #Copy it and set to none as a flag that we already found it
                            module.fastUniverses[u].all_static = False
                            module.fastUniverses[u].save_before_layer = module.fastUniverses[u].top_layer
            
    
        for i in changedUniverses:
            try:
                if i in module.universes:
                    module.universes[i].preFrame()
                    module.universes[i].onFrame()
            except:
                raise
        for i in module.universes:
            module.universes[i].full_rerender  =False
        changedUniverses={}
    
    
    
    
    
    def makeBlankArray(l):
        x = [0]* l
        return numpy.array(x,dtype="f4")
    
    class FadeCanvas():
        def __init__(self):
            "Handles calculating the effect of one scene over a background. This doesn't do blend modes, it just interpolates."
            self.v = {}
            self.a = {}
            self.v2 = {}
            self.a2 = {}
    
        
        def paint(self,scene,fade,vals=None,alphas=None):
            """
            Makes v2 and a2 equal to the current background overlayed with values from scene which is any object that has dicts of dicts of vals and and
            alpha.
    
            Should you have cached dicts of arrays vals and alpha channels(one pair of arrays per universe), put them in vals and arrays
            for better performance.
    
            fade is the fade amount from 0 to 1 (from background to the new)
    
            defaultValue is the default value for a universe. Usually 0.
    
            """
            
            #We assume a lot of these lists have the same set of universes. If it gets out of sync you
            #probably have to stop and restart the scenes.
            for i in vals:
                #Add existing universes to canvas, skip non existing ones
                if not i in self.v:
                    if i in module.universes:
                        self.v[i] = makeBlankArray(len(module.universes[i].values))
                        self.a[i] = makeBlankArray(len(module.universes[i].values))
                        self.v2[i] = makeBlankArray(len(module.universes[i].values))
                        self.a2[i] = makeBlankArray(len(module.universes[i].values))
                    else:
                        continue
                else:
                    #We don't want to fade any values that have 0 alpha in the scene,
                    #because that's how we mark "not present", and we want to track the old val.
                    #faded = self.v[i]*(1-(fade*alphas[i]))+ (alphas[i]*fade)*vals[i]
                    
                    faded = self.v[i]*(1-fade) + (fade*vals[i])
                    
                    
                    
                    #We always want to jump straight to the value if alpha was previously 0.
                    #That's because a 0 alpha would mean the last scene released that channel, and there's
                    #nothing to fade from, so we want to fade in from transparent not from black
                    is_new = self.a == 0
                    self.v2[i] = numpy.where(is_new, vals[i], faded)
                    
                    
            #Now we calculate the alpha values. Including for
            #Universes the cue doesn't affect.
            for i in self.a:
                if not i in alphas:
                    aset = 0
                else:
                    aset = alphas[i]
                self.a2[i] = self.a[i]*(1-fade) + fade*aset
    
    
    
        def paintFadeout(self,scene,fade):
            for i in self.v:
                self.a2[i]= self.a[i]*(1-fade) 
    
        def save(self):
            self.v = copy.deepcopy(self.v2)
            self.a = copy.deepcopy(self.a2)
    
        def clean(self, affect):
            for i in list(self.a.keys()):
                if not i in affect:
                    del self.a[i]
    
            for i in list(self.a2.keys()):
                if not i in affect:
                    del self.a2[i]
    
            for i in list(self.v.keys()):
                if not i in affect:
                    del self.v[i]
    
            for i in list(self.v2.keys()):
                if not i in affect:
                    del self.v2[i]
            
    
    def shortcutCode(code):
        "API to activate a cue by it's shortcut code"
        with module.lock:
            if code in shortcut_codes:
                for i in shortcut_codes[code]:
                    x=i.scene()
                    if x:
                        x.go()
                        x.gotoCue(i.name)
    
    cues =weakref.WeakValueDictionary()
    
    cueDefaults = {
    
        "fadein":0,
        "length": 0,
        "track": True,
        "nextCue": '',
        "sound": "",
        "soundOutput": '',
        "rel_length": False,
        "lengthRandomize": 0,
        'inheritRules':'',
        'rules':[],
        'script':'',
        'values': {},
    }
    
    class Cue():
        "A static set of values with a fade in and out duration"
        __slots__=['id','changed','next_ll','alpha','fadein','fadeout','length','lengthRandomize','name','values','scene',
        'nextCue','track','shortcut','number','inherit','sound','rel_length','script',
        'soundOutput','onEnter','onExit','influences','associations',"rules","reentrant","inheritRules",
        '__weakref__']
        def __init__(self,parent,name, f=False, values=None, alpha=1, fadein=0, fadeout=0, length=0,track=True, nextCue = None,shortcut=None,sound='',soundOutput='',rel_length=False, id=None,number=None,
            lengthRandomize=0,script='',onEnter=None,onExit=None,rules=None,reentrant=True,inheritRules='',**kw):
            #This is so we can loop through them and push to gui
            self.id = uuid.uuid4().hex
            self.name = name
            self.script = script
            self.onEnter = onEnter
            self.onExit = onExit
            self.inheritRules=inheritRules or ''
            self.reentrant=True
    
            ##Rules created via the GUI logic editor
            self.rules = rules or []
    
            disallow_special(name,allowedCueNameSpecials)
            if name[0] in '1234567890 \t_':
                name = 'x'+name
    
            if id:
                disallow_special(id)
            self.inherit = None
            cues[self.id] =self
            #Odd circular dependancy
            try:
                self.number = number or parent.cues_ordered[-1].number+5000
            except:
                self.number = 5000
            self.next_ll = None
            parent._addCue(self,f=f)
            self.changed= {}
            self.alpha = alpha
            self.fadein =fadein
            self.length = length
            self.rel_length = rel_length
            self.lengthRandomize = lengthRandomize
            self.values = values or {}
            self.scene = weakref.ref(parent)
            self.nextCue = nextCue or ''
            #Note: This refers to tracking as found on lighting gear, not the old concept of track from
            #the first version
            self.track = track
            self.shortcut= None
            self.sound = sound or ''
            self.soundOutput = soundOutput or ''
            s = number_to_shortcut(self.number)
            shortcut = shortcut or s
    
            #Used for the livingnight algorithm
            #Aspect, value tuples
            self.influences = {}
    
            #List if tuples(type, aspect, effect)
            #Type is what parameter if the cue is being affected
            self.associations = []
    
    
            self.setShortcut(shortcut)
                
            self.push()
        
        def setInfluences(self, influences):
            self.influences = influences
            self.scene.recalcLivingNight()
        
        def getProbabilty(self):
            """
            When randomly selecting a cue, this modifies the probability of each cue
            based on LivingNight parameters
            """
            s = 1
            for i in self.associations:
                if i[0]== 'probability':
                    s= module.lnEffect(s,i[1],i[2])
    
            return s 
    
        def serialize(self):
                x =  {"fadein":self.fadein,"length":self.length,'lengthRandomize':self.lengthRandomize,"shortcut":self.shortcut,"values":self.values,
                "nextCue":self.nextCue,"track":self.track,"number":self.number,'sound':self.sound,'soundOutput':self.soundOutput,'rel_length':self.rel_length, 'script':self.script, 'rules':self.rules,
                'reentrant':self.reentrant, 'inheritRules': self.inheritRules
                }
    
                #Cleanup defaults
                if x['shortcut']==number_to_shortcut(self.number):
                    del x['shortcut']
                for i in cueDefaults:
                    if x[i]==cueDefaults[i]:
                        del x[i]
                return x
    
        def setScript(self,script, allow_bad=True):
            self.script = script
            try:
                self.scene().refreshRules()
            except:
                rl_log_exc("Error handling script")
                print(traceback.format_exc(6))
                if not allow_bad:
                    raise
                
        
        def push(self):
            for i in module.boards:
                if len(i().newDataFunctions)<100:
                    i().newDataFunctions.append(lambda s:s.pushCueMeta(self.id))
    
        
        def pushData(self):
            for i in module.boards:
                if len(i().newDataFunctions)<100:
                    i().newDataFunctions.append(lambda s:s.pushCueData(self.id))
    
        def pushoneval(self,u,ch,v):
            for i in module.boards:
                if len(i().newDataFunctions)<100:
                    i().newDataFunctions.append(lambda s:s.link.send(["scv",self.id,u,ch,v]))
    
          
        def clone(self,name):
            if name in self.scene().cues:
                raise RuntimeError("Cannot duplicate cue names in one scene")
    
            c = Cue(self.scene(), name, fadein=self.fadein, length=self.length,  lengthRandomize=self.lengthRandomize
            ,values=copy.deepcopy(self.values),nextCue=self.nextCue)
            
            for i in module.boards:
                if len(i().newDataFunctions)<100:
                    i().newDataFunctions.append(lambda s:s.pushCueMeta(c.id))
            for i in module.boards:
                if len(i().newDataFunctions)<100:
                    i().newDataFunctions.append(lambda s:s.pushCueData(c.id))
    
        def setTrack(self,val):
            self.track = bool(val)
            self.scene().rerender = True
        
        def setNumber(self,n):
            "Can take a string representing a decimal number for best accuracy, saves as *1000 fixed point"
            if self.shortcut ==number_to_shortcut(self.number):
                self.setShortcut(number_to_shortcut(int((Decimal(n)*Decimal(1000)).quantize(1))))
            self.number = int((Decimal(n)*Decimal(1000)).quantize(1))
    
            self.push()
    
        def setRules(self,r):
            self.rules = r
            self.scene().refreshRules()
    
        def setInheritRules(self,r):
            self.inheritRules = r
            self.scene().refreshRules()
    
    
        def setShortcut(self,code):
            disallow_special(code,allow=".")
            with module.lock:
                if self.shortcut in shortcut_codes:
                    try:
                        shortcut_codes[code].remove(self)
                    except:
                        pass
                        
                #Do a full GC pass of the shortcut codes list 
                torm = []
                for i in shortcut_codes:
                    if not shortcut_codes[i]:
                        torm.append(i)
                    else:
                        for j in shortcut_codes[i]:
                            if not j.scene():
                                shortcut_codes[i].remove(j)
                for i in torm:
                    del shortcut_codes[i]
    
                if code in shortcut_codes:
                    shortcut_codes[code].append(self)
                else:
                    shortcut_codes[code] = [self]
        
    
                self.shortcut = code
                self.push()
    
        def setValue(self,universe,channel,value):
            disallow_special(universe, allow="_@")
            if isinstance(channel,int):
                pass
            elif isinstance(channel,str):
    
                x = channel.strip()
                if not x==channel:
                    raise ValueError("Channel name cannot begin or end with whitespace")
    
                #If it looks like an int, cast it even if it's a string,
                #We get a lot of raw user input that looks like that.
                try:
                    channel=int(channel)
                except:
                    pass
            else:
                raise Exception("Only str or int channel numbers allowed")
            
    
            
            #Assume anything that can be an int, is meant to be
            if isinstance(channel, str):
                try:
                    channel=int(channel)
                except:
                    pass
    
            
          
    
            with module.lock:
                if universe =="__variables__":
                    self.scene().scriptContext.setVar(channel,self.scene().evalExpr(value))
    
                self.scene().rerender = True
                reset = False
                if not (value is None):
                    if not universe in self.values:
                        self.values[universe] = {}
                        reset = True
                    if not channel in self.values[universe]:
                        reset = True
                    self.values[universe][channel] = value
                else:
                    empty=False
                    if channel in self.values[universe]:
                        del self.values[universe][channel]
                    if not self.values[universe]:
                        empty=True
                        del self.values[universe]
                    if empty:
                        self.pushData()        
                self.pushoneval(universe,channel,value)
                
                    
                x = mapChannel(universe, channel)
                if x:
                    universe, channel = x[0],x[1]
    
                    if self.scene().cue==self and self.scene().isActive():
                        self.scene().rerender=True    
                        if (not universe in self.scene().cue_cached_alphas_as_arrays) and universe in module.universes and not value is None:
                            self.scene().cue_cached_vals_as_arrays[universe] = numpy.array([0.0]*len(module.universes[universe].values),dtype="f4")
                            self.scene().cue_cached_alphas_as_arrays[universe] = numpy.array([0.0]*len(module.universes[universe].values),dtype="f4")
                        if universe in self.scene().cue_cached_alphas_as_arrays:
                            self.scene().cue_cached_alphas_as_arrays[universe][channel] = 1 if not value is None else 0
                            self.scene().cue_cached_vals_as_arrays[universe][channel] =  self.scene().evalExpr(value if not value is None else 0)
                        if not universe in self.scene().affect:
                            self.scene().affect.append(universe)
    
                        #The FadeCanvas needs to know about this change
                        self.scene().render(force_repaint=True)
    
                #For blend modes that don't like it when you
                #change the list of values without resetting
                if reset:
                    self.scene().setBlend(self.scene().blend)
    
    
                    
        def clearValues(self):
            "THIS FUNCTION DOESNT WORK"
            self.values= {}
    
            if self.scene().cue==self and self.scene().isActive():
                self.scene().rerender=True    
                if (not universe in self.scene().cue_cached_alphas_as_arrays) and universe in module.universes and not value is None:
                    self.scene().cue_cached_vals_as_arrays[universe] = numpy.array([0.0]*len(module.universes[universe].values),dtype="f4")
                    self.scene().cue_cached_alphas_as_arrays[universe] = numpy.array([0.0]*len(module.universes[universe].values),dtype="f4")
                if universe in self.scene().cue_cached_alphas_as_arrays:
                    self.scene().cue_cached_alphas_as_arrays[universe][channel] = 1 if not value is None else 0
                    self.scene().cue_cached_vals_as_arrays[universe][channel] =  self.scene().evalExpr(value if not value is None else 0)
                if not universe in self.scene().affect:
                    self.scene().affect.append(universe)
    
                #The FadeCanvas needs to know about this change
                self.scene().render(force_repaint=True)
    
            #For blend modes that don't like it when you
            #change the list of values without resetting
            self.scene().setBlend(self.scene().blend)
            for i in module.boards:
                if len(i().newDataFunctions)<100:
                    i().newDataFunctions.append(lambda s:s.pushCueData(self.id))                
    
    class ClosedScene():
        pass
    
    class Scene():
        "An objecting representing one scene"
        def __init__(self,name=None, values=None, active=False, alpha=1, priority= 50, blend="normal",id=None, defaultActive=False,blendArgs=None,backtrack=True,defaultCue=True, syncKey=None, bpm=60, syncAddr="239.255.28.12", syncPort=1783, soundOutput='',notes='',page=None):
    
            "Not suggested to defaultCue==False, it's only there to avoid conflicts when loading saved cues"
            if name and name in module.scenes_by_name:
                raise RuntimeError("Cannot have 2 scenes sharing a name: "+name)
    
            if not name.strip():
                raise ValueError("Invalid Name")
    
            disallow_special(name)
            self.lock = threading.RLock()
    
            self.notes=notes
    
            if page and isinstance(page, str):
               page = {'html':page,'css':'','js':''}
    
            self.page=page or {'html':'','css':'','js':''}
    
    
            self.id = id or uuid.uuid4().hex
    
            
            #This is for the nice display screens you can embed in pages
            self.pageLink = kaithem.widget.APIWidget(id=self.id)
            self.pageLink.require("users.chandler.pageview")
    
            def c(u,cmd):
                if cmd[0]=='getvars':
                    for v in self.chandlerVars:
                        if v.startswith("pagevars."):
                            if isinstance(v, (str, int,float,bool)):
                                if isinstance(v,str):
                                    if len(v)>1024*512:
                                        continue
                                self.pageLink.send(["var", v.split(".",1)[1],self.chandlerVars[v]])
                if cmd[0]=='evt':
                    if not cmd[1].startswith("page."):
                        raise ValueError("Only events starting with page. can be raised from a scenepage")
                    self.event(cmd[1],cmd[2])
    
                if cmd[0]=="set":
                    if len(self.chandlerVars)>256:
                        if isinstance(cmd[2], (str, int,float,bool)):
                            if isinstance(cmd[2],str):
                                if len(cmd[2])>512:
                                    raise ValueError("Max 512 chars for val set from page")
                            self.ChandlerScriptContext.setVar("pagevars."+cmd[1],cmd[2])
    
            self.pageLink.attach(c)
    
            #Used to determine the numbering of added cues
            self.topCueNumber = 0
            #Only used for monitor scenes
            self.valueschanged = {}
            #Place to stash a blend object for new blending mode
            self._blend = None
            self.blendClass = None
            self.alpha = alpha if defaultActive else 0
            self.active = False
            self.defaultalpha = alpha
            self.name = name
            self.values = values or {}
            self.canvas = None
            self.backtrack = backtrack
            self.bpm = bpm
            self.soundOutput = soundOutput
    
            self.cue=None
    
            #Used for the tap tempo algorithm
            self.lastTap = 0
            self.tapSequence = 0
            
            #The list of cues as an actual list that is maintained sorted by number
            self.cues_ordered = []
            #This flag is used to avoid having to repaint the canvas if we don't need to
            self.fadeInCompleted = False
            #A pointer into that list pointing at the current cue. We have to update all this
            #every time we change the lists
            self.cuePointer = 0
    
            #Used for storing when the sound file ended. 0 indicates a sound file end event hasn't
            #happened since the cue started
            self.sound_end = 0
    
            self.cues = {}
            if defaultCue:
                self.cue = Cue(self,"default",self.values)
            
            #Used to avoid an excessive number of repeats in random cues
            self.cueHistory = []
    
            #List of universes we should be affecting.
            #Based on what values are in the cue and what values are inherited
            self.affect= []
       
            #Lets us cache the lists of values as numpy arrays with 0 alpha for not present vals
            #which are faster that dicts for some operations
            self.cue_cached_vals_as_arrays = {}
            self.cue_cached_alphas_as_arrays = {}
    
            self.rerenderOnVarChange = False
    
            #Set up the multicast synchronization
            self.pavillionc = None
            self.syncKey = syncKey
            self.syncPort = syncPort
            self.syncAddr = syncAddr
            if self.syncKey:
                self.pavillionSetup()
    
            self.enteredCue = 0
            
            #Map event name to runtime as unix timestamp
            self.runningTimers ={}
    
    
            self.priority = priority
            #Used by blend modes
            self.blendArgs = blendArgs or {}
            self.setBlend(blend)
            self.defaultActive = defaultActive
    
            #Used to indicate that the most recent frame has changed something about the scene
            #Metadata that GUI clients need to know about.
            self.hasNewInfo = {}
            
            #Set to true every time the alpha value changes or a scene value changes
            #set to false at end of rendering
            self.rerender = False
            
            #Last time the scene was started. Not reset when stopped
            self.started = 0
    
    
            self.chandlerVars = {}
    
            #The bindings for script commands that might be in the cue metadata
            self.scriptContext = None
    
    
            #List the active LivingNight influences
            self.influences = {}
    
            self.recalcLivingNight()
    
    
            import hashlib
    
            
            if name:
                   module.scenes_by_name[self.name] = self
            if not name:
                name = self.id
            module.scenes[self.id] = self
    
            if defaultCue:
                self.gotoCue('default',sendSync=False)
                pass
    
            if active:
                self.go()
                if isinstance(active, float):
                    self.started = module.timefunc()-active
    
        def __del__(self):
            try:
                self.pavillionc.close()
                self.pavillions.close()
            except:
                pass
    
    
        def close(self):
            "Unregister the scene and delete it from the lists"
            with module.lock:
                self.stop()
                if module.scenes_by_name.get(self.name,None) is self:
                    del module.scenes_by_name[self.name]
                if module.scenes.get(self.id,None) is self:
                    del module.scenes_by_name[self.id]
    
        def evalExpr(self,s):
            """Given A string, return a number if it looks like one, evaluate the expression if it starts with =, otherwise
                return the input.
    
                Given a number, return it.
    
                Basically, implements something like the logic from a spreadsheet app.
            """
            return self.scriptContext.preprocessArgument(s)    
    
        def pavillionSetup(self):
            if self.syncKey and not isinstance(self.syncKey,bytes) and not (len(self.syncKey)==32):
                bsynckey = base64.b64decode(self.syncKey)
                if not len(bsynckey)==32:
                    raise ValueError("Key must be 32 bytes, or 32 base64 encoded bytes")
            elif isinstance(self.syncKey,bytes) and len(self.syncKey)==32:
                bsynckey = self.syncKey
            else:
                raise ValueError("Key must be 32 bytes, or 32 base64 encoded bytes")
            self.bsynckey = bsynckey
    
            #Generate target from sync key, so you don't have to do it yourself
            msgtarget = hashlib.sha256(bsynckey).hexdigest()
            self.messagetargetstr = msgtarget
    
            try:
                self.pavillionc.close()
                self.pavillions.close()
            except:
                pass
    
    
            class Client(pavillion.Client):
                def onServerStatusUpdate(self, server):
                    with module.lock:
                        self.pushMeta()
    
            self.pavillions = pavillion.Server(keys={b'0'*16:bsynckey},port=self.syncPort,multicast=self.syncAddr, daemon=True)
            self.pavillions.setStatusReporting(True)
    
            self.pavillionc = pavillion.Client(psk=bsynckey, clientID=b'0'*16,address=(self.syncAddr, self.syncPort), daemon=True)
            self.pavillions.ignore[self.pavillionc.address]=True
    
    
            def f(name,data, client):
                if name =="cue":
                    data=data.decode("utf-8")
                    data = data.split("\n")
                    t = float(data[1])
    
                    #If the time matches, treat it as the "same" event that we don't need to handle again
                    if abs(t-self.enteredCue)<0.03:
                        return
                    #If the transition happened more than 5 seconds in the future, that doesn't make any sense
                    if t-module.timefunc()>5:
                        return
                    #If the transition happened more than 24h ago, ignore it.
                    if module.timefunc()-t>(3600*24):
                        return
                    
                    if data[0] in self.cues:
                        self.gotoCue(data[0],t,sendSync=False)
            self.msgtarget = self.pavillions.messageTarget(msgtarget,f)
    
    
        
        def recalcLivingNight(self):
            "This is called whenever a relevant change happens to LivingNight."
            with self.lock:
                if self.cue:
                    #When the cue changes we alsi
                    x = self.cue.influences
    
                    for i in self.influences:
                        if not i in x:
                            del self.influences[i]
    
                    for i in x:
                        if i in self.influences:
                            self.influences[i].update(x[i])
                        else:
                            self.influences[i]=module.lnInfluence(i,x[i])
    
    
        def insertSorted(self,c):
            with module.lock:
                self.cues_ordered.append(c)
                self.cues_ordered.sort(key=lambda i: i.number)
                try:
                    self.cuePointer = self.cues_ordered.index(self.cue)
                except:
                    pass
            #Regenerate linked list by brute force when a new cue is added.
            for i in range(len(self.cues_ordered)-1):
                self.cues_ordered[i].next_ll= self.cues_ordered[i+1]
            self.cues_ordered[-1].next_ll = None
    
        def getDefaultNext(self):
            try:
                return self.cues_ordered[self.cuePointer+1].name
            except:
                return None
        
    
        def getAfter(self,cue):
            x = self.cues[cue].next_ll
            return x.name if x else None
    
        def getParent(self,cue):
            "Return the cue that this cue name should inherit values from or None"
            with module.lock:
                if not self.cues[cue].track:
                    return None
                if self.cues[cue].inherit:
                    if self.cues[cue].inherit in self.cues and not self.cues[cue].inherit == cue:
                        return self.cues[cue].inherit
                    else:
                        return None
                
                #This is an optimization for if we already know the index
                if cue==self.cue.name:
                    v = self.cuePointer
                else:
                    v = self.cues_ordered.index(self.cues[cue])
    
                if not v==0:
                    x = self.cues_ordered[v-1]
                    if not x.nextCue or x.nextCue == cue:
                        return x.name
                return None
    
        def getAfter(self,cue):
            x = self.cues[cue].next_ll
            return x.name if x else None
    
        def rmCue(self,cue):
            with module.lock:
                if not len(self.cues)>1:
                    raise RuntimeError("Cannot have scene with no cues")
                if self.cue and self.name == cue:
                    try:
                        self.gotoCue("default")
                    except:
                        self.gotoCue(self.cues_ordered[0].name)
    
                if cue in cues:
                    id = cue
                    name = cues[id].name
                elif cue in self.cues:
                    name = cue
                    id = self.cues[cue].id
                self.cues_ordered.remove(self.cues[name])
    
                if cue in cues:
                    id = cue
                    del self.cues[cues[cue].name]
                elif cue in self.cues:
                    id = self.cues[cue].id
                    del self.cues[cue]
                for i in module.boards:
                    if len(i().newDataFunctions)<100:
                        i().newDataFunctions.append(lambda s:s.link.send(["delcue",id]))
                try:
                    self.cuePointer = self.cues_ordered.index(self.cue)
                except:
                    pass
            #Regenerate linked list by brute force when a new cue is added.
            for i in range(len(self.cues_ordered)-1):
                self.cues_ordered[i].next_ll= self.cues_ordered[i+1]
            self.cues_ordered[-1].next_ll = None
    
        def pushCues(self):
            for i in module.boards:
                if len(i().newDataFunctions)<100:
                    i().newDataFunctions.append(lambda s:pushCueList(i.id))
    
        def addCue(self,name,**kw):
            Cue(self,name,**kw)
    
        def _addCue(self,cue,prev=None,f=True):
            name = cue.name
            self.insertSorted(cue)
            if name in self.cues and not f:
                raise RuntimeError("Cue would overwrite existing.")
            self.cues[name] = cue
            if prev and prev in self.cues:
                self.cues[prev].nextCue= self.cues[name]
    
            for i in module.boards:
                if len(i().newDataFunctions)<100:
                    i().newDataFunctions.append(lambda s:s.pushCueMeta(self.cues[name].id))
            for i in module.boards:
                if len(i().newDataFunctions)<100:
                    i().newDataFunctions.append(lambda s:s.pushCueData(cue.id))
    
        def pushMeta(self,cue=False,statusOnly=False):
            #Push cue first so the client already has that data when we jump to the new display
            if cue:
                for i in module.boards:
                    if len(i().newDataFunctions)<100:
                        i().newDataFunctions.append(lambda s:s.pushCueMeta(self.cue.id))
    
            for i in module.boards:
                if len(i().newDataFunctions)<100:
                    i().newDataFunctions.append(lambda s:s.pushMeta(self.id,statusOnly=statusOnly))
    
        def event(self,s,value=None, info=''):
            #No error loops allowed!
            if not s=="script.error":
                self._event(s)
    
        
        def _event(self, s,value=None,info=''):
            "Manually trigger any script bindings on an event"
            with self.lock:
                try:
                    self.scriptContext.event(s)
                except Exception as e:
                    rl_log_exc("Error handling event")
                    print(traceback.format_exc(6))
                    
    
    
        def gotoCue(self, cue,t=None, sendSync=True,generateEvents=True):
            "Goto cue by name, number, or string repr of number"
            with module.lock:
    
                if self.canvas:
                    self.canvas.save()
    
                self.fadeInCompleted = False
                #There might be universes we affect that we don't anymore,
                #We need to rerender those because otherwise the system might think absolutely nothing has changed.
                #A full rerender on every cue change isn't the most efficient, but it shouldn't be too bad
                #since most frames don't have a cue change in them
                for i in self.affect:
                    if i in module.universes:
                        module.universes[i].full_rerender = True
    
                if cue == "__stop__":
                    self.stop()
                    return
    
                elif cue == "__random__":
                    for i in range(0,100 if len(self.cues)>2 else 1):
                        x = [i.name for i in self.cues_ordered]
                        for i in reversed(self.cueHistory):
                            if len(x)<3:
                                break
                            elif i in x:
                                x.remove(i)
                        cue = random.choice(x)
                        if not cue == self.cue.name:
                            break
    
                #Handle random selection option cues
                elif "|" in cue:
                    x = cue.split("|")
                    for i in reversed(self.cueHistory):
                        if len(x)<3:
                            break
                        elif i in x:
                            x.remove(i)
                    cue = random.choice(x).strip()
                    
                elif "*" in cue:
                    import fnmatch
                    x = []
    
                    for i in self.cues_ordered:
                        if fnmatch.fnmatch(i.name, cue):
                            x.append(i.name)
                    if not x:
                        raise ValueError("No matching cue for pattern: "+cue)
                                    
                    #Do the "Shuffle logic" that avoids  recently used cues.
                    #Eliminate until only two remain, the min to not get stuck in
                    #A fixed pattern. Sometimes allow three to mix things up more.
    
                    optionsNeeded = 2
                    for i in reversed(self.cueHistory):
                        if len(x)<=optionsNeeded:
                            break
                        elif i in x:
                            x.remove(i)
                    cue = random.choice(x)
    
                           
                if not cue in self.cues:
                    try:
                        c = float(cue)
                    except:
                        raise ValueError("No such cue "+str(cue))
                    for i in self.cues_ordered:
                        if i.number-(float(cue)*1000)<0.001:
                            cue = i.name
                            break
    
                
    
                cobj = self.cues[cue]
                
                if self.cue:
                    if cobj==self.cue:
                        if not cobj.reentrant:
                            return
                else:
                    #Act like we actually we in the default cue, but allow reenter no matter what since
                    #We weren't in any cue
                    self.cue = self.cues['default']    
                
                if not (cue==self.cue.name):
                    if generateEvents:
                        if self.active:
                            self.event("cue.exit", value=self.cue.name)
    
                
                
                if sendSync:
                    if self.pavillionc:
                        def f():
                            self.pavillionc.sendMessage(self.messagetargetstr,"cue", (cue+"\n"+str(t or module.timefunc())).encode("utf-8"))
                        kaithem.misc.do(f)
                self.cueHistory.append(cue)
                self.cueHistory = self.cueHistory[-100:]
                self.sound_end = 0
    
                #Allow specifying an "Exact" time to enter for zero-drift stuff
                self.enteredCue = t or module.timefunc()
    
                self.fadeout_start =False
    
               
    
    
    
                try:
                    #Take rules from new cue, don't actually set this as the cue we are in
                    #Until we succeed in running all the rules that happen as we enter
                    self.refreshRules(cobj)
                except:
                    rl_log_exc("Error handling script")
                    print(traceback.format_exc(6))
                
                if self.active:
                    if self.cue.onExit:
                        self.cue.onExit(t)
                    
    
    
                    if cobj.onEnter:
                        cobj.onEnter(t)
                    
                    if generateEvents:
                        self.event('cue.enter', cobj.name)
    
    
    
                #We don't fully reset until after we are done fading in and have rendered.
                #Until then, the affect list has to stay because it has stuff that prev cues affected.
                #Even if we are't tracking, we still need to know to rerender them without the old effects,
                #And the fade means we might still affect them for a brief time.
    
    
    
                cuevars = self.cues[cue].values.get("__variables__",{})
                for i in cuevars:
                    try:
                        self.scriptContext.setVar(i,self.evalExpr(cuevars[i]))
                    except:
                        print(traceback.format_exc())
                        rl_log_exc("Error with cue variable "+i)
    
                
                #When jumping to a cue that isn't directly the next one, apply and "parent" cues.
                #We go backwards until we find a cue that has no parent. A cue has a parent if and only if it has either
                #an explicit parent or the previous cue in the numbered list either has the default next cue or explicitly
                #references this cue.
                cobj = self.cues[cue]
    
                if self.backtrack and not cue == (self.cue.nextCue or self.getDefaultNext()) and cobj.track:
                    l = []
                    safety = 10000
                    x = self.getParent(cue)
                    while x:
                        #No l00ps
                        if x in l:
                            break
    
                        #Don't backtrack past the current cue for no reason
                        if x is self.cue:
                            break
    
                        l.append(self.cues[x])
                        x = self.getParent(x)
                        safety -= 1
                        if not safety:
                            break
    
                    for cuex in reversed(l):
                        self.cueValsToNumpyCache(cuex)
    
                
    
                #optimization, try to se if we can just increment if we are going to the next cue, else
                #we have to actually find the index of the new cue
                if self.cuePointer<(len(self.cues_ordered)-1) and self.cues[cue] is self.cues_ordered[self.cuePointer+1]:
                    self.cuePointer += 1
                else:
                    self.cuePointer = self.cues_ordered.index(self.cues[cue])
    
                        
                self.cue = self.cues[cue]
                
                kaithem.sound.stop(str(self.id))
                c = 0
                while c<50 and kaithem.sound.isPlaying(str(self.id)):
                    c+=1
                    time.sleep(0.017)
                if self.cue.sound and self.active:
    
                    sound = self.cue.sound
    
                    sound = self.resolveSound(sound)
    
                    if os.path.isfile(sound):
                        out = self.cue.soundOutput
                        if not out:
                            out = self.soundOutput
                        if not out:
                            out = None
                        print(self.id,self.alpha)
                        kaithem.sound.play(sound,handle=str(self.id),volume=self.alpha,output=out)
                        
                    else:
                        self.event("error", info="File does not exist: "+sound)
                
                self.recalcRandomizeModifier()
                self.recalcCueLen()
                
                self.cueValsToNumpyCache(self.cue, not self.cue.track)
        
                self.rerender = True
                self.pushMeta(statusOnly=True)
    
    
        def resolveSound(self, sound):
            #Allow relative paths
            if not sound.startswith("/"):
                for i in getSoundFolders():
                    if os.path.isfile(os.path.join(i,sound)):
                        sound = os.path.join(i,sound)
            if not sound.startswith("/"):
                sound = kaithem.sound.resolveSound(sound)
            return sound
    
        def recalcRandomizeModifier(self):
            "Recalculate the random variance to apply to the length"
            self.randomizeModifier =random.triangular(-self.cue.lengthRandomize, +self.cue.lengthRandomize)
    
        def recalcCueLen(self):
                "Calculate the actual cue len, without changing the randomizeModifier"
                cuelen = self.scriptContext.preprocessArgument(self.cue.length)
                
                if not isinstance(cuelen,(int, float)):
                        raise RuntimeError("Invalid cue length, must resolve to int or float")
    
                if self.cue.sound and self.cue.rel_length:
                    path = self.resolveSound(self.cue.sound)
                    try:
                        slen = TinyTag.get(path).duration+cuelen
                        self.cuelen=  max(0,self.randomizeModifier+slen)
                    except:
                        logging.exception("Error getting length for sound "+str(path))
                        self.cuelen = 0
    
                else: 
                    self.cuelen = max(0,self.randomizeModifier+cuelen)
    
    
        def recalcCueVals(self):
            self.cueValsToNumpyCache(self.cue, not self.cue.track)
    
        def cueValsToNumpyCache(self,cuex, clearBefore=False):
            """Apply everything from the cue to the fade canvas"""
            #Loop over universes in the cue
            if clearBefore:
                self.cue_cached_vals_as_arrays={}
                self.cue_cached_alphas_as_arrays={}
    
            for i in cuex.values:
                universe=mapUniverse(i)
                if not universe:
                    continue
    
                if not universe in module.universes:
                    continue
    
                if not universe in self.cue_cached_vals_as_arrays:
                    l = len(module.universes[universe].values)
                    self.cue_cached_vals_as_arrays[universe] = numpy.array([0.0]*l,dtype="f4")
                    self.cue_cached_alphas_as_arrays[universe] = numpy.array([0.0]*l,dtype="f4")
                    
                if not universe in self.affect:
                    self.affect.append(universe)
    
                self.rerenderOnVarChange=False
                    
                for j in cuex.values[i]:
                    cuev = cuex.values[i][j]
                    x = mapChannel(i, j)
                    if x:
                        universe, channel = x[0],x[1]
    
                    self.cue_cached_alphas_as_arrays[universe][channel] = 1.0 if not cuev==None else 0
                    try:
                        self.cue_cached_vals_as_arrays[universe][channel] = self.evalExpr(cuev if not cuev==None else 0)
                    except:
                        self.event("script.error", self.name+" cue "+cuex.name+" Val " +str((universe,channel))+"\n"+traceback.format_exc())
    
                    if isinstance(cuev, str) and cuev.startswith("="):
                        self.rerenderOnVarChange = True
    
    
        def refreshRules(self,rulesFrom=None):
            with module.lock:
    
                #We copy over the event recursion depth so that we can detct infinite loops
                if not self.scriptContext:
                    self.scriptContext = DebugScriptContext(rootContext,variables=self.chandlerVars,gil=module.lock)
    
                    self.scriptContext.addNamespace("pagevars")
    
                    self.scriptContext.scene = self.id
                    self.scriptContext.sceneObj = weakref.ref(self)
                    self.scriptContext.sceneName = self.name
    
                self.scriptContext.clearBindings()
    
                self.scriptContext.setVar("$scene", self.name)
                self.scriptContext.setVar("$cue", (rulesFrom or self.cue).name)
                self.runningTimers ={}
                
                if self.active:
                    ##Legacy stuff
                    if (rulesFrom or self.cue).script:
                        self.scriptContext.addBindings(parseCommandBindings((rulesFrom or self.cue).script))
                    #Actually add the bindings
                    self.scriptContext.addBindings((rulesFrom or self.cue).rules)
                    x = (rulesFrom or self.cue).inheritRules
                    while x and x.strip():
                        self.scriptContext.addBindings(self.cues[x].rules)
                        x = self.cues[x].inheritRules
    
                    self.scriptContext.startTimers()
    
                try:
                    for i in module.boards:
                        i().link.send(['scenetimers',self.id, self.runningTimers])
                except:
                    rl_log_exc("Error handling timer set notification")
                
    
        def nextCue(self,t=None):
            with module.lock:
                if self.cue.nextCue and ((self.cue.nextCue in self.cues) or self.cue.nextCue.startswith("__") or "|" in self.cue.nextCue or "*" in self.cue.nextCue):
                    self.gotoCue(self.cue.nextCue,t)
                elif not self.cue.nextCue:
                    x= self.getDefaultNext()
                    if x:
                        self.gotoCue(x,t)
    
        def setupBlendArgs(self):
            if hasattr(self.blendClass,"parameters"):
                for i in self.blendClass.parameters:
                    if not i in self.blendArgs:
                        self.blendArgs[i] = self.blendClass.parameters[i][3]
                    
    
        def go(self,nohandoff=False):
            with module.lock:
                if self in module.activeScenes:
                    return
                self.canvas = FadeCanvas()
    
                self.manualAlpha = False
                self.active =True
    
               
                if not self.cue:
                    self.gotoCue('default',sendSync=False)
                else:
                    #Re-enter cue to create the cache
                    self.gotoCue(self.cue.name)
                #Bug workaround for bug where scenes do nothing when first activated
                self.canvas.paint(self.cue, 0,vals=self.cue_cached_vals_as_arrays, alphas=self.cue_cached_alphas_as_arrays)
    
                self.enteredCue = module.timefunc()
    
                if self.blend in module.blendmodes:
                    self._blend = module.blendmodes[self.blend](self)
    
    
                self.effectiveValues = None
    
                self.hasNewInfo = {}
                self.started = module.timefunc()
    
    
    
                if not self in module._activeScenes:
                    module._activeScenes.append(self)
                module._activeScenes = sorted(module._activeScenes,key=lambda k: (k.priority, k.started))
                module.activeScenes = module._activeScenes[:]
               
                #Minor inefficiency rendering twice the first frame
                self.rerender = True
                #self.render()
    
            
            
        def isActive(self):
            return self.active
        
        def setPriority(self,p):
            self.hasNewInfo = {}
            self.priority = p
            with module.lock:
                module._activeScenes = sorted(module._activeScenes,key=lambda k: (k.priority, k.started))
                module.activeScenes = module._activeScenes[:]
                try:
                    for i in self.affect:
                        if i in module.universes:
                            module.universes[i].full_rerender = True
                except:
                    pass
    
        def setPage(self,page,style, script):
            self.page= {
                    'html':page,
                    'css': style,
                    'js': script
                }
            self.pageLink.send(['refresh'])
     
        def setName(self,name):
            disallow_special(name)
            if self.name=="":
                raise ValueError("Cannot name scene an empty string")
            if not isinstance(name, str):
                raise TypeError("Name must be str")
            with module.lock:
                if name in module.scenes_by_name:
                    raise ValueError("Name in use")
                if self.name in module.scenes_by_name:
                    del module.scenes_by_name[self.name]
                self.name = name
                module.scenes_by_name[name]=self
                self.hasNewInfo = {}
                self.scriptContext.setVar("$scene", self.name)
    
        def setBacktrack(self,b):
            b =bool(b)
            if self.backtrack == b:
                return
            else:
                self.backtrack = b
                x= self.enteredCue
                self.gotoCue(self.cue.name)
                self.enteredCue = x
                self.rerender=True
            self.hasNewInfo = {}
    
        def setBPM(self,b):
            b =float(b)
            if self.bpm == b:
                return
            else:
                self.bpm = b
                self.rerender=True
            self.hasNewInfo = {}
    
        def tap(self, t=None):
            "Do a tap tempo tap. If the tap happened earlier, use t to enter that time"
            t = t or module.timefunc()
    
            x= t-self.lastTap
    
            self.lastTap = t
    
            l = 60/self.bpm
            
            #More than 8s, we're starting a new tap tapSequence
            if x> 8:
                self.tapSequence = 0
    
    
            #If we are more than 5 percent off from where the beat is expected,
            #Start agaon
            if self.tapSequence> 1:
                if abs(x-l)> l*0.05:
                    self.tapSequence = 0
    
            if self.tapSequence:
                f = max((1/self.tapSequence)**2,0.0025)
                self.bpm = self.bpm*(1-f) + (60/(x))*f
            self.tapSequence+= 1
    
            l= 60/self.bpm
            ts = t-self.enteredCue
            beats =  ts/l
    
            fbeat = beats%1
            #We are almost right on where a beat would be, make a small phase adjustment
    
            #Back project N beats into the past finding the closest beat to when we entered the cue
            new_ts = round(beats)*l
            x = t-new_ts
    
            if (fbeat<0.1 or fbeat>0.90) and self.tapSequence:
                #Filter between that backprojected time and the real time
                #Yes I know we already incremented tapSequence
                f = 1/self.tapSequence**1.2
                self.enteredCue = self.enteredCue*(1-f) + x*f
            elif self.tapSequence:
                #Just change enteredCue to match the phase.
                self.enteredCue = x
            self.hasNewInfo = {}
    
    
        def stop(self):
            with module.lock:
                #No need to set rerender
                self.scriptContext.clearBindings()
                self.scriptContext.clearState()
                self._blend =None
                self.hasNewInfo = {}
                self.canvas = None
                
                try:
                    for i in self.affect:
                        if i in module.universes:
                            module.universes[i].full_rerender = True
                except:
                    pass
     
                self.affect = []
                if self in module._activeScenes:
                    module._activeScenes.remove(self)
                    module.activeScenes = module._activeScenes[:]
    
                self.active = False
                self.cue_cached_vals_as_arrays = {}
                self.cue_cached_alphas_as_arrays = {}
                kaithem.sound.stop(str(self.id))
    
                self.runningTimers.clear()
                self.cue=None
                try:
                    for i in module.boards:
                        i().link.send(['scenetimers',self.id, self.runningTimers])
                except:
                    rl_log_exc("Error handling timer set notification")
                    print(traceback.format_exc())
                
    
    
            
        def setAlpha(self,val,sd=False):
            kaithem.sound.setvol(val, str(self.id))
            self.rerender = True
            
            if not self.isActive():
                self.go()
            self.manualAlpha = True
            self.alpha = val
            if sd:
                self.defaultalpha = val
            self.hasNewInfo = {}
    
        def setSyncKey(self, key):
            if key and not isinstance(key,bytes) and not (len(key)==32):
                bsynckey = base64.b64decode(key)
                if not len(bsynckey)==32:
                    self.hasNewInfo = {}
                    raise ValueError("Key must be 32 bytes, or 32 base64 encoded bytes")
    
            elif isinstance(keyy,bytes) and len(key)==32:
                key = base64.b64encode(key)
            else:
                self.hasNewInfo = {}
                raise ValueError("Key must be 32 bytes, or 32 base64 encoded bytes")
    
    
            with self.lock:
                self.syncKey = key
                self.hasNewInfo = {}
                self.pavillionSetup()
                
    
        def setSyncAddress(self, addr):
            with self.lock:
                self.syncAddr = addr
                self.pavillionSetup()
                self.hasNewInfo = {}
        
        def setSyncPort(self, port):
            with self.lock:
                self.syncPort = port
                self.pavillionSetup()
                self.hasNewInfo = {}
    
    
        
        def addCue(self,name,**kw):
            return Cue(self,name,**kw)
    
        def setBlend(self,blend):
            disallow_special(blend)
            blend=str(blend)[:256]
            self.blend= blend
            if blend in module.blendmodes:
                if self.isActive():
                    self._blend = module.blendmodes[blend](self)
                self.blendClass = module.blendmodes[blend]
                self.setupBlendArgs()
            else:
                self.blendArgs = self.blendArgs or {}
                self._blend = None
                self.blendClass = None
            self.rerender = True
            self.hasNewInfo = {}
    
        def setBlendArg(self,key,val):
            disallow_special(key,"_")
            #serializableness check
            json.dumps(val)
            if not hasattr(self.blendClass,"parameters") or not key in self.blendClass.parameters:
                raise KeyError("No such param")
    
            if val is None:
                del self.blendArgs[key]
            else:
                if self.blendClass.parameters[key][1] == "number":
                    val= float(val)
                self.blendArgs[key] = val
            self.rerender = True
            self.hasNewInfo = {}
    
            
        def clearValue(self,universe,channel):
            self.rerender = True
            try:
                del self.values[universe][channel]
                if not self.values[universe]:
                    x = self.values[universe]
                    del self.values[universe]
                    #Put it back if there was a write from another thread. Prob
                    #still not totally threadsafe
                    if x:
                        self.values[universe] =x
            except:
                pass
            self.valueschanged = {}
            
       
    
        
        def render(self,force_repaint=False):
            "Calculate the current alpha value, handle stopping the scene and spawning the next one"
            if self.cue.fadein:
                fadePosition = min((module.timefunc()-self.enteredCue)/(self.cue.fadein*(60/self.bpm)),1)
            else:
                fadePosition = 1
    
            if fadePosition<1:
                self.rerender = True
    
    
            if self.cue.length and(module.timefunc()-self.enteredCue)> self.cuelen*(60/self.bpm):
                #rel_length cues end after the sound in a totally different part of code
                #Calculate the "real" time we entered, which is exactly the previous entry time plus the len.
                #Then round to the nearest millisecond to prevent long term drift due to floating point issues.
                self.nextCue(round(self.enteredCue+self.cuelen*(60/self.bpm),3))
            else:
                if force_repaint or not self.fadeInCompleted:
                    self.canvas.paint(self.cue, fadePosition,vals=self.cue_cached_vals_as_arrays, alphas=self.cue_cached_alphas_as_arrays)
                    
                    if fadePosition >= 1:
    
                        #Check if there could be effects from other cues
                        if not self.cue.track:
                            #We no longer affect universes from anything else
                            self.affect = []
                            for i in self.cue.values:
                                i = mapUniverse(i)
                                if i in module.universes:
                                    if not i in self.affect:
                                        self.affect.append(i)
    
                            #Remove unused universes from the cue
                            self.canvas.clean(self.cue.values)
    
                        self.fadeInCompleted = True
                        self.rerender=True
    
        def updateMonitorValues(self):
            if self.blend == "monitor":
                data =  self.cue.values
                for i in data:
                    for j in data[i]:
                        x = mapChannel(i,j)
                        if x:
                            if x[0] in module.universes:
                                v = module.universes[x[0]].values[x[1]]
                                self.cue.values[i][j] = float(v)
                self.valueschanged={}
    
    def event(s,value=None, info=''):
        #disallow_special(s, allow=".")
        with module.lock:
            for i in module.activeScenes:
                i._event(s, value=value, info=info)
    
    
    lastrendered = 0
    
    module.Board = ChandlerConsole
    
    module.board =ChandlerConsole()
    module.boards.append(weakref.ref(module.board))
    module.Scene = Scene
    
    kaithem.chandler.board = module.board
    kaithem.chandler.Scene = module.Scene
    kaithem.chandler.scenesByUUID = module.scenes
    kaithem.chandler.scenes = module.scenes_by_name
    kaithem.chandler.Universe = Universe
    kaithem.chandler.blendmodes = module.blendmodes
    kaithem.chandler.fixture = Fixture
    kaithem.chandler.shortcut = shortcutCode
    
    kaithem.chandler.commands = rootContext.commands
    kaithem.chandler.event = event
    
    
    module.controluniverse = module.Universe("control")
    module.varsuniverse = module.Universe("__variables__")

def eventAction():
    with module.lock:
        render()
    global lastrendered
    if module.timefunc() -lastrendered > 1/48.0:
        with module.lock:
            pollsounds()
        with boardsListLock:
            for i in module.boards:
                b = i()
                if b:
                    b.guiPush()
                del b
        lastrendered = module.timefunc()
