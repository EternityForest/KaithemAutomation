
import NetworkManager
import uuid,weakref, threading,logging

from .import registry, widgets, scheduling

by_uuid = weakref.WeakValueDictionary()

log = logging.getLogger("system.wifi")



def applyConnections():
    #Get all the interfaces that are not already connected
    freeDevices = []

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

        else:
            freeDevices.append(device)

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
                if dev.ActiveConnection.uuid in by_uuid:
                    if by_uuid[dev.ActiveConnection.uuid].priority >= self.priority:
                        continue
                    else:
                        if self.priority<51:
                            continue
            #If they selected an interface, only bind to that one.
            if con.interface and not dev.Udi==con.interface:
                continue
            for ap in dev.GetAccessPoints():
                if ap.Ssid == con.ssid:
                    if ap.Strength > selectedDeviceStrength:
                        selectedDevice = dev
                        selectedDeviceStrength = ap.Strength
        if selectedDevice:
           con.activate(interface=selectedDevice.Udi)
           freeDevices.remove(selectedDevice)
           


u =  'f598ca94-d461-11e9-ae8b-6368d32e2345'


class Connection():
    def __init__(self,ssid, psk,interface='',mode="sta", priority = 50,uuid=NetworkManager):
        self.ssid = ssid
        self.psk = psk
        self.mode = mode
        self.priority = priority
        self.uuid = uuid or str(uuid.uuid4())
        self.interface=interface
        by_uuid[self.uuid] = self
        try:
            NetworkManager.Settings.GetConnectionByUuid(self.uuid).Delete()
        except:
            pass


        if mode =='adhoc':
            keymgt = 'wpa-none'
        if mode == 'ap' or mode=='sta':
            keymgt='wpa-psk'


        connection = {
            '802-11-wireless': {'mode': 'infrastructure',
                                'ssid': ssid},
            '802-11-wireless-security': {'key-mgmt': keymgt, 'psk':psk, 'group': ['ccmp'] if psk else []},

            'connection': {'id': 'testconnect',
                            'type': '802-11-wireless',
                            'uuid':self.uuid,
                    },
            'ipv4': {'method': 'auto'},
            'ipv6': {'method': 'auto'},
        }

        NetworkManager.Settings.AddConnectionUnsaved(connection)



    def __del__(self):
        try:
            NetworkManager.Settings.GetConnectionByUuid(self.uuid).Delete()
        except:
            pass

    def activate(self, interface=None):
        devices = NetworkManager.NetworkManager.GetAllDevices()
        for dev in devices:
            if dev.DeviceType ==  NetworkManager.NM_DEVICE_TYPE_WIFI:
                if self.interface and not dev.Udi==self.interface:
                    continue
                if dev.ActiveConnection in by_uuid:
                    try:
                        if by_uuid[dev.ActiveConnection.Uuid].priority>= self.priority:
                            continue
                    except:
                        logging.exception("what?")
                
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

applyConnections()


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
                            if i['interface']==x['interface']:
                                if x.priority== i['priority']:
                                    continue
                registryConnections[i['uuid']] = Connection(ssid=i['ssid'], psk=i['psk'],interface=i['interface'],mode=i['mode'], priority=i['priority'])
        except:
            log.exception("Error setting up connection to "+str(i.get('ssid',"")))
    
    for i in registryConnections:
        if not i in uuids:
            del registryConnections[i]


def handleMessage(u,v):
    if v[0]=='refresh':
        api.send(['connections',registry.get('system.wifi/connections',[])])

    if v[0]=='setConnectionParam':
        x = registry.get('system.wifi/connections',[])
        for i in x:
            if i['uuid']==v[1]:
                i[v[2]]==v[3]
        x = reversed(sorted(x, key=lambda c: (c.priority, c.interface)))
        registry.set('system.wifi/connections',x)
        api.send(['connections',registry.get('system.wifi/connections',[])])

    if v[0]=='addConnection':
        c = {
            'ssid': '', 'mode':'sta', 'psk':'', 'interface':'', 'priority': 50,
            'uuid': str(uuid.uuid4())
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

@scheduling.scheduler.everyMinute
def worker():
    applyConnections()


api = widgets.APIWidget()
api.require("/admin/settings.edit")
api.attach(handleMessage)
