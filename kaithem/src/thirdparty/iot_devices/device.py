import collections
import traceback
from typing import Any, Callable, Dict, Optional, Union
import logging
import time
import json
import copy

# example device_manifest.json file that should be in any module declaring devices. keys are device type names.


# submodule values are the submodule you would have to import to get access to that device type. blank is the root.
# easy to read manually!
"""
"devices": {
  "Device":{
    "submodule": ""
    "description": "Device base clas
  }
}
"""

#Gonna overwrite these functions insude functions...
minimum = min
maximum = max

class Device():
    """represents exactly one "device".   should not be used to represent an interface to a large collection, use
    one instance per device.
    
    it is a future proposed kaithem_automation device spec meant to allow you to write integrations that are also general 
    purpose libraries.
    
    """


    # this name must be the same as the name of the device itself
    device_type: str="Device"
    default_config={}

    # Iterable of config keys that should be considered secret, and hidden behind asterisks and such.
    config_secrets={}

    def __init__(self, name: str, config: Dict[str, str],**kw):
        """ name must be a special char free string. config must be a dict of string keys and values.
        all options that are device-specific must begin with "device."
        
        all options must be strings, let's keep this extremely simple and easy and basic and not
        restrict what kind of file is needed to store them, and also be 1-1 compatible with html forms.
        
        data must contain a name field, and must contain a type field matching the device type name.
        
        all other fields must be optional, and a blank unconfigured device should be creatable.  the device should set
        it's own missing fields for use as a template.
        
        the intent here is that some kind of loader mechanism will create a device by dynamically looking up
        the class based on the type, then auto-creating a subclass that adds any program-specific features.
        
        the other intent is you just manually create the data and use the device library in your program.


        Options starting with temp. are reserved for device specific things that should not actually be saved.


        Options endning with __ are used to add additional fields with special meaning.
        """

        config=copy.deepcopy(config)

        if config.get("type",self.device_type) != self.device_type:
            raise ValueError("This config does not match this class type:"+str((config['type'], self,type)))
    

        # Raise error on bad data.
        json.dumps(config)

        self.config: Dict[str, str] = config
        self.__datapointhandlers: Dict[str, Callable] = {}
        self.datapoints = {}

        # Used to store properties about config keys
        self.config_properties: Dict[str, Dict[str:Any]]= {}

        #Functions that can be called to explicitly request a data point
        #That return the new value
        self.__datapoint_getters: Dict[str, Callable] = {}

        for i in self.default_config:
            if not i in self.config:
                self.set_config_option(i,self.default_config[i])

        self.name=name
        if 'name' in self.config:
            if not self.config['name']== name:
                raise ValueError("Nonmatching name")
            name=self.name = config['name']
        else:
            self.set_config_option('name', name)
        

    @staticmethod
    def discover_devices(config:Dict[str, str] = {}, current_device: Optional[object]=None, intent="", **kwargs) -> Dict[str, Dict]:
        """ gives a dict of device data dicts that could be used to create a new device, indexed by a descriptive name.
        not required and may just return None.

        You may pass a partial config that the device may ignore.  It is to let you pass connection details used to find other
        similar devices.

        Current device MAY be set to the current version of a device, if it is being used in a UI along the lines of
        suggesting how to further set up a partly configured device, or suggesting ways to add another similar device.

        Kwargs is reserved for further hints on what kinds of devices should be discovered.

        The device should reuse as much of the given config as possible, discarding anything that wouldn't 
        work with the selected device.

        Intent may be a hint as to what kind of config you are looking for.  If it is "new", that means the host wants to add another
        similar device.  If it is "replace", the host wants to keep the same config but point at a different physical device.  If it is
        "configure",  the host wants to look for alternate configurations available for the same exact device.

        Discovery could even be used to suggest configuratons once you already have a connection to a device.


        Security gotcha:

        Discovered suggestions MUST NOT have any passwords or secrets if the suggestion is for something other than what
        the user provided it for, unless the protocol does not reveal the secrets to the server.
        
        You do not want to autosuggest trying the same credentials at bad.com that the user gave for example.com.

    
        
        UI:

        The suggested UI semantics for discover commands is "Add a similar device" and "Reconfigure this device".
        
        Reconfiguration should always be available as the user might always want to take an existing device object and
        swap out the actual physical device it connects to.


        """

        return {}

    def set_config_option(self, key: str, value: str):
        """sets an option in self.config. used for subclassing as you may want to persist.
        __init__ will automatically set the state.  this is used by the device itself to set it's 
        own persistent values at runtime, perhaps in response to a websocket message.

        Will always set the key in self.config.
        
        
        the host is responsible for subclassing this and actually saving the data somehow, should that feature be needed.
        """

        # Auto strip the values to clean them up
        self.config[key] = value.strip()


    def set_config_default(self, key: str, value: str):
        """sets an option in self.config if it does not exist or is blank. used for subclassing as you may want to persist.
       
         Calls into set_config_option, you should not need to subclass this.
        """

        if not key in self.config or not self.config[key].strip():
            self.set_config_option(key,value.strip())


    def print(self, s: str, title: str = ""):
        """used by the device to print to the hosts live device message feed, if such a thing should happen to exist"""
        logging.info(title + ': ' + str(s))

    def handle_error(self, s: str, title: str = ""):
        """like print but specifically marked as error. may get special notification.  should not be used for brief network loss
        """
        logging.error(title + ': ' + str(s))

    def handle_exception(self):
        self.handle_error(traceback.format_exc())

    def numeric_data_point(self,
                           name: str,
                           min: Optional[float] = None,
                           max: Optional[float] = None,
                           hi: Optional[float] = None,
                           lo: Optional[float] = None,
                           description: str = "",
                           unit: str = '',
                           handler:  Optional[Callable[[str,float,Any], Any]] = None,
                           interval: float = 0,
                           writable=True,
                           **kwargs):
        """register a new numeric data point with the given properties. handler will be called when it changes.
        only meant to be called from within __init__.
        
        hi and lo just tell what is a value outside of normal ranges that a user may want to be aware of.
        they do not have any special alarm function by default.

        The intent is that you can subclass this and have your own implementation of data points,
        such as exposing an MQTT api or whatever else.

        Interval annotates the default data rate the point will produce, for use in setting default poll
        rates by the host, if the host wants to poll.

        It does not mean the host SHOULD poll this, it only suggest a rate to poll at if the host has a subscriber to this data.

        Writable is purely for a host that might subclass this, to determine if it should allow writing to the point.



        self.datapoints[name] will start out with tha value of None

        """

        if min is None:
            min = -10**24

        if max is None:
            max = 10**24

        self.datapoints[name] = None

        def onChangeAttempt(v: Optional[float], t, a):
            if v is None:
                return
            if callable(v):
                v = v()
            v = float(v)
            v = minimum(max, v)
            v = maximum(min, v)
            t = t or time.monotonic()

            if self.datapoints[name] == v:
                return

            self.datapoints[name] = v

            #Handler used by the device
            if handler:
                handler(v, t, a)

            self.on_data_change(name, v, t, a)

        self.__datapointhandlers[name] = onChangeAttempt


    def string_data_point(self,
                           name: str,
                           description: str = "",
                           unit: str = '',
                           handler: Optional[Callable[[str,float,Any], Any]] = None,
                           interval: float = 0,
                           writable=True,
                           **kwargs):
        """register a new string data point with the given properties. handler will be called when it changes.
        only meant to be called from within __init__.
        
        The intent is that you can subclass this and have your own implementation of data points,
        such as exposing an MQTT api or whatever else.

        Interval annotates the default data rate the point will produce, for use in setting default poll
        rates by the host, if the host wants to poll.

        It does not mean the host SHOULD poll this, it only suggest a rate to poll at if the host has a subscriber to this data.

        self.datapoints[name] will start out with tha value of None

        """

        self.datapoints[name] = None

        def onChangeAttempt(v: Optional[str], t, a):
            if v is None:
                return
            if callable(v):
                v = v()
            v = str(v)
            t = t or time.monotonic()

            if self.datapoints[name] == v:
                return

            self.datapoints[name] = v

            #Handler used by the device
            if handler:
                handler(v, t, a)

            self.on_data_change(name, v, t, a)

        self.__datapointhandlers[name] = onChangeAttempt


    def object_data_point(self,
                           name: str,
                           description: str = "",
                           unit: str = '',
                           handler: Optional[Callable[[Dict,float,Any], Any]] = None,
                           interval: float = 0,
                            writable=True,
                           **kwargs):
        """register a new string data point with the given properties. handler will be called when it changes.
        only meant to be called from within __init__.
        
        The intent is that you can subclass this and have your own implementation of data points,
        such as exposing an MQTT api or whatever else.

        Interval annotates the default data rate the point will produce, for use in setting default poll
        rates by the host, if the host wants to poll.

        It does not mean the host SHOULD poll this, it only suggest a rate to poll at if the host has a subscriber to this data.

        self.datapoints[name] will start out with tha value of None

        """

        self.datapoints[name] = None

        def onChangeAttempt(v: Optional[str], t, a):
            if v is None:
                return
            if callable(v):
                v = v()

            # Validate
            json.dumps(v)

            # Mutability trouble
            v = copy.deepcopy(v)

            t = t or time.monotonic()

            if self.datapoints[name] == v:
                return

            self.datapoints[name] = v

            #Handler used by the device
            if handler:
                handler(v, t, a)

            self.on_data_change(name, v, t, a)

        self.__datapointhandlers[name] = onChangeAttempt



    def bytestream_data_point(self,
                           name: str,
                           description: str = "",
                           unit: str = '',
                           handler: Optional[Callable[[Dict,float,Any], Any]] = None,
                            writable=True,
                           **kwargs):
        """register a new bytestream data point with the given properties. handler will be called when it changes.
        only meant to be called from within __init__.
        
        Bytestream data points do not store data, they only push it through.

        Despite the name, buffers of bytes may not be broken up or combined, this is buffer oriented,
        """

        self.datapoints[name] = None

        def onChangeAttempt(v: Optional[str], t, a):
            t = t or time.monotonic()
            self.datapoints[name] = v

            #Handler used by the device
            if handler:
                handler(v, t, a)

            self.on_data_change(name, v, t, a)

        self.__datapointhandlers[name] = onChangeAttempt


    def push_bytes(self,name:str,value:bytes):
        """Same as set_data_point but for bytestream data"""
        self.set_data_point(name, value)


    def set_data_point(self,
                       name: str,
                       value,
                       timestamp: Optional[float] = None,
                       annotation: Optional[float] = None):
        """
        set a data point of the device. may be called by the device itself or by user code. this is the primary api
        and we try to funnel as much as absolutely possible into it.
        
        things like button presses that are not actually "data points" can be represented as things like
        (button_event_name, timestamp) tuples in object_tags.
        
        things like autodiscovered ui can be done just by adding more descriptive metadata to a data point.
                
        timestamp if present is a time.monotonic() time.  annotation is an arbitrary object meant to be compared for identity,
        for various uses, such as loop prevention when dealting with network sync, when you need to know where a value came from.

        This must be thread safe, but the change detection could glitch out and discard if you go from A to B and back to A again.
        
        When there is multiple writers you will want to aither do your own lock or ensure that you use unique values, 
        like with an event counter.
        
        """


        self.__datapointhandlers[name](value, timestamp, annotation)

    
    def set_data_point_getter(self,name:str, getter: Callable):
        self.__datapoint_getters[name] = getter

    def on_data_change(self, name: str, value, timestamp: float, annotation):
        "used for subclassing, this is how you watch for data changes"
        pass

    def request_data_point(self, name: str):
        """Rather than just passively read, actively request a data point's new value.

        Meant to be called by external host code.
        
        """
        if name in self.__datapoint_getters:
            x = self.__datapoint_getters[name]()
            if not x is None:
                # there has been a change! Maybe!  call a handler
                self.__datapointhandlers[name](x, time.monotonic(), "From getter")
                self.datapoints[name] = x
                return x

        return self.datapoints[name]

    def set_alarm(self, name:str, datapoint:str, 
            expression:str, priority:str="info" ,
            trip_delay:float=0, auto_ack:bool=False,
             release_condition:Optional[str]=None, **kw):
        """ declare an alarm on a certain data point.   this means we should consider the data point to be in an
            alarm state whenever the expression is true.  
            
            used by the device itself to tell the host what it considers to be an alarm condition.
            
            the expression must look like "value > 90", where the operator can be any of the common comparision operators.
            
            you may set the trip delay to require it to stay tripped for a certain time,
            polling during that time and resettig if it is not tripped.
            
            the alarm remains in the alarm state till the release condition is met, by default it's just when the trip
            condition is inactive.  at which point it will need to be acknowledged by the user.
            
            
            these alarms should be considered "presets" that the user can override if possible.   
            by default this function could just be a no-op, it's here because of kaithem_automation's alarm support,
            but many applications may be better off with full manual alarming.  
            
            in kaithem the expression is arbitrary, but for this lowest common denominator definition it's likely best to
            limit it to easily semantically parsible strings.
        
        """
        pass


    def close(self):
        "relese all resources and clean up"

    def on_delete(self):
        """
        release all persistent resources, used by the host app to tell the user the device is being permanently deleted.
        may be used to delete any files automatically created.
        """


    # optional ui integration features
    # these are here so that device drivers can device fully custom u_is.


    def on_ui_message(self,msg:Union[float, int, str, bool, None, dict, list],**kw):
        """recieve a json message from the ui page.  the host is responsible for providing a send_ui_message(msg)
        function to the manage and create forms, and a set_ui_message_callback(f) function.
        
        these messages are not directed at anyone in particular, have no semantics, and will be recieved by all
        manage forms including yourself.  they are only meant for very tiny amounts of general interest data and fast commands.
        
        this lowest common denominator approach is to ensure that the ui can be fully served over mqtt if desired.
    
        """

    def send_ui_message(self, msg:Union[float, int, str, bool, None, dict, list]):
        """
        send a message to everyone including yourself.
        """

    def get_management_form(self,) -> Optional[str]:
        """must return a snippet of html suitable for insertion into a form tag, but not the form tag itself.
        the host application is responsible for implementing the post target, the authentication, etc.
        
        when the user posts the form, the config options will be used to first close the device, then build 
        a completely new device.
        
        the host is responsible for the name and type parts of config, and everything other than the device.* keys.
        """

    @classmethod
    def get_create_form(**kwargs) -> Optional[str]:
        """must return a snippet of html used the same way as get_management_form, but for creating brand new devices"""

    def handle_web_request(self,relpath,params,method,**kwargs):
        """To be called by the framework.  Security must be handled by the framework.
           Frameworks may implement separate read and write permissions that apply separately
           to GET and other requests.

           For this reason you should always check that the method is a POST before accepting a write operation.   
        """
        return "No web content here"

    def web_serve_file(self,path,filename=None,mime=None):
        """
        From within your web handler, you can return the result of this to serve that file
        """
        raise NotImplementedError("This host framework does not support this feature")