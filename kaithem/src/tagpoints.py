from . import widgets
from .unitsofmeasure import convert, unitTypes
from . import scheduling, workers, virtualresource, messagebus, directories, persist, alerts, taghistorian
import time
import threading
import weakref
import logging
import types
import traceback
import math
import os
import gc
import functools
import re
import random
import json
import copy

import dateutil
import dateutil.parser


from typing import Callable, Union, Dict, List, Any
from typeguard import typechecked

logger = logging.getLogger("tagpoints")
syslogger = logging.getLogger("system")


exposedTags: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


# These are the atrtibutes of a tag that can be overridden by configuration.
# Setting tag.hi sets the runtime property, but we ignore it if the configuration takes precedence.
configAttrs = {
    'hi', 'lo', 'min', 'max', 'interval', 'displayUnits'
}
softConfigAttrs = {
    'overrideName', 'overrideValue', 'overridePriority', 'type', 'onChange', 'value','mqtt,server','mqtt.password','mqtt.port',"mqtt.messageBusName","mqtt.topic",'mqtt.incomingPriority','mqtt.incomingExpiration'
}

t = time.monotonic

# This is used for messing with the set of tags.
# We just accept that creating and deleting tags and claims is slow.
lock = threading.RLock()

allTags: Dict[str, weakref.ref] = {}
allTagsAtomic: Dict[str, weakref.ref] = {}

providers = {}

subscriberErrorHandlers: List[Callable] = []

hasUnsavedData = [0]

# Allows use to recalc entire lists of tags on the creation of another tag,
# For dependancy resolution
recalcOnCreate: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


defaultDisplayUnits = {
    "temperature": "degC|degF",
    "length": "m",
    "weight": "g",
    "pressure": "psi|Pa",
    "voltage": "V",
    "current": "A",
    "power": "W",
    "frequency": "Hz",
    "ratio": "%",
}


@functools.lru_cache(500, False)
def normalizeTagName(name: str, replacementChar=None):
    "Normalize hte name, and raise errors on anything just plain invalid, unless a replacement char is supplied"
    name = name.strip()
    if name == "":
        raise ValueError("Tag with empty name")

    if name[0] in '0123456789':
        raise ValueError("Begins with number")

    # Special case, these tags are expression tags.
    if not name.startswith("="):
        for i in illegalCharsInName:
            if i in name:
                if replacementChar:
                    name = name.replace(i, replacementChar)
                else:
                    raise ValueError(
                        "Illegal char in tag point name: " + i + " in " + name)
        if not name.startswith("/"):
            name = "/" + name
    else:
        if name.startswith("/="):
            name = name[1:]

    return name


class TagProvider():
    def mount(self, path):
        if not self.path.endswith("/"):
            self.path.append("/")
        self.path = path
        with lock:
            providers[path] = weakref.ref(self)

    def unmount(self):
        del providers[self.path]

    def __del__(self):
        with lock:
            del providers[self.path]

    def getTag(self, tagName):
        return _TagPoint(tagName)


configTags: Dict[str, object] = {}
configTagData = {}


def configTagFromData(name, data):
    name = normalizeTagName(name)

    t = data.get("type",'')

    # Get rid of any unused existing tag
    try:
        if name in configTags:
            del configTags[name]
            gc.collect()
            time.sleep(0.01)
            gc.collect()
            time.sleep(0.01)
            gc.collect()
    except Exception:
        logger.exception("Deleting tag config")

    tag=None
    # Create or get the tag
    if t == "number":
        tag = Tag(name)

    elif t == "string":
        tag = StringTag(name)
    elif name in allTags:
        tag = allTags[name]()
    else:
        # Config later when the tag is actually created
        configTagData[name] = data
        return

    if tag:
        configTags[name] = tag
    # Now set it's config.
    tag.setConfigData(data)


def getFilenameForTagConfig(i):
    if i.startswith("/"):
        n = i[1:]
    else:
        n = i
    return os.path.join(directories.vardir, "tags", n + ".yaml")


def gcEmptyConfigTags():
    torm = []
    # Empty dicts can be deleted from disk, letting us just revert to defaultsP
    for i in configTagData:
        if not configTagData[i].getAllData():
            # Can't delete the actual data till the file on disk is gone,
            # Which is handled by the persist libs
            if not os.path.exists(configTagData[i].filename):
                torm.append(i)

    # Note that this is pretty much the only way something can ever be deleted,
    # When it is empty we garbarge collect it.
    # This means we never need to worry about what to keep config data for.
    for i in torm:
        configTagData.pop(i, 0)


def loadAllConfiguredTags(f=os.path.join(directories.vardir, "tags")):
    with lock:
        global configTagData

        configTagData = persist.loadAllStateFiles(f)

        gcEmptyConfigTags()

        for i in list(configTagData.keys()):
            try:
                configTagFromData(i, configTagData[i].getAllData())
            except Exception:
                logging.exception("Failure with configured tag: " + i)
                messagebus.postMessage(
                    "/system/notifications/errors", "Failed to preconfigure tag " + i + "\n" + traceback.format_exc())


# _ and . allowed
illegalCharsInName = "{}|\\<>,?-=+)(*&^%$#@!~`\n\r\t\0"


class _TagPoint(virtualresource.VirtualResource):
    """
        A Tag Point is a named object that can be chooses from a set of data sources based on priority,
        filters that data, and returns it on a push or a pull basis.

        A data source here is called a "Claim", and can either be a number or a function. The highest
        priority claim is called the active claim.

        If the claim is a function, it will be called at most once per interval, which is set by tag.interval=N
        in seconds. However the filter function is called every time the data is requested.

        If there are any subscribed functions to the tag, they will automatically be called at the tag's interval,
        with the one parameter being the tag's value. Any getter functions will be called to get the value.


        It is also a VirtualResource, and as such if you enter it into a module, then replace it,
        all claims and subscriptions carry over.

        One generally does not instantiate a tag this way, instead they use the Tag function
        which can get existing tags. This allows use of tags for cross=

    """

    #Random opaque indicator
    DEFAULT_ANNOTATION='1d289116-b250-482e-a3d3-ffd9e8ac2b57'

    defaultData: Any = None
    type = 'object'
    mqttEncoding = 'json'


    @typechecked
    def __init__(self, name: str):
        global allTagsAtomic
        name = normalizeTagName(name)
        if name in allTags:
            raise RuntimeError(
                "Tag with this name already exists, use the getter function to get it instead")
        virtualresource.VirtualResource.__init__(self)

        # Dependancu tracking, if a tag depends on other tags, such as =expression based ones
        self.sourceTags: Dict[str, _TagPoint] = {}

        self.dataSourceWidget = None

        self.description = ''
        # True if there is already a copy of the deadlock diagnostics running
        self.testingForDeadlock = False

        self.alreadyPostedDeadlock = False


        #The very first time we push the tag value, we push even if the new val and prev val are both 0.
        #This makes sure we don't miss anything.
        self.isNotFirstPush =False

        
        #How long until we expire any incoming MQTT data
        self.incomingMQTTExpiration=0


        #Start timestamp at 0 meaning never been set
        #Value, timestamp, annotation.  This is the raw value, and the value could actually be a callable returning a value
        self.vta = (copy.deepcopy(self.defaultData), 0, None)

        # Used to track things like min and max, what has been changed by manual setting.
        # And should not be overridden by code.

        # We use excel-style "if it looks loke a number, it is", to simplify web based input for this one.
        self.configOverrides: Dict[str, object] = {}

        self._dynConfigValues: Dict[str, object] = {}
        self.dynamicAlarmData: Dict[str, object] = {}
        self.configuredAlarmData: Dict[str, object] = {}
        # The merged combo of both of those
        self.effectiveAlarmData: Dict[str, object] = {}

        self.alarms: Dict[str, object] = {}

        self._configuredAlarms: Dict[str, object] = {}

        self.name: str = name
        # The cached actual value from the claims
        self.cachedRawClaimVal = copy.deepcopy(self.defaultData)
        # The cached output of processValue
        self.lastValue = self.cachedRawClaimVal
        # The real current in use val, after the config override logic
        self._interval: Union[float, int] = 0
        self.activeClaim: Union[None, Claim] = None
        self.claims: Dict[str, Claim] = {}
        self.lock = threading.RLock()
        self.subscribers: List[weakref.ref] = []
        self.poller: Union[None, Callable] = None

        #Do we have anything set via the config page that would override the code-set mqtt stuff?
        self.hasMQTTConfig=False
        self.mqttClaim = None
        self.mqttConnection=None

        #When was the last time we got *real* new data
        self.lastGotValue = 0

        
        #If set, it is the function used to revert to the MQTT settings sefibed in code, as opposed to the
        #configured ones.
        self.mqttDynamicConnect=None



        self.lastError: Union[float, int] = 0

        # String describing the "owner" of the tag point
        # This is not a precisely defined concept
        self.owner: str = ""


        self.handler = None

        from . import kaithemobj

        if hasattr(kaithemobj.kaithem.context,'event'):
            self.originEvent = kaithemobj.kaithem.context.event
        else:
            self.originEvent=None

        # Used for the expressions in alert conditions and such
        self.evalContext = {
            "math": math,
            "time": time,
            'tag': self,
            're': re,
            'kaithem': kaithemobj.kaithem,
            'random': random,
            'tv': self.contextGetNumericTagValue,
            'stv': self.contextGetStringTagValue,
            'dateutil': dateutil
        }
        try:
            import numpy as np
            self.evalContext['np'] = np
        except ImportError:
            pass

        self.lastPushedValue = None
        self.onSourceChanged = None

        with lock:
            allTags[name] = weakref.ref(self)
            allTagsAtomic = allTags.copy()

        self.defaultClaim = self.claim(
            copy.deepcopy(self.defaultData), 'default',timestamp=0,annotation=self.DEFAULT_ANNOTATION)

        # What permissions are needed to
        # read or override this tag, as a tuple of 2 permission strings and an int representing the priority
        # that api clients can use.
        # As always, configured takes priority
        self.permissions = ['', '', 50]
        self.configuredPermissions = ['', '', 50]

        self.apiClaim: Union[None, Claim] = None

        # This is where we can put a manual override
        # claim from the web UI.
        self.manualOverrideClaim: Union[None, Claim] = None

        self._alarms: Dict[str, object] = {}

        with lock:
            messagebus.postMessage(
                "/system/tags/created", self.name, synchronous=True)
            if self.name in recalcOnCreate:
                for i in recalcOnCreate[self.name]:
                    try:
                        i()
                    except Exception:
                        logging.exception("????")

        if self.name.startswith("="):
            self.exprClaim = createGetterFromExpression(self.name, self)
        with lock:
            self.setConfigData(configTagData.get(self.name, {}))



    #In reality value, timestamp, annotation are all stored together as a tuple
    @property
    def timestamp(self):
        return self.vta[1]

    @property
    def annotation(self):
        return self.vta[2]



    def isDynamic(self):
        return callable(self.vta[0])

    def expose(self, r='', w='__never__', p=50, configured=False):
        """If not r, disable web API.  Otherwise, set read and write permissions.
           If configured permissions are set, they totally override code permissions.
           Empty configured perms fallback tor runtime

        """

        # Handle different falsy things someone might use to try and disable this
        if not r:
            r = ''
        if not w:
            w = '__never__'

        if isinstance(r, list):
            r = ','.join(r)
        if isinstance(w, list):
            w = ','.join(w)

        # Just don't allow numberlike permissions so we can keep pretending any config item that looks like a number, is.
        # Also, why would anyone do that?
        for i in r.split(",") + w.split(","):
            try:
                float(i)
                raise RuntimeError("Permission: " + str(i) +
                                   " looks like a number")
            except ValueError:
                pass

        if not p:
            p = 50
        # Make set we don't somehow save bad data and break everything
        p = int(p)
        w = str(w)
        r = str(r)

        if not r or not w:
            d = ['', '', '']
            emptyPerms = True
        else:
            emptyPerms = False
            d = [r, w, p]

        with lock:
            with self.lock:
                if configured:
                    self.configuredPermissions = d

                    self._recordConfigAttr(
                        'permissions', d if not emptyPerms else None)
                    hasUnsavedData[0] = True
                else:
                    self.permissions = d

                # Merge config and direct
                d2 = self.getEffectivePermissions()

                # Be safe, only allow writes if user specifies a permission
                d2[1] = d2[1] or '__never__'

                if not d2[0]:
                    self.dataSourceWidget = None
                    self.dataSourceAutoControl = None
                    try:
                        del exposedTags[self.name]
                    except KeyError:
                        pass
                    if self.apiClaim:
                        self.apiClaim.release()
                else:
                    w = widgets.DataSource(id="tag:" + self.name)

                    #The tag.control version is exactly the same but output-only, so you can have a synced UI widget that
                    #can store the UI setpoint state even when the actual tag is overriden.
                    self.dataSourceAutoControl = widgets.DataSource(id="tag.control:" + self.name)
                    self.dataSourceAutoControl.write(None)
                    w.setPermissions([i.strip() for i in d2[0].split(",")], [
                                     i.strip() for i in d2[1].split(",")])

                    self.dataSourceAutoControl.setPermissions([i.strip() for i in d2[0].split(",")], [
                                     i.strip() for i in d2[1].split(",")])            
                    w.value = self.value

                    exposedTags[self.name] = self
                    if self.apiClaim:
                        self.apiClaim.setPriority(p)
                    self._apiPush()

                    w.attach(self.apiHandler)
                    self.dataSourceAutoControl.attach(self.apiHandler)

                    self.dataSourceWidget = w

    def mqttConnect(self, *,server=None, port=1883, password=None,messageBusName=None, mqttTopic=None, incomingPriority=None, incomingExpiration=0, configured=False):

        port=int(port)

        if incomingPriority==None:
            incomingPriority=50
        incomingPriority=int(incomingPriority)

        self.incomingMQTTExpiration=float(incomingExpiration)

        def doConnect():
            if server or messageBusName or password and (not server=='__disable__'):
                self.mqttDisconnect(False)
            else:
                self.mqttDisconnect(True)

            if self.mqttClaim:
                self.mqttClaim.setPriority(incomingPriority)
                self.mqttClaim.setExpiration(self.incomingMQTTExpiration)

            from scullery import mqtt
            n = self.name
            if n[0]=='/':
                n=n[1:]
            n="tagpoints/"+n

            self.mqttPriority = int(incomingPriority)
            self.mqttTopic = mqttTopic or n

            if server or messageBusName or password and (not server=='__disable__'):
                self.mqttConnection = mqtt.getConnection(server=server, port=port, password=password, messageBusName=messageBusName)
                self.mqttConnection.subscribe(self.mqttTopic, self._onIncomingMQTTMessage,encoding=self.mqttEncoding)
                self.subscribe(self._mqttHandler)
        
        if configured:
            #If the user deleted the configuration, go back to what was set in code
            if not(server or messageBusName or password):
                if  self.mqttDynamicConnect:
                    self.mqttDisconnect(False)
                    self.mqttDynamicConnect()
                else:
                    self.mqttDisconnect(True)
                self.hasMQTTConfig=False

            else:
                self.hasMQTTConfig=True
                doConnect()

            
        else:
            #If this is something set in code, connect if we don't have a configured connection setup already.
            
            if not self.hasMQTTConfig:
                doConnect()
            self.mqttDynamicConnect= doConnect

    def mqttDisconnect(self,unclaim=True):
        self.unsubscribe(self._mqttHandler)
        if self.mqttConnection:
            self.mqttConnection.unsubscribe(self.mqttTopic, self._onIncomingMQTTMessage)
            self.mqttConnection=None

        if unclaim:
            try:
                self.mqttClaim.release()
            except AttributeError:
                pass

    def _onIncomingMQTTMessage(self,topic,value):
        if not self.mqttClaim:
            self.mqttClaim = self.claim(value, name="MQTTSync", priority=self.mqttPriority,annotation="MQTTSyncIncoming")
            self.mqttClaim.setExpiration(self.incomingMQTTExpiration)
        else:
            self.mqttClaim.set(value,annotation="MQTTSyncIncoming")
        
    def _mqttHandler(self, value,t,a):
        #No endless l00ps.
        if a =='MQTTSyncIncoming':
            return
        #Publish local changes to the MQTT bus.
        self.mqttConnection.publish(self.mqttTopic, value,retain=True,encoding=self.mqttEncoding)





    def apiHandler(self, u, v):
        if v is None:
            if self.apiClaim:
                self.apiClaim.release()
        else:
            # No locking things up if the times are way mismatched and it sets a time way in the future
            self.apiClaim = self.claim(v, 'WebAPIClaim', priority=(
                self.getEffectivePermissions())[2], annotation=u)

            # They tried to set the value but could not, so inform them of such.
            if not self.currentSource == self.apiClaim.name:
                self._apiPush()

    def controlApiHandler(self, u, v):
        if v is None:
            if self.apiClaim:
                self.apiClaim.release()
        else:
            # No locking things up if the times are way mismatched and it sets a time way in the future
            self.apiClaim = self.claim(v, 'WebAPIClaim', priority=(
                self.getEffectivePermissions())[2], annotation=u)

            # They tried to set the value but could not, so inform them of such.
            if not self.currentSource == self.apiClaim.name:
                self._apiPush()

        self.dataSourceAutoControl.write(v)

    def getEffectivePermissions(self):
        d2 = [self.configuredPermissions[0] or self.permissions[0],
              self.configuredPermissions[1] or self.permissions[1],
              self.configuredPermissions[2] or self.permissions[2]]

        # Block exposure at all if the permission is never
        if '__never__' in d2[0]:
            d2[0] = ''
            d2[1] = ''

        return d2

    def _apiPush(self):
        "If the expose function was used, push this to the dataSourceWidget"
        if not self.dataSourceWidget:
            return

        # Immediate write, don't push yet, do that in a thread because TCP can block
        def pushFunction():
            # Set value immediately, for later page loads
            self.dataSourceWidget.value = self.value
            if self.guiLock.acquire(timeout=1):
                try:
                    # Use the new literal computed value, not what we were passed,
                    # Because it could have changed by the time we actually get to push
                    self.dataSourceWidget.send(self.value)
                finally:
                    self.guiLock.release()

        # Should there already be a function queued for this exact reason, we just let
        # That one do it's job
        if self.guiLock.acquire(timeout=0.001):
            try:
                workers.do(pushFunction)
            finally:
                self.guiLock.release()

    @staticmethod
    def toMonotonic(t):
        offset = time.time() - time.monotonic()
        return t - offset

    @staticmethod
    def toWallClock(t):
        offset = time.time() - time.monotonic()
        return t + offset

    def testForDeadlock(self):
        "Run a check in the background to make sure this lock isn't clogged up"
        def f():
            # Approx check, more than one isn't the worst thing
            if self.testingForDeadlock:
                return

            self.testingForDeadlock = True

            if self.lock.acquire(timeout=30):
                self.lock.release()
            else:
                if not self.alreadyPostedDeadlock:
                    messagebus.postMessage("/system/notifications/errors", "Tag point: " + self.name +
                                           " has been unavailable for 30s and may be involved in a deadlock. see threads view.")
                    self.alreadyPostedDeadlock = True

            self.testingForDeadlock = False
        workers.do(f)

    def _recordConfigAttr(self, k, v):
        "Make sure a config attr setting gets saved"

        # If it looks like a number, it is.  That makes the code simpler for dealing
        # With web inputs and assorted things like that in a uniform way without needing to
        # special case based on the attribute name
        try:
            v = float(v)
        except:
            pass

        # Reject various kinds of empty, like None, empty strings, all whitespace.
        # Treat them as meaning to get rid of the attr
        if v not in (None, '') and (v.strip() if isinstance(v, str) else True):
            self.configOverrides[k] = v
            if self.name not in configTagData:
                configTagData[self.name] = persist.getStateFile(
                    getFilenameForTagConfig(self.name))
                configTagData[self.name][k] = v
                configTagData[self.name].noFileForEmpty = True
            configTagData[self.name][k] = v
        else:
            # Setting at attr to none or an empty string
            # Deletes it.
            self.configOverrides.pop(k, 0)
            if self.name in configTagData:
                configTagData[self.name].pop(k, 0)

    def recalc(self, *a):
        "Just re-get the value as needed"
        # It's a getter, ignore the mypy unused thing.
        self.poll()

    def contextGetNumericTagValue(self, n):
        "Get the tag value, adding it to the list of source tags. Creates tag if it isn't there"
        try:
            return self.sourceTags[n].value
        except KeyError:
            self.sourceTags[n] = Tag(n)
            # When any source tag updates, we want to recalculate.
            self.sourceTags[n].subscribe(self.recalc)
            return self.sourceTags[n].value
        return 0

    def contextGetStringTagValue(self, n):
        "Get the tag value, adding it to the list of source tags. Creates tag if it isn't there"
        try:
            return self.sourceTags[n].value
        except KeyError:
            self.sourceTags[n] = StringTag(n)
            # When any source tag updates, we want to recalculate.
            self.sourceTags[n].subscribe(self.recalc)
            return self.sourceTags[n].value
        return 0

    def setConfigAttr(self, k: str, v):
        "Sets the configured attribute by name, and also sets the corresponding dynamic attribute."

        if k not in configAttrs:
            raise ValueError(
                k + " does not support overriding by configuration")

        with lock:
            self._recordConfigAttr(k, v)
            if isinstance(v, str):
                if v.strip() == '':
                    v = None
                else:
                    try:
                        v = float(v)
                    except Exception:
                        pass
            # Attempt to go back to the values set by code
            if v is None:
                v = self._dynConfigValues.get(k, v)

            # For all the config attrs, setting the property sets the dynamic attr.
            # But WE also want to invoke all the side effects of setting the prop when we reconfigure.
            # As a hack, we save and restore that value, so that we preserve the original un-configured val.

            x = self._dynConfigValues.get(k, None)

            setattr(self, k, v)

            # Restore TODO race condition here!!!!!!
            # We get the old dyn val if it is set by another thread in between
            self._dynConfigValues[k] = x

            hasUnsavedData[0] = True

    # Note the black default condition, that lets us override a normal alarm while using the default condition.
    def setAlarm(self, name, condition='', priority="info", releaseCondition='', autoAck='no', tripDelay='0', isConfigured=False, _refresh=True):
        with lock:
            if not name:
                raise RuntimeError("Empty string name")

            if autoAck is True:
                autoAck = 'yes'
            if autoAck is False:
                autoAck = 'no'

            tripDelay = str(tripDelay)

            d = {
                'condition': condition,
                'priority': priority,
                'autoAck': autoAck,
                'tripDelay': tripDelay,
                'releaseCondition': releaseCondition
            }

            # Remove empties to make way for defaults
            d = {i: d[i] for i in d if d[i]}

            if isConfigured:
                if not isinstance(condition, str) and condition is not None:
                    raise ValueError(
                        "Configurable alarms only allow str or none condition")
                hasUnsavedData[0] = True

                storage = self.configuredAlarmData
            else:
                storage = self.dynamicAlarmData
                # Dynamics are weak reffed
                if not _refresh:
                    # This is because we need somewhere to return the strong ref
                    raise RuntimeError(
                        "Cannot create dynamic alarm without the refresh option")

            if condition is None:
                try:
                    storage.pop(name, 0)
                except Exception:
                    logger.exception("I don't think this matters")
            else:
                storage[name] = d

            # If we have configured alarms, there should be a configTagData entry.
            # If not, delete, because when that is empty it's how we know
            # to delete the actual file
            if isConfigured:
                if self.configuredAlarmData:
                    if self.name not in configTagData:
                        configTagData[self.name] = persist.getStateFile(
                            getFilenameForTagConfig(self.name))
                        configTagData[self.name].noFileForEmpty = True

                configTagData[self.name]['alarms'] = self.configuredAlarmData

            if _refresh:
                x = self.createAlarms(name)
                if x and not isConfigured:
                    # Alarms have to have a reference to the config data
                    x._tag_config_ref = d
                    return x

    def clearDynamicAlarms(self):
        with lock:
            if self.dynamicAlarmData:
                self.dynamicAlarmData.clear()
                self.createAlarms()

    def createAlarms(self, limitTo=None):
        merged = {}
        with lock:
            # Combine the merged and configured alarms
            # at a granular per-attribute level

            for i in self.dynamicAlarmData:
                d = self.dynamicAlarmData[i]
                if d:
                    merged[i] = merged.get(i, {})
                    for j in d:
                        merged[i][j] = d[j]

            for i in self.configuredAlarmData:
                merged[i] = merged.get(i, {})
                for j in self.configuredAlarmData[i]:
                    merged[i][j] = self.configuredAlarmData[i][j]

            self.effectiveAlarmData = merged.copy()

            # Cancel all existing alarms
            for i in self.alarms:
                a = self.alarms[i]
                if a:
                    if not limitTo or i == limitTo:
                        try:
                            self.unsubscribe(a.tagSubscriber)
                        except Exception:
                            logger.exception("Maybe already unsubbed?")


                        #This is the poller for polling even when there is no change, at a very low rate,
                        #To catch any edge cases not caught by watching tag changes
                        try:
                            a.poller.unregister()
                        except:
                            logger.exception("Maybe already unsubbed?")


                        a.release()

            if not limitTo:
                self.alarms = {}
                self._configuredAlarms = {}
            else:
                self.alarms.pop(limitTo, 0)
                self._configuredAlarms.pop(limitTo, 0)

            for i in merged:
                if not limitTo or i == limitTo:
                    d = merged[i]
                    self._alarmFromData(i, d)

            if limitTo and limitTo in self.alarms:
                return self.alarms[limitTo]

    def _alarmFromData(self, name, d):
        if not d.get("condition", ''):
            return

        if d.get("condition", '').strip() in ("False", "None", "0"):
            return
        tripCondition = d['condition']

        releaseCondition = d.get('releaseCondition', None)

        priority = d.get("priority", "warning") or 'warning'
        autoAck = d.get("autoAck", '').lower() in ('yes', 'true', 'y', 'auto')
        tripDelay = float(d.get("tripDelay", 0) or 0)

        # Shallow copy, because we are going to override the tag getter
        context = copy.copy(self.evalContext)

        tripCondition = compile(
            tripCondition, self.name + ".alarms." + name + "_trip", "eval")
        if releaseCondition:
            releaseCondition = compile(
                releaseCondition, self.name + ".alarms." + name + "_release", "eval")

        n = self.name.replace("=", 'expr_')
        for i in illegalCharsInName:
            n = n.replace(i, "_")

        # This is technically unnecessary, the weakref/GC based cleanup could handle it eventually,
        # But we want a real complete guarantee that it happens *right now*
        oldAlert = self.alarms.get(name, None)
        try:
            if oldAlert:
                for i in oldAlert.sourceTags:
                    try:
                        oldAlert.sourceTags[i].unsubscribe(
                            oldAlert.recalcFunction)
                    except Exception:
                        logger.exception("cleanup err")
                self.unsubscribe(oldAlert.tagSubscriber)

        except Exception:
            logger.exception("cleanup err")

        obj = alerts.Alert(n + ".alarms." + name,
                           priority=priority,
                           autoAck=autoAck,
                           tripDelay=tripDelay,
                           )
        #For debugging reasons
        obj.tagEvalContext = context

        obj.sourceTags = {}

        def f():
            try:
                if hasattr(self, "meterWidget"):
                    return self.meterWidget.render()
                elif hasattr(self, "spanWidget"):
                    return self.spanWidget.render()
                else:
                    return "Binary Tagpoint"
            except Exception as e:
                return str(e)

        obj.notificationHTML = f


        def alarmRecalcFunction(*a):
            "Recalc with same val vor this tag, but perhaps a new value for other tags that may be fetched in the expression eval"
            try:
                if eval(tripCondition, context, context):
                    obj.trip("Tag value:" + str(context['value'])[:128])
                elif releaseCondition:
                    if eval(releaseCondition, context, context):
                        obj.release()
                else:
                    obj.release()
            except Exception as e:
                obj.error(str(e))
                raise

        def alarmPollFunction(value, timestamp,annotation):
            "Given a new tag value, recalc the alarm expression"
            context['value'] = value
            context['timestamp']=timestamp
            context['annotation']=annotation

            alarmRecalcFunction()

        obj.recalcFunction = alarmRecalcFunction

        obj.poller= scheduling.scheduler.scheduleRepeating(alarmRecalcFunction, 60, sync=False)

        # Functions used for getting other tag values

        def contextGetNumericTagValue(n):
            """Since an alarm can use values from other tags, we must track those values, and from there
                recalc the alarm whenever they should change.
            """
            if n not in obj.sourceTags:
                obj.sourceTags[n] = Tag(n)
                # When any source tag updates, we want to recalculate.
                obj.sourceTags[n].subscribe(obj.recalcFunction)
            return obj.sourceTags[n].value

        def contextGetStringTagValue(n):
            """Since an alarm can use values from other tags, we must track those values, and from there
                recalc the alarm whenever they should change.
            """
            if n not in obj.sourceTags:
                obj.sourceTags[n] = StringTag(n)
                # When any source tag updates, we want to recalculate.
                obj.sourceTags[n].subscribe(obj.recalcFunction)
            return obj.sourceTags[n].value

        context['tv'] = contextGetNumericTagValue
        context['stv'] = contextGetStringTagValue

        # Store our new modified context.
        obj.context = context

        obj.tagSubscriber = alarmPollFunction
        self.subscribe(alarmPollFunction)
        self.alarms[name] = obj

        try:
            alarmPollFunction(self.value,  self.timestamp,self.annotation)
        except Exception:
            logger.exception(
                "Error in test run of alarm function for :" + name)
            messagebus.postMessage("/system/notifications/errors",
                                   "Error with tag point alarm\n" + traceback.format_exc())

        return alarmPollFunction

    def setConfigData(self, data):
        with lock:
            hasUnsavedData[0] = True
            # New config, new chance to see if there's a problem.
            self.alreadyPostedDeadlock = False

            if data and self.name not in configTagData:
                configTagData[self.name] = persist.getStateFile(
                    getFilenameForTagConfig(self.name))
                configTagData[self.name].noFileForEmpty = True

            if 'type' in data:
                if data['type'] == 'number' and not isinstance(self, _NumericTagPoint):
                    raise RuntimeError(
                        "Tag already exists and is not a numeric tag")
                if data['type'] == 'string' and not isinstance(self, _StringTagPoint):
                    raise RuntimeError(
                        "Tag already exists and is not a string tag")
                if data['type'] == 'object' and not isinstance(self, _TagPoint):
                    raise RuntimeError(
                        "Tag already exists and is not an object tag")

            # Only modify tags if the current data matches the existing
            # Configured value and has not beed overwritten by code
            for i in configAttrs:
                if i in data:
                    self.setConfigAttr(i, data[i])
                else:
                    self.setConfigAttr(i, None)

            for i in softConfigAttrs:
                if i in data:
                    self._recordConfigAttr(i, data[i])
                else:
                    self._recordConfigAttr(i, None)

            # The type field is what determines a tag that can be
            # created purely through config
            if data.get("type", None):
                configTags[self.name] = self
            else:
                # Pop from that storage, this shouldn't exist if there is no
                # external reference
                configTags.pop(self.name, 0)

            if hasattr(self, 'configuredOnChangeAction'):
                self.unsubscribe(self.configuredOnChangeAction)
                del self.configuredOnChangeAction

            if data.get("onChange", None):
                # Configurable onChange handlers
                ocfc = compile(data['onChange'],
                               self.name + ".onChange", 'exec')

                def ocf(value, timestamp, annotation):
                    exec(ocfc, self.evalContext, self.evalContext)
                self.configuredOnChangeAction = ocf
                self.subscribe(ocf)

            loggers = data.get('loggers', [])

            if loggers:
                configTagData[self.name]['loggers'] = data['loggers']
            else:
                try:
                    del configTagData[self.name]['loggers']
                except KeyError:
                    pass
            self.configLoggers = []
            for i in loggers:
                interval = float(i.get("interval", 60) or 60)
                length = float(
                    i.get("historyLength", 3 * 30 * 24 * 3600) or 3 * 30 * 24 * 3600)

                accum = i['accumulate']
                try:
                    c = taghistorian.accumTypes[accum](self, interval, length)
                    self.configLoggers.append(c)
                except Exception:
                    messagebus.postMessage(
                        "/system/notifications/errors", "Error creating logger for: " + self.name + "\n" + traceback.format_exc())

            # this is apparently just for the configured part, the dynamic part happens behind the scenes in
            # setAlarm via createAlarma
            alarms = data.get('alarms', {})
            self.configuredAlarmData = {}
            for i in alarms:
                if alarms[i]:
                    # Avoid duplicate param
                    alarms[i].pop('name', '')
                    self.setAlarm(
                        i, **alarms[i], isConfigured=True, _refresh=False)
                else:
                    self.setAlarm(i, None, isConfigured=True, _refresh=False)

            # This one is a little different. If the timestamp is 0,
            # We know it has never been set.
            if 'value' in data and not data['value'].strip() == '':
                configTagData[self.name]['value'] = data['value']

                if self.timestamp == 0:
                    # Set timestamp to 0, this marks the tag as still using a default
                    # Which can be further changed
                    self.setClaimVal("default", float(
                        data['value']), 0, "Configured default")
            else:
                if self.name in configTagData:
                    configTagData[self.name].pop("value", 0)

            # Todo there's a duplication here, we refresh allthe alarms, not sure we need to
            self.createAlarms()

            # Delete any existing configured value override claim
            if hasattr(self, 'kweb_manualOverrideClaim'):
                self.kweb_manualOverrideClaim.release()
                del self.kweb_manualOverrideClaim

            # Val override last, in case it triggers an alarm
            # Convert to string for consistent handling, the config engine things anything that looks like a number, is.
            overrideValue = str(data.get('overrideValue', '')).strip()


            if self.type == "binary":
                try:
                    overrideValue = bytes.fromhex(overrideValue)
                except:
                    logging.exception("Bad hex in tag override")
                    overrideValue = b''

            if overrideValue:
                if overrideValue.startswith("="):
                    self.kweb_manualOverrideClaim = createGetterFromExpression(
                        overrideValue, self, int(data.get('overridePriority', '') or 90))
                else:
                    self.kweb_manualOverrideClaim = self.claim(overrideValue, data.get(
                        'overrideName', 'config'), int(data.get('overridePriority', '') or 90))

            p = data.get('permissions', ('', '', ''))
            # Set configured permissions, overriding runtime
            self.expose(*p, configured=True)

            try:
                self.mqttConnect(
                    server=data.get("mqtt.server",''),
                    password=data.get("mqtt.password",''),
                    port=int(data.get("mqtt.port",'1883')), 
                    messageBusName=data.get("mqtt.messageBusName",''),
                    mqttTopic=data.get("mqtt.topic",''),
                    incomingPriority=data.get("mqtt.incomingPriority",'50'),
                    incomingExpiration=data.get("mqtt.incomingExpiration",'0'),
                    configured=True
                )
            except:
                messagebus.postMessage(
                    "/system/notifications/errors", "Failed to setup MQTT tag connection in" + self.name + "\n" + traceback.format_exc())
    @property
    def interval(self):
        return self._interval

    @interval.setter
    def interval(self, val):
        self._dynConfigValues['interval'] = val
        if not val == self.configOverrides.get('interval', val):
            return
        if val is not None:
            self._interval = val
        else:
            self._interval = 0

        messagebus.postMessage(
                "/system/tags/interval"+self.name, self._interval, synchronous=True)
        with self.lock:
            self._managePolling()

    @classmethod
    def Tag(cls, name: str, defaults={}):
        name = normalizeTagName(name)
        rval = None
        with lock:
            if name in allTags:
                x = allTags[name]()
                if x:
                    if x.__class__ is not cls:
                        raise TypeError(
                            "A tag of that name exists, but it is the wrong type. Existing: " + str(x.__class__) + " New: " + str(cls))
                    rval = x

            else:
                for i in sorted(providers.keys(), key=lambda p: len(p.path), reverse=True):
                    if name.startswith(i):
                        rval = providers[i].getTag(i)

            if not rval:
                rval = cls(name)

            return rval

    @property
    def currentSource(self):

        #Avoid the lock by using retru in case claim disappears
        for i in range(0,1000):
            try:
                return self.activeClaim().name
            except:
                time.sleep(0.001)
        return self.activeClaim().name

    def filterValue(self, v):
        "Pure function that returns a cleaned up or normalized version of the value"
        return v

    def __del__(self):
        global allTagsAtomic
        with lock:
            try:
                del allTags[self.name]
                allTagsAtomic = allTags.copy()
            except Exception:
                logger.exception("Tag may have already been deleted")
            messagebus.postMessage(
                "/system/tags/deleted", self.name, synchronous=True)

    def __call__(self, *args, **kwargs):
        if not args:
            return self.value
        else:
            return self.setClaimVal(*args, **kwargs)

    def interface(self):
        "Override the VResource thing"
        # With no replacement or master objs, we just return self
        return self

    def handoff(self, other):
        # Tag points have no concept of a master object.
        # They have no parameters that can' be set from any ref to it
        if not other == self:
            raise RuntimeError(
                "Tag points can't be replaced except by the same obj")
        return

    def _managePolling(self):
        interval = self._interval or 0
        if (self.subscribers or self.handler) and interval > 0:
            if not self.poller or not (interval == self.poller.interval):
                if self.poller:
                    self.poller.unregister()
                    self.poller=None

                self.poller = scheduling.scheduler.scheduleRepeating(
                    self.poll, interval, sync=False)
        else:
            if self.poller:
                self.poller.unregister()
                self.poller = None

    @typechecked
    def subscribe(self, f: Callable):
        if self.lock.acquire(timeout=20):
            try:

                ref: Union[weakref.WeakMethod, weakref.ref, None] = None

                if isinstance(f, types.MethodType):
                    ref = weakref.WeakMethod(f)
                else:
                    ref = weakref.ref(f)

                for i in self.subscribers:
                    if f==i():
                        syslogger.warning("Double subscribe detected, same function subscribed to "+self.name+" more than once.  Only the first takes effect.")
                        self._managePolling()
                        return
                        


                self.subscribers.append(ref)

                torm = []
                for i in self.subscribers:
                    if not i():
                        torm.append(i)
                for i in torm:
                    self.subscribers.remove(i)
                messagebus.postMessage(
                "/system/tags/subscribers"+self.name, len(self.subscribers), synchronous=True)
                self._managePolling()
            finally:
                self.lock.release()
        else:
            self.testForDeadlock()
            raise RuntimeError(
                "Cannot get lock to subscribe to this tag. Is there a long running subscriber?")

    def unsubscribe(self, f):
        if self.lock.acquire(timeout=20):
            try:
                x = None
                for i in self.subscribers:
                    if i() == f:
                        x = i
                if x:
                    self.subscribers.remove(x)
                messagebus.postMessage(
                "/system/tags/subscribers"+self.name, len(self.subscribers), synchronous=True)
                self._managePolling()
            finally:
                self.lock.release()
        else:
            self.testForDeadlock()
            raise RuntimeError(
                "Cannot get lock to subscribe to this tag. Is there a long running subscriber?")

    @typechecked
    def setHandler(self, f: Callable):
        self.handler = weakref.ref(f)

    def _debugAdminPush(self, value, t, a):
        pass

    def poll(self):
        if self.lock.acquire(timeout=5):
            try:
                self._getValue()
                self._push()
            finally:
                self.lock.release()
        else:
            self.testForDeadlock()

    def _push(self):
        """Push to subscribers. Only call under the same lock you changed value
            under. Otherwise the push might happen in the opposite order as the set, and
            subscribers would see the old data as most recent.

            Also, keep setting the timestamp and annotation under that lock, to stay atomic
        """

        # This is not threadsafe, but I don't think it matters.
        # A few unnecessary updates shouldn't affect anything.
        if self.lastValue == self.lastPushedValue:
            if self.isNotFirstPush:
                return

        self.isNotFirstPush=True

        # Note the difference with the handler.
        # It is called synchronously, right then and there
        if self.handler:
            f = self.handler()
            if f:
                f(self.lastValue, self.timestamp, self.annotation)
            else:
                self.handler = None

        self._apiPush()

        self.lastPushedValue = self.lastValue

        for i in self.subscribers:
            f = i()
            if f:
                try:
                    f(self.lastValue, self.timestamp, self.annotation)
                except Exception:
                    try:
                        extraData = str((str(self.lastValue)[:48], self.timestamp, str(self.annotation)[:48]))
                    except Exception as e:
                        extraData= str(e)
                    logger.exception("Tag subscriber error, val,time,annotation was: "+extraData)
                    # Return the error from whence it came to display in the proper place
                    for i in subscriberErrorHandlers:
                        try:
                            i(self, f, self.lastValue)
                        except Exception:
                            print("Failed to handle error: " +
                                  traceback.format_exc(6)+"\nData: "+extraData)
            del f

    def processValue(self, value):
        """Represents the transform from the claim input to the output.
            Must be a pure-ish function
        """
        return value

    @property
    def age(self):
        return time.monotonic() - self.vta[1]

    @property
    def value(self):
        return self._getValue()

    def pull(self):
        if not self.lock.acquire(timeout=15):
            raise RuntimeError("Could not get lock")
        try:
            return self._getValue(True)
        finally:
            self.lock.release()


    def _getValue(self, force=False):
        "Get the processed value of the tag, and update lastValue, It is meant to be called under lock."


        #Overrides not guaranteed to be instant
        if (self.lastGotValue > time.time()-self.interval) and not force:
            return self.lastValue


        activeClaim= self.activeClaim()

        activeClaimValue = activeClaim.value

        if not callable(activeClaimValue):
            # We no longer are aiming to support using the processor for impure functions

            #Todo why is this time.time not monotonic?
            self.lastGotValue = time.time()
            self.lastValue = self.processValue(activeClaimValue)

        else:
            # Rate limited tag getter logic. We ignore the possibility for
            # Race conditions and assume that calling a little too often is fine, since
            # It shouldn't affect correctness

            #Note that this is on a per-claim basis.  Every claim has it's own cache.
            if (time.monotonic() - activeClaim.lastGotValue > self._interval) or force:
                # Set this flag immediately, or else a function with an error could defeat the cacheing
                # And just flood everything with errors
                activeClaim.lastGotValue = time.monotonic()

                try:
                    # However, the actual logic IS ratelimited
                    # Note the lock is IN the try block so we don' handle errors under it and
                    # Cause bugs that way

                    # Viewing the state is pretty critical, we don't want to block
                    # that too long or we might interfere with manual recovery
                    if not self.lock.acquire(timeout=10 if force else 1):

                        self.testForDeadlock()
                        if force:
                            raise RuntimeError("Error getting lock")
                        # We extend the idea that cache is allowed to also
                        # mean we can fall back to cache in case of a timeout.
                        else:
                            logging.error(
                                "tag point:" + self.name + " took too long getting lock to get value, falling back to cache")
                            return self.lastValue
                    try:
                        # None means no new data
                        x = activeClaimValue()
                        t = time.monotonic()

                        if x is not None:
                            # Race here. Data might not always match timestamp an annotation, if we weren't under lock
                            self.vta=(activeClaimValue,t,None)

                            #Set the timestamp on the claim, so that it will not become expired
                            self.activeClaim().vta=self.vta

                            activeClaim.cachedValue=(x,t)

                            #This is just used to calculate the overall age of the tags data
                            self.lastGotValue = time.time()
                            self.lastValue = self.processValue(x)
            
                    finally:
                        self.lock.release()

                except Exception:
                    # We treat errors as no new data.
                    logger.exception("Error getting tag value")

                    # The system logger is the one kaithem actually logs to file.
                    if self.lastError < (time.time() - (60 * 10)):
                        syslogger.exception(
                            "Error getting tag value. This message will only be logged every ten minutes.")
                    # If we can, try to send the exception back whence it came
                    try:
                        from src import newevt
                        newevt.eventByModuleName(
                            activeClaimValue.__module__)._handle_exception()
                    except Exception:
                        print(traceback.format_exc())

        return self.lastValue

    @value.setter
    def value(self, v):
        self.setClaimVal("default", v, time.monotonic(),
                         "Set via value property")

    @property
    def pushOnRepeats(self, v):
        return False

    @pushOnRepeats.setter
    def pushOnRepeats(self, v):
        raise AttributeError("Push on repeats was causing too much trouble and too many loops and too much confusion and has been removed")


    def handleSourceChanged(self, name):
        if self.onSourceChanged:
            try:
                self.onSourceChanged(name)
            except Exception:
                logging.exception("Error handling changed source")

    def claim(self, value, name=None, priority=None, timestamp=None, annotation=None):
        """Adds a 'claim', a request to set the tag's value either to a literal
            number or to a getter function.

            A tag's value is the highest priority claim that is currently
            active, or the value returned from the getter if the active claim is
            a function.
        """

        name = name or 'claim' + str(time.time())
        if timestamp is None:
            timestamp = time.monotonic()

        if priority and priority > 100:
            raise ValueError("Maximum priority is 100")

        if not callable(value):
            value = self.filterValue(value)

        if not self.lock.acquire(timeout=15):
            raise RuntimeError("Could not get lock")
        try:

            # we're changing the value of an existing claim,
            # We need to get the claim object, which we stored by weakref
            claim = None
            # try:
            #     ##If there's an existing claim by that name we're just going to modify it
            if name in self.claims:
                claim = self.claims[name]()

             

            # If the weakref obj disappeared it will be None
            if claim is None:
                priority = priority or 50
                claim = self.claimFactory(
                    value, name, priority, timestamp, annotation)

            else:   
                #It could have been released previously.
                claim.released = False
                #Inherit priority from the old claim if nobody has changed it
                if priority is None:
                    priority = claim.priority
                if priority is None:
                    priority = 50


            claim.vta = value,timestamp,annotation

            claim.priority = priority

            # Note  that we use the time, so that the most recent claim is
            # Always the winner in case of conflictsclaim

        
            self.claims[name] =weakref.ref(claim)

            if self.activeClaim:
                ac=self.activeClaim()
            else:
                ac=None

            # If we have priortity on them, or if we have the same priority but are newer
            if (ac is None) or (priority > ac.priority) or ((priority == ac.priority) and(timestamp > ac.timestamp)):
                self.activeClaim = self.claims[name]
                self.handleSourceChanged(name)

                if callable(self.vta[0]) or callable(value):
                    self._managePolling()

                self.vta = (value, timestamp, annotation)

            # If priority has been changed on the existing active claim
            # We need to handle it
            elif name == ac.name:
                # Defensive programming against weakrefs dissapearing
                # in some kind of race condition that leaves them in the list.
                # Basically we find the highest priority valid claim

                #Deref all weak refs
                c =  [i() for i in self.claims.values()]
                #Eliminate dead references
                c = [i for i in c if i]
                #Get the top one
                c= sorted(c, reverse=True)

                for i in c:
                    x = i
                    if x:
                        self.vta = (x.value, x.timestamp, x.annotation)

                        if not i == self.activeClaim():
                            self.activeClaim = weakref.ref(i)
                            self.handleSourceChanged(i.name)
                        else:
                            self.activeClaim = weakref.ref(i)
                        break
            
            self._getValue(force=True)
            self._push()
            return claim
        finally:
            self.lock.release()

    def setClaimVal(self, claim, val, timestamp, annotation):
        "Set the value of an existing claim"

        if timestamp is None:
            timestamp = time.monotonic()

        valCallable=True
        if not callable(val):
            valCallable=False
            val = self.filterValue(val)

        if not self.lock.acquire(timeout=10):
            raise RuntimeError("Could not get lock!")

        try:
            c = self.claims[claim]

            # If we're setting the active claim
            if c == self.activeClaim:
                upd = True
            else:
                co=c()
                ac = self.activeClaim()

                upd = False
                # We can "steal" control if we have the same priority and are more recent, byt to do that we have to use the slower claim function that handles creating
                # and switching claims
                if (ac is None) or( co.priority >= ac.priority and timestamp >= ac.timestamp):
                    self.claim(val, claim, co.priority, timestamp, annotation)
                    return

            # Grab the claim obj and set it's val
            x = c()
            if self.poller or valCallable:
                self._managePolling()


            x.vta = val,timestamp,annotation

            if upd:
                self.vta = (val, timestamp, annotation)
                if valCallable:
                    #No need to call the function right away, that can happen when a getter calls it
                    pass#self._getValue()
                else:
                    self.lastGotValue = time.time()
                    self.lastValue=self.processValue(val)               
                # No need to push is listening
                if (self.subscribers or self.handler):
                    self._push()
        finally:
            self.lock.release()

    # Get the specific claim object for this class
    def claimFactory(self, value, name, priority, timestamp, annotation):
        return Claim(self, value, name, priority, timestamp, annotation)

    def getTopClaim(self):
        #Deref all weak refs
        x =  [i() for i in self.claims.values()]
        #Eliminate dead references
        x = [i for i in x if i and not i.released]
        if not x:
            return None
        #Get the top one
        x= sorted(x, reverse=True)[0]
        return x

    def release(self, name):
        if not self.lock.acquire(timeout=10):
            raise RuntimeError("Could not get lock!")

        try:
            # Ifid lets us filter by ID, so that a claim object that has
            # Long since been overriden can't delete one with the same name
            # When it gets GCed
            if name not in self.claims:
                return


            if name == "default":
                raise ValueError("Cannot delete the default claim")

            self.claims[name]().released = True
            o=self.getTopClaim()
            #All claims gone means this is probably in a __del__ function as it is disappearing
            if not o:
                return

            self.vta = (o.value, o.timestamp, o.annotation)
            self.activeClaim=weakref.ref(o)

            self._getValue()
            self._push()
            self._managePolling()
        finally:
            self.lock.release()


class _NumericTagPoint(_TagPoint):
    defaultData = 0
    type = 'number'
    @typechecked
    def __init__(self, name: str,
                 min: Union[float, int, None] = None,
                 max: Union[float, int, None] = None):

        # Real active compouted vals after the dynamic/configured override logic
        self._hi: Union[None, float, int] = None
        self._lo: Union[None, float, int] = None
        self._min: Union[None,float, int] = min
        self._max: Union[None,float, int] = max
        # Pipe separated list of how to display value
        self._displayUnits: Union[str, None] = None
        self._unit = ""
        self.guiLock = threading.Lock()
        self._meterWidget = None

        self.apiWidget = widgets.APIWidget()

        self._setupMeter()
        _TagPoint.__init__(self, name)

    def processValue(self, value):

        if self._min is not None:
            value = max(self._min, value)

        if self._max is not None:
            value = min(self._max, value)

        return float(value)

    @property
    def meterWidget(self):
        if not self.lock.acquire(timeout=5):
            raise RuntimeError("Error getting lock")
        try:
            if self._meterWidget:
                x = self._meterWidget
                if x:
                    self._debugAdminPush(self.value, None, None)
                    # Put if back if the function tried to GC it.
                    self._meterWidget = x
                    return self._meterWidget

            self._meterWidget = widgets.Meter()

            def f(v, t, a):
                self._debugAdminPush(v, t, a)
            self.subscribe(f)
            self._meterWidget.updateSubscriber = f

            self._meterWidget.defaultLabel = self.name.split(".")[-1][:24]

            self._meterWidget.setPermissions(
                ['/users/tagpoints.view'], ['/users/tagpoints.edit'])
            self._setupMeter()
            # Try to immediately put the correct data in the gui
            if self.guiLock.acquire():
                try:
                    # Note: this in-thread write could be slow
                    self._meterWidget.write(self.lastValue)
                finally:
                    self.guiLock.release()
            return self._meterWidget
        finally:
            self.lock.release()

    def _debugAdminPush(self, value, t, a):

        if not self._meterWidget:
            return

        if not self._meterWidget.stillActive():
            if not self.lock.acquire(timeout=5):
                raise RuntimeError("Error getting lock")
            self._meterWidget = None
            self.lock.release()
            return

        # Immediate write, don't push yet, do that in a thread because TCP can block

        def pushFunction():
            self._meterWidget.write(value, push=False)
            if self.guiLock.acquire(timeout=1):
                try:
                    # Use the cached literal computed value, not what we were passed,
                    # Because it could have changed by the time we actually get to push
                    self._meterWidget.write(self.lastValue)
                finally:
                    self.guiLock.release()

        # Should there already be a function queued for this exact reason, we just let
        # That one do it's job
        if self.guiLock.acquire(timeout=0.001):
            try:
                workers.do(pushFunction)
            finally:
                self.guiLock.release()

    def filterValue(self, v):
        return float(v)

    def claimFactory(self, value, name, priority, timestamp, annotation):
        return NumericClaim(self, value, name, priority, timestamp, annotation)

    @property
    def min(self):
        return self._min

    @min.setter
    def min(self, v: Union[None, float, int]):
        self._dynConfigValues['min'] = v

        if not v == self.configOverrides.get('min', v):
            return
        self._min = v
        self.pull()
        self._setupMeter()

    @property
    def max(self):
        return self._max

    @max.setter
    def max(self, v: Union[None, float, int]):
        self._dynConfigValues['max'] = v
        if not v == self.configOverrides.get('max', v):
            return
        self._max = v
        self.pull()
        self._setupMeter()

    @property
    def hi(self):
        x = self._hi
        if self._hi is None:
            return 10**18
        return x

    @hi.setter
    def hi(self, v: Union[None, float, int]):
        self._dynConfigValues['hi'] = v
        if not v == self.configOverrides.get('hi', v):
            return
        if v is None:
            v = 10**16
        self._hi = v
        self._setupMeter()

    @property
    def lo(self):
        if self._lo is None:
            return 10**18
        return self._lo

    @lo.setter
    def lo(self, v: Union[None, float, int]):
        self._dynConfigValues['lo'] = v
        if not v == self.configOverrides.get('lo', v):
            return
        if v is None:
            v = -(10**16)
        self._lo = v
        self._setupMeter()

    def _setupMeter(self):
        if not self._meterWidget:
            return
        self._meterWidget.setup(self._min if (not (self._min is None)) else -100,
                                self._max if (
                                    not (self._max is None)) else 100,
                                self._hi if not (self._hi is None) else 10**16,
                                self._lo if not (
                                    self._lo is None) else -(10**16),
                                unit=self.unit,
                                displayUnits=self.displayUnits
                                )

    def convertTo(self, unit):
        "Return the tag's current vakue converted to the given unit"
        return convert(self.value, self.unit, unit)

    def convertValue(self, value, unit):
        "Convert a value in the tag's native unit to the given unit"
        return convert(value, self.unit, unit)

    @property
    def unit(self):
        return self._unit

    @unit.setter
    @typechecked
    def unit(self, value: str):
        if self._unit:
            if not self._unit == value:
                if value:
                    raise ValueError(
                        "Cannot change unit of tagpoint. To override this, set to None or '' first")
        # TODO race condition in between check, but nobody will be setting this from different threads
        # I don't think
        if not self._displayUnits:
            # Rarely does anyone want alternate views of dB values
            if "dB" not in value:
                try:
                    self._displayUnits = defaultDisplayUnits[unitTypes[value]]
                except Exception:
                    self._displayUnits = value
            else:
                self._displayUnits = value

        self._unit = value
        self._setupMeter()
        if self._meterWidget:
            self._meterWidget.write(self.value)

    @property
    def displayUnits(self):
        return self._displayUnits

    @displayUnits.setter
    def displayUnits(self, value):
        if value and not isinstance(value, str):
            raise RuntimeError("units must be str")
        self._dynConfigValues['displayUnits'] = value
        if not value == self.configOverrides.get('displayUnits', value):
            return

        self._displayUnits = value
        self._setupMeter()
        if self._meterWidget:
            self._meterWidget.write(self.value)


class _StringTagPoint(_TagPoint):
    defaultData = ''
    unit = "string"
    type = 'string'
    mqttEncoding = 'utf8'
    @typechecked
    def __init__(self, name: str):
        self.guiLock = threading.Lock()
        self._spanWidget = None

        _TagPoint.__init__(self, name)

    def processValue(self, value):

        return str(value)

    def filterValue(self, v):
        return str(v)

        
    def _mqttHandler(self, value,t,a):
        #No endless l00ps.
        if a =='MQTTSyncIncoming':
            return
        #Publish local changes to the MQTT bus.
        self.mqttConnection.publish(self.mqttTopic, value,retain=True,encoding='utf8')


    def _debugAdminPush(self, value, timestamp, annotation):
        # Immediate write, don't push yet, do that in a thread because TCP can block

        if not self._spanWidget:
            if not self.lock.acquire(timeout=5):
                raise RuntimeError("Error getting lock")
            self._spanWidget = None
            self.lock.release()
            return

        if not self._spanWidget.stillActive():
            if not self.lock.acquire(timeout=5):
                raise RuntimeError("Error getting lock")
            self._spanWidget = None
            self.lock.release()
            return

        # Limit the length
        value = value[:256]
        self._spanWidget.write(value, push=False)

        def pushFunction():
            self._spanWidget.value = value
            if self.guiLock.acquire(timeout=1):
                try:
                    # Use the cached literal computed value, not what we were passed,
                    # Because it could have changed by the time we actually get to push
                    self._spanWidget.write(self.lastValue)
                finally:
                    self.guiLock.release()
        # Should there already be a function queued for this exact reason, we just let
        # That one do it's job
        if self.guiLock.acquire(timeout=0.001):
            try:
                workers.do(pushFunction)
            finally:
                self.guiLock.release()

    @property
    def spanWidget(self):
        if not self.lock.acquire(timeout=5):
            raise RuntimeError("Error getting lock")
        try:
            if self._spanWidget:
                x = self._spanWidget

                def f(v, t, a):
                    self._debugAdminPush(v, t, a)
                self.subscribe(f)
                x.updateSubscriber = f

                if x:
                    self._debugAdminPush(self.value, None, None)
                    # Put if back if the function tried to GC it.
                    self._spanWidget = x
                    return self._spanWidget

            self._spanWidget = widgets.DynamicSpan()

            self._spanWidget.setPermissions(
                ['/users/tagpoints.view'], ['/users/tagpoints.edit'])
            # Try to immediately put the correct data in the gui
            if self.guiLock.acquire():
                try:
                    # Note: this in-thread write could be slow
                    self._spanWidget.write(self.lastValue)
                finally:
                    self.guiLock.release()
            return self._spanWidget
        finally:
            self.lock.release()


class _ObjectTagPoint(_TagPoint):
    defaultData: object = {}
    type = 'object'
    @typechecked
    def __init__(self, name: str):
        self.guiLock = threading.Lock()

        self.validate = None
        self._spanWidget = None
        _TagPoint.__init__(self, name)

    def processValue(self, value):

        if isinstance(value, str):
            value = json.loads(value)
        else:
            value = copy.deepcopy(value)

        if self.validate:
            value = self.validate(value)

        return value

    def filterValue(self, v):

        return v

    def _debugAdminPush(self, value, timestamp, annotation):
        # Immediate write, don't push yet, do that in a thread because TCP can block

        if not self._spanWidget:
            if not self.lock.acquire(timeout=5):
                raise RuntimeError("Error getting lock")
            self._spanWidget = None
            self.lock.release()
            return

        if not self._spanWidget.stillActive():
            if not self.lock.acquire(timeout=5):
                raise RuntimeError("Error getting lock")
            self._spanWidget = None
            self.lock.release()
            return

        value = json.dumps(value)
        # Limit the length
        value = value[:256]
        self._spanWidget.write(value, push=False)

        def pushFunction():
            self._spanWidget.value = value
            if self.guiLock.acquire(timeout=1):
                try:
                    # Use the cached literal computed value, not what we were passed,
                    # Because it could have changed by the time we actually get to push
                    self._spanWidget.write(json.dumps(self.lastValue))
                finally:
                    self.guiLock.release()
        # Should there already be a function queued for this exact reason, we just let
        # That one do it's job
        if self.guiLock.acquire(timeout=0.001):
            try:
                workers.do(pushFunction)
            finally:
                self.guiLock.release()

    @property
    def spanWidget(self):
        if not self.lock.acquire(timeout=5):
            raise RuntimeError("Error getting lock")
        try:
            if self._spanWidget:
                x = self._spanWidget

                def f(v, t, a):
                    self._debugAdminPush(v, t, a)
                self.subscribe(f)
                x.updateSubscriber = f
                if x:
                    self._debugAdminPush(self.value, None, None)
                    # Put if back if the function tried to GC it.
                    self._spanWidget = x
                    return self._spanWidget

            self._spanWidget = widgets.DynamicSpan()

            self._spanWidget.setPermissions(
                ['/users/tagpoints.view'], ['/users/tagpoints.edit'])
            # Try to immediately put the correct data in the gui
            if self.guiLock.acquire():
                try:
                    # Note: this in-thread write could be slow
                    self._spanWidget.write(self.lastValue)
                finally:
                    self.guiLock.release()
            return self._spanWidget
        finally:
            self.lock.release()


class _BinaryTagPoint(_TagPoint):
    defaultData: bytes = b''
    type = 'binary'

    @typechecked
    def __init__(self, name: str):
        self.guiLock = threading.Lock()

        self.validate = None
        _TagPoint.__init__(self, name)

    def processValue(self, value):
        if isinstance(value, bytes):
            value = value
        else:
            value=bytes(value)

        if self.validate:
            value = self.validate(value)

        return value

    def filterValue(self, v):
        return v





class Claim():
    "Represents a claim on a tag point's value"
    @typechecked
    def __init__(self, tag: _TagPoint, value,
                 name: str = 'default', priority: Union[int, float] = 50,
                 timestamp: Union[int, float, None] = None, annotation=None):

        self.name = name
        self.tag = tag
        self.vta = value,timestamp,annotation

        #If the value is a callable, this is the cached result plus the timestamp for the cache, separate
        #From the vta timestamp of when that callable actually got set.
        self.cachedValue = (None, timestamp)


        #Track the last *attempt* at reading the value if it is a callable, regardless of whether
        #it had new data or not.

        #It is in monotonic time.
        self.lastGotValue=0

        self.priority = priority

        #The priority set in code, regardless of whether we expired or not
        self.realPriority = priority
        self.expired = False

        #What priority should we take on in the expired state.
        self.expiredPriority=0

        self.expiration = 0
        
        self.poller = None

        self.released = False

    def __del__(self):
        if self.name != 'default':
            #Must be self.release not self.tag.release or old claims with the same name would
            #mess up new ones. The class method has a check for that.
            self.release()

    def __lt__(self, other):
        if self.released:
            if not other.released:
                return True
        if (self.priority, self.timestamp) < (other.priority, other.timestamp):
            return True
        return False

    def __le__(self, other):
        if self.released:
            if not other.released:
                return True
        if (self.priority, self.timestamp) <= (other.priority, other.timestamp):
            return True
        return False

    def __gt__(self, other):
        if other.released:
            if not self.released:
                return True        
        if (self.priority, self.timestamp) > (other.priority, other.timestamp):
            return True
        return False

    def __ge__(self, other):
        if other.released:
            if not self.released:
                return True   
        if (self.priority, self.timestamp) >= (other.priority, other.timestamp):
            return True
        return False

    def expirePoll(self,force=False):
        #Quick check and slower locked check.  If we are too old, set our effective
        #priority to the expired priority.


        #Expiry for callables is based on the actual function itself.
        #Expiry for  direct values is based on the timestamp of when external code set it.
        if callable(self.value):
            ts= self.cachedValue[1]
        else:
            ts = self.timestamp

        if not self.expired:

            if ts < (time.monotonic()- self.expiration):
                #First we must try to refresh the callable.
                self.refreshCallable()
                if self.tag.lock.acquire(timeout=90):
                    try:
                        if callable(self.value):
                            ts= self.cachedValue[1]
                        else:
                            ts = self.timestamp

                        if ts < (time.monotonic()- self.expiration):
                            self.setPriority(self.expiredPriority, False)
                            self.expired=True
                    finally:
                        self.tag.lock.release()
                else:
                    raise RuntimeError("Cannot get lock to set priority, waited 90s")
        else:
            #If we are already expired just refresh now.
            self.refreshCallable()

    
    def refreshCallable(self):
        #Only call the getter under lock in case it happens to not be threadsafe
        if callable(self.value):
            if self.tag.lock.acquire(timeout=90):
                self.lastGotValue=time.monotonic()
                try:
                    x = self.value()
                    if not x is None:
                        self.cachedValue = (x,time.monotonic())
                        self.unexpire()
                finally:
                    self.tag.lock.release()
                
            else:
                raise RuntimeError("Cannot get lock to set priority, waited 90s")

            


    def setExpiration(self,expiration, expiredPriority=1):
        """Set the time in seconds before this claim is regarded as stale, and what priority to revert to in the stale state.
            Note that that if you use a getter with this, it will constantly poll in the background
        """
        if self.tag.lock.acquire(timeout=90):
            try:
               self.expiration=expiration
               self.expiredPriority=expiredPriority
               self._managePolling()

            finally:
                self.tag.lock.release()
        else:
            raise RuntimeError("Cannot get lock, waited 90s")


    def _managePolling(self):
        interval = self.expiration
        if interval > 0:
            if not self.poller or not (interval == self.poller.interval):
                if self.poller:
                    self.poller.unregister()
                self.poller = scheduling.scheduler.scheduleRepeating(
                    self.expirePoll, interval, sync=False)
        else:
            if self.poller:
                self.poller.unregister()
                self.poller = None


    def unexpire(self):
        #If we are expired, un-expire ourselves.
        if self.expired:
            if self.tag.lock.acquire(timeout=90):
                try:
                    if self.expired:
                        self.expired=False
                        self.setPriority(self.realPriority,False)
                finally:
                    self.tag.lock.release()
            else:
                raise RuntimeError("Cannot get lock to set priority, waited 90s")

    @property
    def value(self):
        return self.vta[0]
    @property
    def timestamp(self):
        return self.vta[1]

    @property
    def annotation(self):
        return self.vta[2]


    def set(self, value, timestamp=None, annotation=None):

        #Not threadsafe here if multiple threads use the same claim, value, timestamp, and annotation can 
        self.vta =(value, self.timestamp, self.annotation)

        #If we are expired, un-expi
        if self.expired:
           self.unexpire()

        #In the released state we must do it all over again
        elif self.released:
            if self.tag.lock.acquire(timeout=60):
                try:
                    self.tag.claim(value=self.value, timestamp=self.timestamp, annotation=self.annotation,
                                priority=self.priority, name=self.name)
                finally:
                    self.tag.lock.release()

            else:
                raise RuntimeError("Cannot get lock to re-claim after release, waited 60s")
        else:
            self.tag.setClaimVal(self.name, value, timestamp, annotation)

    def release(self):
        try:
            #Stop any weirdness with an old claim double releasing and thus releasing a new claim
            if not self.tag.claims[self.name]() is self:

                #If the old replaced claim is somehow the active omne we acrtuallty should handle that
                if not self.tag.activeClaim() is self:
                    return
        except KeyError:
            return


        self.tag.release(self.name)

    def setPriority(self, priority,realPriority=True):
        if self.tag.lock.acquire(timeout=60):
            try:
                if realPriority:
                    self.realPriority = priority
                self.priority = priority
                self.tag.claim(value=self.value, timestamp=self.timestamp, annotation=self.annotation,
                               priority=self.priority, name=self.name)
            finally:
                self.tag.lock.release()

        else:
            raise RuntimeError("Cannot get lock to set priority, waited 60s")

    def __call__(self, *args, **kwargs):
        if not args:
            raise ValueError("No arguments")
        else:
            return self.set(*args, **kwargs)


class NumericClaim(Claim):
    "Represents a claim on a tag point's value"
    @typechecked
    def __init__(self, tag: _TagPoint, value,
                 name: str = 'default', priority: Union[int, float] = 50,
                 timestamp: Union[int, float, None] = None, annotation=None):

        Claim.__init__(self, tag, value, name, priority, timestamp, annotation)

    def setAs(self, value, unit, timestamp=None, annotation=None):
        "Convert a value in the given unit to the tag's native unit"
        self.set(convert(value, unit, self.tag.unit), timestamp, annotation)

# Math for the first order filter
# v is our state, k is a constant, and i is input.

# At each timestep of one, we do:
# v = v*(1-k) + i*k

# moving towards the input with sped determined by k.
# We can reformulate that as explicitly taking the difference, and moving along portion of it
# v = (v+((i-v)*k))

# We can show this reformulation is correct with XCas:
# solve((v*(1-k) + i*k) - (v+((i-v)*k)) =x,x)

# x is 0, because the two equations are always the same.


# Now we use 1-k instead, such that k now represents the amount of difference allowed to remain.
# Higher k is slower.
# (v+((i-v)*(1-k)))


# Twice the time means half the remaining difference, so we are going to raise k to the power of the number of timesteps
# at each round to account for the uneven timesteps we are using:
# v = (v+((i-v)*(1-(k**t))))

# Now we need k such that v= 1/e when starting at 1 going to 0, with whatever our value of t is.
# So we substitute 1 for v and 0 for i, and solve for k:
# solve(1/e = (1+((0-1)*(1-(k**t)))),k)

# Which gives us k=exp(-(1/t))


class Filter():
    pass


class LowpassFilter(Filter):
    def __init__(self, name, inputTag, timeConstant, priority=60, interval=-1):
        self.state = inputTag.value
        self.filtered = self.state
        self.lastRanFilter = time.monotonic()
        self.lastState = self.state

        # All math derived with XCas
        self.k = math.exp(-(1 / timeConstant))
        self.lock = threading.Lock()

        self.inputTag = inputTag
        inputTag.subscribe(self.doInput)

        self.tag = Tag(name)
        self.claim = self.tag.claim(
            self.getter, name=inputTag.name + ".lowpass", priority=priority)

        if interval is None:
            self.tag.interval = timeConstant / 2
        else:
            self.tag.interval = interval

    def doInput(self, val, ts, annotation):
        "On new data, we poll the output tag which also loads the input tag data."
        self.tag.poll()

    def getter(self):
        self.state = self.inputTag.value

        # Get the average state over the last period
        state = (self.state + self.lastState) / 2
        t = time.monotonic() - self.lastRanFilter
        self.filtered = (
            self.filtered + ((state - self.filtered) * (1 - (self.k**t))))
        self.lastRanFilter += t

        self.lastState = self.state

        # Suppress extremely small changes that lead to ugly decimals and network traffic
        if abs(self.filtered - self.state) < (self.filtered / 1000000.0):
            return self.state
        else:
            return self.filtered


class HighpassFilter(LowpassFilter):

    def getter(self):
        self.state = self.inputTag.value

        # Get the average state over the last period
        state = (self.state + self.lastState) / 2
        t = time.monotonic() - self.lastRanFilter
        self.filtered = (
            self.filtered + ((state - self.filtered) * (1 - (self.k**t))))
        self.lastRanFilter += t

        self.lastState = self.state

        s = self.state - self.filtered

        # Suppress extremely small changes that lead to ugly decimals and network traffic
        if abs(s) < (0.0000000000000001):
            return 0
        else:
            return s


class HysteresisFilter(Filter):
    def __init__(self, name, inputTag, hysteresis=0, priority=60):
        self.state = inputTag.value

        # Start at midpoint with the window centered
        self.hysteresisUpper = self.state + hysteresis / 2
        self.hysteresisLower = self.state + hysteresis / 2
        self.lock = threading.Lock()

        self.inputTag = inputTag
        inputTag.subscribe(self.doInput)

        self.tag = _NumericTagPoint(name)
        self.claim = self.tag.claim(
            self.getter, name=inputTag.name + ".hysteresis", priority=priority)

    def doInput(self, val, ts, annotation):
        "On new data, we poll the output tag which also loads the input tag data."
        self.tag.poll()

    def getter(self):
        with self.lock:
            self.lastState = self.state

            if val >= self.hysteresisUpper:
                self.state = val
                self.hysteresisUpper = val
                self.hysteresisLower = val - self.hysteresis
            elif val <= self.hysteresisLower:
                self.state = val
                self.hysteresisUpper = val + self.hysteresis
                self.hysteresisLower = val
            return self.state


def createGetterFromExpression(e, t, priority=98):

    try:
        for i in t.sourceTags:
            t.sourceTags[i].unsubscribe(t.recalc)
    except:
        logger.exception(
            "Unsubscribe fail to old tag.  A subscription mau be leaked, wasting CPU. This should not happen.")

    t.sourceTags = {}

    def recalc(*a):
        t()
    t.recalcHelper = recalc

    c = compile(e[1:], t.name + "_expr", "eval")

    def f():
        return(eval(c, t.evalContext, t.evalContext))

    # Overriding these tags would be extremely confusing because the
    # Expression is right in the name, so don't make it easy
    # with priority 98 by default
    c2 = t.claim(f, "ExpressionTag", priority)
    t.pull()
    return c2


Tag = _NumericTagPoint.Tag
ObjectTag = _ObjectTagPoint.Tag
StringTag = _StringTagPoint.Tag
BinaryTag = _BinaryTagPoint.Tag
