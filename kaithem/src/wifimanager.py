
import uuid,weakref, threading,logging

from .import registry, widgets, scheduling,messagebus

by_uuid = weakref.WeakValueDictionary()

log = logging.getLogger("system.wifi")



def applyConnections():


    #Skip the whole nonsense if there's no connections set up anyway
    if not by_uuid:
        return

    #This whole file is imported on-demand, because it has so many dependancies
    #And isn't available everywhere.
    import NetworkManager

    #SSID to (strength, device) of strongest connection to an AP
    connectionStrengths ={}
    for device in NetworkManager.NetworkManager.GetAllDevices():
        if not device.DeviceType ==  NetworkManager.NM_DEVICE_TYPE_WIFI:
            continue

        if device.ActiveAccessPoint:
            if device.ActiveAccessPoint.Ssid in connectionStrengths:
                if connectionStrengths[device.ActiveAccessPoint.Ssid][0]>device.ActiveAccessPoint.Strength:
                    connectionStrengths[device.ActiveAccessPoint.Ssid] =(device.ActiveAccessPoint.Strength,device)
            else:
                connectionStrengths[device.ActiveAccessPoint.Ssid] =(device.ActiveAccessPoint.Strength,device)


    #Clear weak connections when a strong connection exists to that same access point
    for device in NetworkManager.NetworkManager.GetAllDevices():
        if not device.DeviceType ==  NetworkManager.NM_DEVICE_TYPE_WIFI:
            continue
        if device.ActiveAccessPoint:
            if device.ActiveAccessPoint.Ssid in connectionStrengths:
                if not device.Udi == connectionStrengths[device.ActiveAccessPoint.Ssid][1].Udi:
                    if connectionStrengths[device.ActiveAccessPoint.Ssid][1].Strength < device.ActiveAccessPoint.Strength-3:
                        device.Disconnect()      

    connections = []
    try:
        for i in by_uuid:
            connections.append(by_uuid[i])
    except:
        return

    #Connections bound to a particular interfae get priority, as others can
    #Just find another adapter
    connections = reversed(sorted(connections, key=lambda x:(x.priority,x.interface)))

    #Connect everything that needs connection if the SSID is visible.
    for con in connections:
        selectedDevice = None
        selectedDeviceStrength = 0

        #If we already have a reasonable connection to an AP,
        #We don't need to make another.
        if con.ssid in connectionStrengths:
            #The rule about only one device per ssid is ignored if weself
            #Explicitly select access points
            if not con.interface:
                if connectionStrengths[con.ssid][0]>30:
                    continue

        for dev in NetworkManager.NetworkManager.GetAllDevices():
            if not dev.DeviceType ==  NetworkManager.NM_DEVICE_TYPE_WIFI:
                continue        

            #Don't allow connections to stomp on higher priority connections
            if dev.ActiveConnection:
                if dev.ActiveConnection.Uuid in by_uuid:
                    if by_uuid[dev.ActiveConnection.Uuid].priority >= con.priority:
                        continue
                else:
                    #Assume unknown is priority 50
                    if con.priority<51:
                        continue
            #If they selected an interface, only bind to that one.
            if con.interface and not dev.Udi==con.interface:
                continue

            #Make sure we don't select a device that can't even see the AP
            if con.mode == 'sta':
                for ap in dev.GetAccessPoints():
                    if ap.Ssid == con.ssid:
                        if ap.Strength > selectedDeviceStrength:
                            selectedDevice = dev
                            selectedDeviceStrength = ap.Strength
            else:
                #Just pick one
                selectedDevice = dev
                selectedDeviceStrength = 100
        if selectedDevice:
           if selectedDevice.ActiveAccessPoint:
                selectedDevice.Disconnect()
           con.activate(interface=selectedDevice.Udi)

modes={
    3:'AP',
    2:'STA'
}        


def matchIface(a, pattern):
    if pattern.endswith("*"):
        if a.startswith(pattern[:-1]):
            return True
    else:
        if a==pattern:
            return True
def getConnectionStatus():
    d = {}
    import NetworkManager
    try:
        devs = NetworkManager.NetworkManager.GetAllDevices()
        print("Err getting devices, using fallback")
    except:
        devs = NetworkManager.NetworkManager.GetDevices()

    for device in devs:
        if  device.DeviceType ==  NetworkManager.NM_DEVICE_TYPE_WIFI:
            ap = device.ActiveAccessPoint
            if ap:
                #2=WiFi STA 
                d[device.Udi] = (ap.Ssid, 100 if (not device.Mode==2) else ap.Strength, modes.get(device.Mode,"UNKNOWN") )
            else:
                d[device.Udi] = ("", 0, "DISCONNECTED")
        else:
            d[device.Udi] = ("NOT_WIFI",0, "UNKNOWN")

    return d

# def scanWeak():
#     d = {}
#     import NetworkManager
#     for device in NetworkManager.NetworkManager.GetAllDevices():
#         if  device.DeviceType ==  NetworkManager.NM_DEVICE_TYPE_WIFI:
#             ap = device.ActiveAccessPoint
#             if device.mode == 2:
#                 if ap.Strength< 30:
#                     pass
#     return d



class Connection():
    def __init__(self,ssid, psk,interface='',mode="sta", priority = 50,id=None,addrs=''):
        import NetworkManager

        self.ssid = ssid
        self.psk = psk
        self.mode = mode
        self.priority = priority
        self.uuid = id or str(uuid.uuid4())
        self.interface=interface
        self.addrs = addrs
        by_uuid[self.uuid] = self
        try:
            NetworkManager.Settings.GetConnectionByUuid(self.uuid).Delete()
        except:
            pass

        if mode =='adhoc':
            keymgt = 'wpa-none'
        if mode == 'ap' or mode=='sta':
            keymgt='wpa-psk'

        authalg =''
        if not psk:
            keymgt='none'
            authalg="open"

        modes= {
            'ap': 'ap',
            'sta': 'infrastructure',
            'adhoc': 'adhoc'
        }

        def parseAddresses(a):
            v6=[]
            v4=[]
            
            for i in a.split(","):
                i =i.strip()
                if not i:
                    continue

                i = i.split("/")
                if len(i)>1:
                    snlen=int(i[1])
                    addr = i[0]
                else:
                    addr = i[0]
                    snlen=24
                if ":" in addr:
                    v6.append({"address":addr,"prefix":snlen})
                else:
                    v6.append({"address":addr,"prefix":snlen})
            return v4, v6

        v4,v6 = parseAddresses(addrs)

        #Give it a default address, so it actually works
        if mode=="ap" and not v4:
            v4=[{"address":"10.0.0.1","prefix":24}]
        
        connection = {
            '802-11-wireless': {'mode': modes[mode],
                                'ssid': ssid},
            '802-11-wireless-security': {'key-mgmt': keymgt,
             'psk':psk, 
             'group': ['ccmp'] if psk else [],             
             },

            'connection': {'id': "temp:"+ssid,
                            'type': '802-11-wireless',
                            'uuid':self.uuid,
                    },
            'ipv4': {'method': 'auto', "address-data":v4, 'dns':registry.get("system.wifi/v4_dns",[])},
            'ipv6': {'method': 'auto', 'address-data':v6, 'dns':registry.get("system.wifi/v6_dns",[])},
        }
        NetworkManager.Settings.AddConnectionUnsaved(connection)



    def __del__(self):

        #Detect if this has been replaced by another with the same UUID
        #And we should avoid deleting the new one.
        #May have a race condition, doesn't matter, leaving one or two
        #connections on rare occasions isn't a big deal, they don't persist anyway,
        #And they'll get cleaned up next time something with this uuid changes
        if self.uuid in by_uuid:
            if by_uuid[self.uuid] != self:
                return
        try:
            import NetworkManager
            NetworkManager.Settings.GetConnectionByUuid(self.uuid).Delete()
        except:
            pass

    def activate(self, interface=None):
        import NetworkManager

        devices = NetworkManager.NetworkManager.GetAllDevices()
        for dev in devices:
            if dev.DeviceType ==  NetworkManager.NM_DEVICE_TYPE_WIFI:
                if self.interface and matchIface(dev.Udi==self.interface):
                    continue
                if dev.ActiveConnection:
                    if dev.ActiveConnection.Uuid in by_uuid:
                        try:
                            if by_uuid[dev.ActiveConnection.Uuid].priority>= self.priority:
                                continue
                        except:
                            logging.exception("what?")
                    else:
                        if self.priority<51:
                            continue

                if self.mode =="sta":
                    visible = False
                    for i in dev.GetAccessPoints():
                        if i.Ssid==self.ssid:
                            visible=True
                    if visible==False:
                        return

                c = NetworkManager.Settings.GetConnectionByUuid(self.uuid)
                print(c,dev)
                NetworkManager.NetworkManager.ActivateConnection(c, dev,'/')
                return True


registryConnections = {}

def connectionsFromRegistry():
    d = registry.get('system.wifi/connections',[])
    uuids = {}
    for i in d:
        if not isinstance(i,dict):
            log.error("Non-dict found in wifi settings where dict expected")
            continue
        try:
            uuids[i['uuid']] = i
            if i['ssid'] and i['mode']:
                if i['uuid'] in registryConnections:
                    x = registryConnections[i['uuid']]
                    #Check if we really need to update or if we can
                    #Just update priority
                    if i['ssid']==x.ssid and i['psk']==x.psk:
                        if i['mode']==x.mode:
                            if i['interface']==x.interface:
                                if i.get('addrs','') == x.addrs:
                                    x.priority= i['priority']
                                continue
                registryConnections[i['uuid']] = Connection(id=i['uuid'], ssid=i['ssid'], psk=i['psk'],interface=i['interface'],mode=i['mode'], priority=i['priority'], addrs=i.get('addrs',''))
        except:
            log.exception("Error setting up connection to "+str(i.get('ssid',"")))
    
    for i in registryConnections:
        if not i in uuids:
            del registryConnections[i]


def handleMessage(u,v):
    if v[0]=='refresh':
        api.send(['connections',registry.get('system.wifi/connections',[])])
        api.send(['status', getConnectionStatus()])
        api.send(['global',{
        'v4dns': registry.get('system.wifi/v4_dns',[]),
        'v6dns': registry.get('system.wifi/v6_dns',[])
        }
        
        ])

    if v[0]=='setConnectionParam':
        x = registry.get('system.wifi/connections',[])
        for i in x:
            if i['uuid']==v[1]:
                i[v[2]]=v[3]
        x = list(reversed(sorted(x, key=lambda c: (c['priority'], c['interface'],c['uuid']))))
        registry.set('system.wifi/connections',x)
        api.send(['connections',registry.get('system.wifi/connections',[])])

    if v[0]=='addConnection':
        c = {
            'ssid': '', 'mode':'sta', 'psk':'', 'interface':'', 'priority': 50,
            'uuid': str(uuid.uuid4()), 'addrs':''
        }
        x = registry.get('system.wifi/connections',[])
        x.append(c)
        registry.set('system.wifi/connections',x)
        api.send(['connections', registry.get('system.wifi/connections',[])])

    if v[0]=='deleteConnection':
        x = registry.get('system.wifi/connections',[])
        x= [i for i in x if not i['uuid']==v[1]]
        registry.set('system.wifi/connections',x)
        api.send(['connections', registry.get('system.wifi/connections',[])])
    
    if v[0]=="setV6DNS":
        registry.set('system.wifi/v6_dns',[i.strip() for i in v[1].split(",") if i.strip()])

    if v[0]=="setV4DNS":
        registry.set('system.wifi/v4_dns',[i.strip() for i in v[1].split(",") if i.strip()])

    if v[0]=='apply':
        try:
            connectionsFromRegistry()
            applyConnections()
        except:
            log.exception("Error in WifiManager")
            messagebus.postMessage("/system/notifications/errrors","WiFi Manager is set up but not working")


@scheduling.scheduler.everyMinute
def worker():

    #Don't bother if not configured
    if not registry.get('system.wifi/connections',[]):
        return
    try:
        import NetworkManager
    except:
        log.exception("Could not import NetworkManager. Network management disabled.")
        return

    try:
        connectionsFromRegistry()
        applyConnections()
        api.send(['status', getConnectionStatus()])
    except:
        log.exception("Error in WifiManager")


try:
    connectionsFromRegistry()
    applyConnections()
except:
    log.exception("Error in WifiManager")
    messagebus.postMessage("/system/notifications/errrors","WiFi Manager is set up but not working")



api = widgets.APIWidget()
api.require("/admin/settings.edit")
api.attach(handleMessage)
