from src.devices import *

try:
    import pavillion
except:
    #The re-attempt will raise an error if anyone tries 
    #To actually use this stuff.
    pass

k4dlogger = logging.getLogger("system_k4d_errors")

#Indexed by module,resource tuples
loadedSquirrelPrograms = {}

def sqminify(code):
    line = ''
    lines = []
    quote = False
    for i in code:
        if not quote and i=='\n':
            lines.append(line)
            line = ''
        else:
            line+= i
        if i=='"':
            quote = not quote
    lines+= [line]
    olines =[]
    for i in lines:
        x = i.strip()
        if x.startswith("\\") or x.startswith("#"):
            continue
        if not x:
            continue
        
        #Pretty sure two statements like this can just be put together
        if olines and olines[-1][-1] in ";}{" and x[-1] in ";}{":
            olines[-1]+=x
            continue
        #Put closing bracket on the line
        if olines and x[0] =="{":
            olines[-1]+=x
            continue
        olines.append(x)
    return("\n".join(olines))

class RemoteSquirrelProgram():
    def __init__(self, module,resource, data):
        self.target = data['device']
        self.code = data['code']
        self.prgid=data['prgid']
        self.errors = []
        self.print = ""
        self.module = module
        self.resource = resource


    def getPreprocessedCode(self,code=None,minify=True):
        code = code or self.code
        x = {"kaithem":kaithemobj.kaithem, "module":modules_state.scopes[self.module]}
        code =  mako.template.Template(code, uri="SquirrelTemplate"+self.module+'_'+self.resource, global_vars=x)
        code = code.render(**x)
        if minify:
            code = sqminify(code)
        code = "//"+(base64.b64encode(hashlib.sha256(code.encode("utf8")).digest()).decode("utf8"))[:14]+"\n"+ code
        return code

    def upload(self):
        if self.target in remote_devices:
            d = remote_devices[self.target]
         
            d.loadProgram(self.prgid, self.getPreprocessedCode(),self)

    def unload(self):
        if self.target in remote_devices:
            d = remote_devices[self.target]
            d.forceClose(self.prgid)


def removeProgram(module,resource):
    with lock:
        if (module, resource) in loadedSquirrelPrograms:
            loadedSquirrelPrograms[module,resource].unload()
            del loadedSquirrelPrograms[module,resource]


def loadProgramsFromModules():
    from .modules import ActiveModules
    for module in ActiveModules:
        for i in ActiveModules[module]:
            if ActiveModules[module][i]['resource-type'] == 'k4dprog_sq':
                from src import pavilliondevices
                updateProgram(module, i, ActiveModules[module][i])


class PavillionDevice(Device):
    deviceTypeName="pavillion"
    
    @staticmethod
    def validateData(data):
        data['port'] = int(data['port'])


    def close(self):
        Device.close(self)
        try:
            self.pclient.close()
        except:
            pass
    onPavillionConnect =None


    def handleIncomingTagValue(self, value, good_ts, timestamp, name,tag,raw_timestamp,server):
        """
            Conflict resolution and possibly pushing local value to them.
            timesamp must be in the local sytem monotnic scale
            good_ts indicates if that timestamp is actually valid and synced with the remote.

            The conflic resolution logic shouldn't be trusted completely. You may get some glitches
            with bidirectional tags if it makes an incorrect decision about what is new.
        """
        if not "test" in name:
            print(timestamp, raw_timestamp, tag.timestamp,tag.remote_writable)
        if good_ts:
            if ((timestamp>tag.timestamp) and (tag.currentSource=="shared"))  or not (tag.remote_writable):
                #if we have old data, or if it's a read only
                #Tag and we shouldn't try to do conflic resolution anyway

                #However, if the source is not the shared claim, we assume
                #a higher priority claim is in effect and we don't even bother
                #resolving with timestamps.


                #Because sync isn't perfect, we also filter by not accepting the same timestamp from the remote
                #Twice in a row.
                if not(tag.lastRemoteTs==raw_timestamp):
                    self.tagClaims[name].set(value,timestamp,"DoNotSend")
            else:
                #Local data is newer, push it!
                try:
                    t = int(server.toRemoteMonotonic(tag.timestamp)*10**6)
                except:
                    print(traceback.format_exc())
                    t=tag.lastRemoteTs+1
                    tag.lastRemoteTs+=1

                self.pclient.sendMessage("core.tagv", name,struct.pack("<fq",tag.value,int(t)))
            
        else:
            #No time sync. So we use a simpler rule. If it's writable, write it.
            #Almost all tags will not be bidirectional i suspect.

            #But even then we can do a bit more, we can reject timestamps
            #That are identiical to what we already saw, and catch a large number of the repeats.
            if (tag.remote_writable) and not(tag.lastRemoteTs==raw_timestamp):
                try:
                    t = int(server.toRemoteMonotonic(tag.timestamp)*10**6)
                except:
                    #Guess at something higher than what they sent
                    t=raw_timestamp+1000
                    tag.lastRemoteTs=raw_timestamp+1000
                self.pclient.sendMessage("core.tagv", name,struct.pack("<fq",tag.value,int(t)))
            else:
                #Tag isn't writable, we accept their value
                self.tagClaims[name].set(value,timestamp,"DoNotSend")
        
        tag.lastRemoteTs = raw_timestamp


    def __init__(self, name, data):
        import pavillion
        Device.__init__(self,name,data)
        self.pclient=None
        self.recievelock=threading.Lock()
        self.lastError = 0

        self.k4dprint = []
        self.k4derr = []
        self.loaded = weakref.WeakValueDictionary()
        self.lock = threading.RLock()

        self.batteryStatusTag = None
        connectionTag = tagpoints.Tag("/devices/"+name+".rssi")
        connectionTag.min =-100
        connectionTag.max = 20

        self.connectionTag = connectionTag
        self.connectionType = "error"
        self.batteryState = "unknown"

        if not 'address' in data:
            self.handleError("No address specified")
            return
        
        if not 'port' in data:
            self.handleError("No port specified")
            return

        if not 'psk' in data:
            self.handleError("No psk specified")
            return

        if not 'cid' in data:
            self.handleError("No client ID specified")
            return

        self.connectionType = "unknown"



        self.psk = data['psk']

        if len(data['cid'])==32:
            self.cid = bytes.fromhex(data['cid'])
        else:
            self.cid = data['cid'].encode("utf-8")

        self.pubkey = data.get('pubkey',None)
        self.privkey = data.get('privkey',None)
        self.server_pubkey = data.get('server_pubkey', None)


        self.connectionTagClaim = connectionTag.claim(0,"reported",51)
        
        self.batteryStatusClaim =None

        #This alert monitors low battery.
        self.lowBatteryAlert = alerts.Alert("/devices/"+name+".lowsignalalert")


        #If the WiFi signal gets crappy.
        self.lowSignalAlert   = alerts.Alert("/devices/"+name+".lowsignalalert",tripDelay=80,autoAck=True)
        self.unreachableAlert = alerts.Alert("/devices/"+name+".lowsignalalert",tripDelay=5,autoAck=True)

        self.alerts={
            "unreachableAlert":self.unreachableAlert,
            "lowSignalAlert": self.lowSignalAlert,
            "lowBatteryAlert": self.lowSignalAlert,
        }

        DeviceObject = self
        #Has to be here so it doesn't mess everything else
        #up if we can't import Pavillion
        class Client2(pavillion.Client):
            def __init__(self, cb, *a,**k):
                self.connectCB = cb
                import pavillion
                pavillion.Client.__init__(self, *a,**k)
            def onServerConnect(self, addr, pubkey):
                #That lint error is fine
                if self.connectCB:
                    workers.do(self.connectCB)
            def onServerStatusUpdate(self,server):
                DeviceObject.batteryState = server.batteryState()
                if not server.batteryState() =='unknown':
                    blevel = server.battery()
                    if blevel<15:
                        DeviceObject.lowBatteryAlert.trip()
                    elif blevel>35:
                        DeviceObject.lowBatteryAlert.clear()

                    #We create it the first time we actually get a battery status report
                    if not DeviceObject.batteryStatusTag:
                        #here's a tagpoint for the battery level
                        DeviceObject.batteryStatusTag = tagpoints.Tag("/devices/"+name+".battery")
                        DeviceObject.batteryStatusTag.min=1
                        DeviceObject.batteryStatusTag.max=100
                    if not DeviceObject.batteryStatusClaim:
                        DeviceObject.batteryStatusClaim = DeviceObject.batteryStatusTag.claim(blevel,"reported",51)
                    DeviceObject.batteryStatusClaim.set(blevel)

                DeviceObject.netType =server.netType()
                if server.netType() in ('wwan','wlan'):
                    DeviceObject.connectionTagClaim.set(server.rssi())
                    if server.rssi()<-89:
                        DeviceObject.lowSignalAlert.trip()
                    else:
                        DeviceObject.lowSignalAlert.clear()
                #Doesn't really apply to non wireless
                else:
                    #We have a tag for every pavillion device because we assume they
                    #Can roam to wireless because some can. On wired we set RSSI to the max
                    DeviceObject.connectionTagClaim.set(20)
                    DeviceObject.lowSignalAlert.clear()
                DeviceObject.unreachableAlert.clear()
        #This client is passed a callback to autoload all new code onto the device upon connection
        self.pclient = Client2(self.onPavillionConnect, clientID=self.cid,psk=self.psk, address=(data['address'],data['port']))


        def handle_print(name, data, source):
            data= data.decode("utf8")
            with lock:
                try:
                    self.loaded[name].print+= data
                    self.loaded[name].print = self.loaded[name].print[-4096:]
                except Exception as e:
                    print(e)

        def handle_error(name, data, source):
            data= data.decode("utf8")
            with self.recievelock:
                self.k4derr.append((name, data,time.time()))
                self.k4derr = self.k4derr[-256:]
            with lock:
                try:
                    self.loaded[name].errors+= [data, time.time()]
                    self.loaded[name].errors = self.loaded[name].errors[4096:]
                except:
                    k4dlogger.exception("Error logging the error")
            k4dlogger.error("Error in remote progam "+name+":\r\n"+data)
        
        self._handlerror = handle_error
        self._handleprint=handle_print

        #K4d stuff is different for messages from the device itsewkf because it's from
        #A specific program
        self.t = self.pclient.messageTarget("k4dprint",handle_print)
        self.t2 = self.pclient.messageTarget("k4derr",handle_error)
    

        def genericMessage(target,name,data,source):
            try:
                kaithemobj.kaithem.message.post("/devices/"+self.name+"/msg/"+target,(name,data,source))
                if target=="core.print":
                    self.messages.append(time.time(),name, data.decode('utf8'),source)

                elif target=="core.tagv":
                    value, raw_timestamp = struct.unpack("<fq",data)
                    timestamp=raw_timestamp/10**6
                    try:
                        localized_timestamp = self.pclient.getServer().toLocalMonotonic(timestamp)
                        good_ts = True
                    except:
                        print("nooooooooope")
                        good_ts = False
                        localized_timestamp=time.monotonic()
                    print("tagv", value, source)
                    server=self.pclient.getServer(source)
                    #Do the more advanced conflict resolution logic.
                    self.handleIncomingTagValue(value, good_ts,localized_timestamp, name, self.tagPoints[name],timestamp,server)

                
                elif target=="core.tag":
                    #These messages contain pretty much the complete tag state,
                    #We use them to init new tags
                    value, min,max,interval,flags,raw_timestamp = struct.unpack("<ffffBq",data)
                    
                    ##We do this whole thing every time we get this message.
                    ##It's up to them not to waste out time sending it a lot
                    with self.lock:
                        timestamp=raw_timestamp/10**6
                        try:
                            ts = self.pclient.getServer().toLocalMonotonic(timestamp)
                            good_ts = True
                        except:
                            good_ts=False
                            ts=time.monotonic()

                        t = self.tagPoints.copy()
                        t[name]=tagpoints.Tag("/devices/"+self.name+"/"+name)
                        t[name].max = max
                        t[name].min=min
                        t[name].interval=interval
                        t[name].remote_writable = bool(flags&1)
                        #We have a tag, so we now know time sync is important
                        self.pclient.enableTimeSync()

                        #On first connect, we just use the val from the server
                        #to make this easier
                        if not name in self.tagClaims:
                            self.tagClaims[name]= t[name].claim(value,"shared",51,ts,"DoNotSend")
                            t[name].lastRemoteTs = raw_timestamp
                            if t[name].remote_writable:
                                def tagHandler(value,timestamp,annotation):
                                    """When a tag's value chages, inform the server.
                                    """
                                    ##No doing loops
                                    if annotation=="DoNotSend":
                                        return

                                    #Convert the time to the client
                                    try:
                                        ##Note the problem here. It only works if there's only a single server.
                                        #That's just how the protocol is though.
                                        t = int(self.pclient.getServer().toRemoteMonotonic(timestamp)*10**6)
                                    except:
                                        #Awful hack just in case our time is not synced.
                                        t=t[name].lastRemoteTs+1
                                        t[name].lastRemoteTs+=1
                                    self.pclient.sendMessage("core.tagv", name,struct.pack("<fq",value,int(t)))
                                t[name].setHandler(tagHandler)
                                t[name]._refToStashHandler = tagHandler

                    

                        #Name is already in the list. We try to use available info to guess
                        #At who has newer data, even though bidirectional tags aren't exact.
                        else:
                            print("tag", value, source,name)
                            server=self.pclient.getServer(source)
                            self.handleIncomingTagValue(value,good_ts,ts,name,t[name], raw_timestamp,server)
                           
                     

                        self.tagPoints = t


                elif target=="core.alert":
                    #This lets us dynamically add them at runtime
                    if not name in self.alerts:
                        if len(self.alerts)>512:
                            raise RuntimeError("Too many alerts on one device")
                        with self.lock:
                            x = self.alerts.copy()
                            x[name] = alerts.Alert("/devices/"+self.name+"/"+name)
                            self.alerts=x
                        self.setAlertPriorities()

                    #Trip the alarm if the remote device says it's tripped
                    if data[0]>0:
                        self.alerts[name].trip()
                    else:
                        self.alerts[name].clear()
            except:
                #Log to the "system" logger for the first error we have in a while
                if self.lastError <(time.time()- 10*60):
                    syslogger.exception("Error handling message from client(Log ratelimit: 10min)")
                else:
                    logging.exception("Error handling message from client")
                self.lastError = time.time()

        self._handlemsg = genericMessage
        self.t3 = self.pclient.messageTarget(None, genericMessage)

    def __getattr__(self,attr):
        "Transparently pass along things to the pavillion client"
        return getattr(self.pclient,attr)

    def __del__(self):
        try:
            self.pclient.close()
        except:
            pass



    
    def readFile(self,*a,**k):
        return self.pclient.readFile(*a,*k)

    def listDir(self, *a,**k):
        return self.pclient.listDir(*a,*k)

class K4DDevice(PavillionDevice):
    "Represents a device that supports the full K4D standard, allowing remote code execution"

    deviceTypeName = "k4d"
    def forceClose(self, name):
        c = self.pclient
        c.call(4105, name.encode("utf-8"))

    def isRunning(self, name,hash):
        c = self.pclient
        return c.call(4100, name.encode("utf-8")+b"\x00"+hash.encode("utf-8")+b"\x00")[0]>0


    
    def _loadAll(self):
        time.sleep(3)
        with self.lock:
            for i in self.loaded:
                self.loadProgram(i, self.loaded[i].code, self.loaded[i])
    onPavillionConnect = _loadAll
    def loadProgram(self, name, p, obj=None,errors=False):
        with self.lock:
            if obj:
                self.loaded[name]=obj
            try:
                if self.isRunning(name, p[:33]):
                    return

                c = self.pclient
                c.call(4097, name.encode("utf-8"))
                pos =0
                while p:
                    x = p[:1024].encode("utf8")
                    p=p[1024:]
                    c.call(4098, struct.pack("<L",pos) +name.encode("utf8")+b"\x00"+x)
                    pos+= len(x)
                c.call(4099, name.encode("utf-8"))

                syslogger.info("Loaded porgram:" +name+" to k4d device")
            except:
                print(traceback.format_exc())
                if errors:
                    raise


def updateProgram(module,resource, data, upload=True):
    with lock:
        data = data or modules_state.ActiveModules[module][resource]
        if (module, resource) in loadedSquirrelPrograms:
            loadedSquirrelPrograms[module,resource].unload()
        loadedSquirrelPrograms[module,resource] = RemoteSquirrelProgram(module,resource, data)
        if upload:
            #Networks aren't reliable, do everything in a background thread because it might take time 
            #And we'll just try again later if it fails
            def f():
                try:
                    loadedSquirrelPrograms[module,resource].upload()
                except:
                    try:
                        loadedSquirrelPrograms[module,resource].errors.append([time.time(),traceback.format_exc()])
                    except:
                        pass
                    syslogger.exception("Could not upload program: "+ module+"."+resource)
            workers.do(f)


builtinDeviceTypes.update({'pavillion':PavillionDevice,"k4d":K4DDevice})