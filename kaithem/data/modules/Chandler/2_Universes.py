## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1639228690537979
resource-type: event
versions: {}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    import numpy, time, threading, weakref, socket,logging,traceback,gc,copy,struct
    
    logger = logging.getLogger("system.chandler")
    
    
    universesLock = threading.RLock()
    
    #Iterable, made from a copy of universes
    module.universes={}
    
    #MUTABLE
    _universes={}
    
    
    
    class Universe():
        "Represents a lighting universe, similar to a DMX universe, but is not limited to DMX. "
        def __init__(self, name,count=512,number=0):
            for i in ":/[]()*\\`~!@#$%^&*=+|{}'\";<>.,":
                if i in name:
                    raise ValueError("Name cannot contain special characters except _")
            self.name = name
    
            self.hidden=True
    
            #If local fading is disabled, the rendering tries to compress everything down to a set of fade commands.
            #This is the time at which the current fade is supposed to end.
            self.fadeEndTime = 0
    
            #If False, lighting values don't fade in, they just jump straight to the target,
            #For things like smart bulbs where we want to use the remote fade instead.
            self.localFading = True
            
            #Used by blend modes to request that the
            #remote device do onboard interpolation
            #The longest time requested by any layer is used
            #The final interpolation time is the greater of
            #This and the time determined by fadeEndTime
            self.interpolationTime=0
            
            #Let subclasses set these
            if not hasattr(self,"status"):
                self.status = "normal"
            if not hasattr(self,"ok"):
                self.ok = True
    
            
            # name:weakref(fixture) for every ficture that is mapped to this universe
            self.fixtures = {}
    
            #Represents the telemetry data back from the physical device of this universe.
            self.telemetry = {}
    
            #Dict of all board ids that have already pushed a status update
            self.statusChanged = {}
            self.channels = {}
    
            #Maps names to numbers, mostly for tagpoint universes.
            if not hasattr(self,"channelNames"):
                self.channelNames={}
    
            self.groups ={}
            self.values = numpy.array([0.0]*count,dtype="f4")
            self.alphas = numpy.array([0.0]*count,dtype="f4")
    
            
            #These channels should blend like Hue, which is normal blending but
            #There's no "background" of zeros. If there's nothing "behind" it, we consider it
            #100% opaque
            #Type is bool
            self.hueBlendMask = numpy.array([0.0]*count,dtype="?")
    
    
            self.count = count
            #Maps fine channel numbers to coarse channel numbers
            self.fine_channels = {}
            #Used for the caching. It's the layer we want to save as the background state before we apply.
            #Calculated as either the last scene rendered in the stack or the first scene that requests a rerender that affects the universe
            self.save_before_layer = (0,0)
            #Reset in pre_render, indicates if we've not rendered a layer that we think is going to change soon
            #so far in this frame
            self.all_static = True
            with module.lock:
                with universesLock:
                    if name in _universes and _universes[name]():
                        gc.collect()
                        time.sleep(0.1)
                        gc.collect()
                        #We retry, because the universes are often temporarily cached as strong refs
                        if name in _universes and _universes[name]():
                            try:
                                _universes[name]().close()
                            except:
                                raise ValueError("Name "+name+ " is taken")
                    _universes[name] = weakref.ref(self)
                    module.universes = {i:_universes[i] for i in _universes if _universes[i]()}
                
                        
            #flag to apply all scenes, even ones not marked as neding rerender
            self.full_rerender = False
            
            #The priority, started of the top layer layer that's been applied to this scene.
            self.top_layer= (0,0)
    
            #This is the priority, started of the "saved" layer that's been cached so we don't
            #Have to rerender it or anything below it.
            self.prerendered_layer= (0,0)
    
    
            #A copy of the state of the universe just after prerendered_layer was rendered, so we can go back
            #and start from there without rerendering lower layers.
    
            #The format is values,alphas
            self.prerendered_data= ([0.0]*count,[0.0]*count)
            
            #Maybe there might be an iteration error. But it's just a GUI convienence that
            #A simple refresh solves, so ignore it.
            try:
                for i in module.boards:
                    i().pushUniverses()
            except Exception as e:
                print(e)
            
            kaithem.message.post("/chandler/command/refreshFixtures", self.name)
            self.refresh_scenes()
    
    
        def __del__(self):
            self.close()
    
        def close(self):
            with universesLock:
                #Don't delete the object that replaced this
                if self.name in _universes and (_universes[self.name]() is self):
                    del _universes[self.name]
    
                module.universes = {i:_universes[i] for i in _universes if _universes[i]()}
              
                
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
            kaithem.message.post("/chandler/command/refreshScenes",None)
    
        def __del__(self):
            #Do as little as possible in the undefined __del__ thread
            kaithem.message.post("/chandler/command/refreshScenes",None)
    
                
        def channelsChanged(self):
            "Call this when fixtures are added, moved, or modified."
            with module.lock:
                self.fine_channels = {}
                for i in self.channels:
                    fixture = self.channels[i]()
                    if not fixture:
                        continue
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
            values,alphas = self.prerendered_data
            self.values = copy.deepcopy(values)
            self.alphas = copy.deepcopy(alphas)
            
            self.top_layer = self.prerendered_layer
        
        def save_prerendered(self, p, s):
            "Save this layer as the cached layer. Called in the render functions"
            self.prerendered_layer = (p,s)
            self.prerendered_data  = (copy.deepcopy(self.values),copy.deepcopy(self.alphas))
        
        def reset(self):
            "Reset all values to 0 including the prerendered data"
            self.prerendered_layer = (0,0)
            self.values = numpy.array([0.0]*self.count,dtype="f4")
            self.alphas = numpy.array([0.0]*self.count,dtype="f4")
    
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
        data = data.tobytes()[1:513]
        return (b'\x7e\x06'+struct.pack('<H',len(data))+data+b'\xe7')
    
    
    def rawmessage(data):
        "An enttec open DMX message from a set of values"
        data = numpy.maximum(numpy.minimum(data,255),0)
        data = data.astype(numpy.uint8)
        data = data.tobytes()[1:513]
        #Remove the 0 position as DMX starts at 1
        return (b'\0'+data)
    
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
            self.sender = makeSender(DMXSender,weakref.ref(self),portname,framerate)
            self.sender.connect()
            
            Universe.__init__(self,name,channels)
    
            self.hidden=False
    
        def onFrame(self):
            data = message(self.values)
            self.sender.onFrame(data)
    
        def __del__(self):
            #Stop the thread when this gets deleted
            self.sender.onFrame(None)
    
    
    class DMXSender():
        """This object is used by the universe object to send data to the enttec adapter.
            It runs in it's own thread because the frame rate might have nothing to do with
            the rate at which the data actually gets rendered.
        """
        def __init__(self,universe,port,framerate):
            self.frame = threading.Event()
            self.universe= universe
            self.data = message(universe().values)
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
    
    
        def reconnect(self,portlist=None):
            "Try to reconnect to the adapter"
            try:
                import serial
                if not self.portname:
                    import serial.tools.list_ports
    
                    p = portlist or serial.tools.list_ports.comports()
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
                        print("Attempting reconnect")
                        #I don't remember why we retry twice here. But reusing the port list should reduce CPU a lot.
                        time.sleep(3)
                        import serial
                        portlist= serial.tools.list_ports.comports()
                        #reconnect is designed not to raise Exceptions, so if there's0
                        #an error here it's probably because the whole scope is being cleaned
                        self.reconnect(portlist)
                        time.sleep(3)
                        self.reconnect(portlist)
                        time.sleep(1)
                    except:
                        print("Sender thread exiting")
                        print(traceback.format_exc())
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
            self.sender = makeSender(ArtNetSender,weakref.ref(self),addr,port,framerate,scheme)
            
            Universe.__init__(self,name,channels)
    
            self.hidden=False
    
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
            self.hidden=False
            
            self.channelNames={}
            #Put a claim on all the tags
            for i in self.tagpoints:
                #One higher than default
                try:
                    if not i.strip():
                        continue
    
                    x = i.split(':')
    
                    chname=''
                    try:
                        num = int(x[0].strip())
                    except:
                        num = len(self.claims)+1
                        chname = x[0].strip()
                    
                    if len(x)==2:
                        chname = x[1].strip()
                    else:
                        if not chname:
                            chname = 'tp'+str(num)
                    
                    tpn = self.tagpoints[i]
                    if tpn:
                        self.claims[num]= kaithem.tags[tpn].claim(0,"Chandler_"+name,  50 if number < 2 else number)
                        self.channelNames[chname]=num
                        
                except Exception as e:
                    self.status="error, "+i+" "+ str(e)
                    logger.exception("Error related to tag point "+i)
                    print(traceback.format_exc())
                    event("board.error",traceback.format_exc())
    
            #Sender needs the values to be there for setup
            self.values = numpy.array([0.0]*channels,dtype="f4")
            
            Universe.__init__(self,name,channels)
    
    
        def onFrame(self):
            for i in self.claims:
                try:
                    x = float(self.values[i])
                    if x>-1:
                        self.claims[i].set(x)
                except:
                    rl_log_exc("Error in tagpoint universe")
                    print(traceback.format_exc())
    
    
    
    def makeSender(c,uref,*a):
        return c(uref,*a)
    
    
    class ArtNetSender():
        """This object is used by the universe object to send data to the enttec adapter.
            It runs in it's own thread because the frame rate might have nothing to do with
            the rate at which the data actually gets rendered.
        """
        def __init__(self,universe,addr,port,framerate,scheme):
            self.frame = threading.Event()
            self.scheme=scheme
    
    
            self.universe=universe
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
    
    
    
    
    
    
    
    
    class EnttecOpenUniverse(Universe):
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
            self.sender = makeDMXSender(weakref.ref(self),portname,framerate)
            self.sender.connect()
            
            Universe.__init__(self,name,channels)
    
            self.hidden=False
    
        def onFrame(self):
            data = rawmessage(self.values)
            self.sender.onFrame(data)
    
        def __del__(self):
            #Stop the thread when this gets deleted
            self.sender.onFrame(None)
    
    
    def makeDMXSender(uref, port, fr):
        return RawDMXSender(uref,port, fr)
    
    class RawDMXSender():
        """This object is used by the universe object to send data to the enttec adapter.
            It runs in it's own thread because the frame rate might have nothing to do with
            the rate at which the data actually gets rendered.
        """
        def __init__(self,universe,port,framerate):
            self.frame = threading.Event()
            self.data = rawmessage(universe().values)
            self.universe= universe
    
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
                self.port = serial.Serial(p,baudrate=250000, timeout=1.0, write_timeout=1.0,stopbits=2)
    
       
                self.port.read(self.port.inWaiting())
                time.sleep(0.05)
                self.port.break_condition=True
                time.sleep(0.0001)
                self.port.break_condition=False
                time.sleep(0.0003)
                self.port.write(self.data)
                self.port.flush()
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
                    x =self.frame.wait(0.1)
                    with self.lock:
                        if self.data is None:
                            try:
                                self.port.close()
                            except:
                                pass
                            return
                        
                        self.port.break_condition=True
                        time.sleep(0.0001)
                        self.port.break_condition=False
                        time.sleep(0.0003)
    
                        self.port.write(self.data)
                        if x:
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
    
    
    
    class BulbCommand():
        pass
    
    class HSVSmartBulbUniverse(Universe):
        #Thanks to https://github.com/c0z3n/pySimpleDMX
        #I didn't actually use the code, but it was a very useful resouurce
        #For protocol documentation.
        def __init__(self,name,channels=128,portname="",framerate=44,number=0):
            self.ok = False
            self.number=number
            self.status = "Disconnect"
            self.statusChanged = {}
            #Limit framerate to protect flash memory, and bandwidth
            self.framerate = min(framerate,12)
            self.portname=portname
            #Sender needs the values to be there for setup
            self.values = numpy.array([0.0]*channels,dtype="f4")
            self.lock = threading.Lock()
    
            Universe.__init__(self,name,channels)
    
            self.hidden=False
    
            self.lastSend = time.monotonic()
            self.finishedSending = True
            self.awaitingSend = False
    
            #This universe always has exactly one fixture on it, and we auto create that fixture.
            self.assignDefaultFixture()
            self.lastPostedErr=0
            self.localFading=False
    
            self.lastCommand=(0,0,-1)
            self.lastSendTime = 0
    
        def assignDefaultFixture(self):
            self.f = module.Fixture(self.name,[['hue','hue'],['sat','sat'],['val','dim']])
            self.f.assign(self.name, 1)
    
        def getHSV(self):
            return ((self.values[1]/255)*360), (self.values[2]/255), (self.values[3]/255)
    
    
        def onFrame(self):
       
            
            c = BulbCommand()
            h,s,v = self.getHSV()
            t = max(self.fadeEndTime-module.timefunc(), self.interpolationTime,0)
            
            self.cmd=(h,s,v,t)
            
            def sendFunction():
                while self.finishedSending==False:
                    self.awaitingSend=True
                    time.sleep(1/self.framerate)
                with self.lock:
                    self.awaitingSend=False
    
                self.finishedSending=False
                try:
                    try:
                        if self.cmd==self.lastCommand:
                            if self.lastSendTime> time.monotonic()-0.3:
                                return
                        self.lastSendTime=time.monotonic()
                        self.lastCommand =self.cmd
                        if self.portname in kaithem.devices:
                            kaithem.devices[self.portname].setHSV(0,*self.cmd)
                        else:
                            self.setStatus("No device",False)
                        self.setStatus("OK",True)
                    except:
                        self.setStatus("Failed to send",False)
                        if self.lastPostedErr< time.monotonic()-(60*5):
                            kaithem.chandler.event("board.error",self.name+"\n"+traceback.format_exc(chain=True))
                            self.lastPostedErr=time.monotonic()
                finally:        
                    self.finishedSending = True
    
            with self.lock:
                if not self.awaitingSend:
                    kaithem.misc.do(sendFunction)
            
    
    class RGBSmartBulbUniverse(HSVSmartBulbUniverse):
        def getHSV(self):
            c=(self.values[0]/255, self.values[1]/255, self.values[2]/255)
    
            return (c[0]*360,c[1],c[2])
            
        def assignDefaultFixture(self):
            self.f = module.Fixture(self.name,[['red','red'],['green','green'],['blue','blue']])
            self.f.assign(self.name, 1)
    
    
    module.Universe = Universe
    module.EnttecUniverse = EnttecUniverse
    module.EnttecOpenUniverse = EnttecOpenUniverse
    module.TagpointUniverse = TagpointUniverse
    module.ArtNetUniverse = ArtNetUniverse
    module.HSVSmartBulbUniverse = HSVSmartBulbUniverse
    module.RGBSmartBulbUniverse = RGBSmartBulbUniverse

def eventAction():
    pass
