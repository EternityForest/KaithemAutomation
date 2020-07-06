#Copyright Daniel Dunn 2014-2015, 2018,2019
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
import weakref,time,json,base64,cherrypy,os, traceback,random,threading,logging,socket,copy,struct
import random
from . import auth,pages,unitsofmeasure,config,util,messagebus
from src.config import config

logger = logging.getLogger("system.widgets")

#Modify lock for any websocket's subscriptions
subscriptionLock = threading.Lock()
from ws4py.websocket import WebSocket
import ws4py
import ws4py.messaging
widgets = weakref.WeakValueDictionary()
n = 0

from .unitsofmeasure import convert, unitTypes


def eventErrorHandler(f):
    #If we can, try to send the exception back whence it came
    try:
        from . import newevt
        if f.__module__ in newevt.eventsByModuleName:
            newevt.eventsByModuleName[f.__module__]._handle_exception()
    except:
        print(traceback.format_exc())

defaultDisplayUnits={
    "temperature": "degC|degF",
    "length": "m",
    "weight":"g",
    "pressure": "psi|Pa",
    "voltage": "V",
    "current":"A",
    "power": "W",
    "frequency": "Hz"
}

server_session_ID= str(time.time())+str(os.urandom(8))
def mkid():
    global n
    n=(n+1)%10000
    return('id'+str(n))


class ClientInfo():
    def __init__(self,user,cookie=None):
        self.user = user
        self.cookie=cookie

class WebInterface():

    #This index is entirely for AJAX calls
    @cherrypy.expose
    def index(self,**k):
        j = json.loads(k['json'])
        resp = {}
        user = pages.getAcessingUser()
        req = j['req']
        upd = j['upd']

        for i in j['upd']:
            widgets[i]._onUpdate(user,upd[i],"HTMLTEMPORARY")

        for i in req:
            resp[i] = widgets[i]._onRequest(user,"HTMLTEMPORARY")

        return json.dumps(resp)

    @cherrypy.expose
    def ws(self):
        # you can access the class instance through
        if not config['enable-websockets']:
            raise RuntimeError("Websockets disabled in server config")
        handler = cherrypy.request.ws_handler
        if cherrypy.request.scheme == 'https':
            handler.user = pages.getAcessingUser()
            handler.cookie = cherrypy.request.cookie
        else:
            handler.cookie = None
            handler.user = "__guest__"
        handler.clientinfo = ClientInfo(handler.user, handler.cookie)
        clients_info[handler.uuid] =  handler.clientinfo


    @cherrypy.expose
    def ws_allowed(self):
        return str(config['enable-websockets'])

    @cherrypy.expose
    def session_id(self):
        return server_session_ID

def subsc_closure(self,i, widget):
    def f(msg):
        try:
            self.send(msg)
        except socket.error:
            #These happen sometimes when things are disconnecting it seems,
            #And there's no need to waste log space or send a notification.
            pass
        except:
            if not widget.errored_send:
                widget.errored_send = True
                messagebus.postMessage("/system/notifications/errors","Problem in widget "+repr(widget)+", see logs")
                logger.exception("Error sending data from widget "+repr(widget)+" via websocket")
            else:
                logging.exception("Error sending data from websocket")
    return f

clients_info = weakref.WeakValueDictionary()

ws_connections = weakref.WeakValueDictionary()

def getConnectionRefForID(id,deleteCallback=None):
    try:
        return weakref.ref(ws_connections[id],deleteCallback)
    except KeyError:
        return None

usingmp=False
try:
    import msgpack
    usingmp=True
except:
    pass

if config['enable-websockets']:
    class websocket(WebSocket):
        def __init__(self,*args,**kwargs):
            self.subscriptions = []
            self.lastPushedNewData = 0
            self.uuid = "id"+base64.b64encode(os.urandom(16)).decode().replace("/",'').replace("-",'').replace('+','')[:-2]
            self.widget_wslock = threading.Lock()
            ws_connections[self.uuid] = self
            WebSocket.__init__(self,*args,**kwargs)

        def send(self,*a,**k):
            with self.widget_wslock:
                WebSocket.send(self, *a,**k,binary=isinstance(a[0],bytes))

        def closed(self,code,reason):
            with subscriptionLock:
                for i in self.subscriptions:
                    try:
                        widgets[i].subscriptions.pop(self.uuid)
                        widgets[i].subscriptions_atomic = widgets[i].subscriptions.copy()

                        if not widgets[i].subscriptions:
                            widgets[i].lastSubscribedTo = time.monotonic()
                    except:
                        pass

        def received_message(self,message):
            try:
                if isinstance(message,ws4py.messaging.BinaryMessage):
                    o = msgpack.unpackb(message.data,raw=False)
                else:
                    o = json.loads(message.data.decode('utf8'))

                resp = []
                user = self.user
                req = o['req']
                upd = o['upd']

                for i in upd:
                    if i[0] in widgets:
                        widgets[i[0]]._onUpdate(user,i[1],self.uuid)

                for i in req:
                    if i in widget:
                        resp.append([i, widgets[i]._onRequest(user,self.uuid)])

                if 'subsc' in o:
                    for i in o['subsc']:
                        if i in self.subscriptions:
                            continue
                        if i == "__WIDGETERROR__":
                            continue

                        #TODO: DoS by filling memory with subscriptions??

                        with subscriptionLock:
                          if i in widgets:
                                for p in widgets[i]._read_perms:
                                    if not auth.canUserDoThis(user,p):
                                        raise RuntimeError(user +" missing permission: "+str(p) )

                                widgets[i].subscriptions[self.uuid] = subsc_closure(self,i,widgets[i])
                                widgets[i].subscriptions_atomic = widgets[i].subscriptions.copy()
                                #This comes after in case it  sends data
                                widgets[i].onNewSubscriber(user,{})
                                widgets[i].lastSubscribedTo = time.monotonic()

                                self.subscriptions.append(i)
                                resp.append([i, widgets[i]._onRequest(user,self.uuid)])


            except Exception as e:
                logging.exception('Error in widget, responding to '+str(message.data))
                messagebus.postMessage("system/errors/widgets/websocket", traceback.format_exc(6))
                self.send(json.dumps({'__WIDGETERROR__':repr(e)}))

def randID():
    "Generate a base64 id"
    return base64.b64encode(os.urandom(8))[:-1].decode()

idlock = threading.Lock()
class Widget():
    def __init__(self,*args,**kwargs):
        self.value = None
        self._read_perms = []
        self._write_perms=[]
        self.errored_function = None
        self.errored_getter = None
        self.errored_send = None
        self.subscriptions = {}
        self.subscriptions_atomic = {}
        self.echo = True

        #Used for GC, we have a fake subscriber right away so we can do a grace
        #Period before trashing it.
        #Also tracks unsubscribe, you need to combine this with if there are any subscribers
        self.lastSubscribedTo = time.monotonic()

        def f(u,v):
            pass

        def f2(u,v,id):
            pass

        self._callback = f
        self._callback2 = f2

        with idlock:
            #Give the widget an ID for the client to refer to it by
            #Note that it's no longer always a  uuid!!
            if not 'id' in kwargs:
                for i in range(0,250000):
                    self.uuid = randID()
                    if not self.uuid in widgets:
                        break
                    if range>240000:
                        raise RuntimeError("No more IDs?")
            else:
                self.uuid = kwargs['id']

            #Insert self into the widgets list
            widgets[self.uuid] = self

    def stillActive(self):
        if self.subscriptions or (self.lastSubscribedTo>(time.monotonic()-30)):
            return True
    def onNewSubscriber(self,user, cid, **kw):
        pass

    def forEach(self,callback):
        "For each client currently subscribed, call callback with a clientinfo object"
        for i in self.subscriptions:
            callback(clients_info[i])

    #This function is called by the web interface code
    def _onRequest(self,user,uuid):
        """Widgets on the client side send AJAX requests for the new value. This function must
        return the value for the widget. For example a slider might request the newest value.

        This function is also responsible for verifying that the user has the right permissions

        This function is generally only called by the library.

        This function returns if the user does not have permission

        Args:
            user(string):
                the username of the user who is tring to access things.
        """
        for i in self._read_perms:
            if not auth.canUserDoThis(user,i):
                return
        try:
            return self.onRequest(user,uuid)
        except Exception as e:
            logger.exception("Error in widget request to "+repr(self))
            if not (self.errored_getter == id(self._callback)):
                messagebus.postMessage("/system/notifications/errors", "Error in widget getter function %s defined in module %s, see logs for traceback.\nErrors only show the first time a function has an error until it is modified or you restart Kaithem."
                                        %(self._callback.__name__, self._callback.__module__))
                self.errored_getter = id(self._callback)

    #This function is meant to be overridden or used as is
    def onRequest(self,user,uuid):
        """This function is called after permissions have been verified when a client requests the current value. Usually just returns self.value

        Args:
            user(string):
                The username of the acessung client
        """
        return self.value

    #This function is called by the web interface whenever this widget is written to
    def _onUpdate(self,user,value,uuid):
        """Called internally to write a value to the widget. Responisble for verifying permissions. Returns if user does not have permission"""
        for i in self._read_perms:
            if not auth.canUserDoThis(user,i):
                return

        for i in self._write_perms:
            if not auth.canUserDoThis(user,i):
                return

        self.onUpdate(user,value,uuid)

    def doCallback(self,user,value,uuid):
        "Run the callback, and if said callback fails, post a message about it."
        try:
            self._callback(user,value)
        except Exception as e:
            eventErrorHandler(self._callback)
            logger.exception("Error in widget callback for "+repr(self))
            if not (self.errored_function == id(self._callback)):
                messagebus.postMessage("/system/notifications/errors", "Error in widget callback function %s defined in module %s, see logs for traceback.\nErrors only show the first time a function has an error until it is modified or you restart Kaithem."
                                    %(self._callback.__name__, self._callback.__module__))
                self.errored_function = id(self._callback)
            raise e



        try:
            self._callback2(user,value,uuid)
        except Exception as e:
            logger.exception("Error in widget callback for "+repr(self))
            eventErrorHandler(self._callback2)
            if not (self.errored_function == id(self._callback)):
                messagebus.postMessage("/system/notifications/errors", "Error in widget callback function %s defined in module %s, see logs for traceback.\nErrors only show the first time a function has an error until it is modified or you restart Kaithem."
                                    %(self._callback.__name__, self._callback.__module__))
                self.errored_function = id(self._callback)
            raise e

    #Return True if this user can write to it
    def isWritable(self):
        for i in self._write_perms:
            if not pages.canUserDoThis(i):
                return "disabled"
        return ""

    #Set a callback if it ever changes
    def attach(self,f):
        self._callback = f

    #Set a callback if it ever changes.
    #This version also gives you the connection ID
    def attach2(self,f):
        self._callback2 = f

    #meant to be overridden or used as is
    def onUpdate(self,user,value,uuid):
        self.value = value
        self.doCallback(user,value,uuid)
        if self.echo:
            self.send(value)

    #Read and write are called by code on the server
    def read(self):
        return self.value

    def write(self,value,push=True):
        self.value = value
        self.doCallback("__SERVER__",value,"__SERVER__")
        if push:
            self.send(value)
        

    def send(self,value):
        "Send a value to all subscribers without invoking the local callback"
        if usingmp:
            d=msgpack.packb([[self.uuid,value]])
        else:
            d = json.dumps([[self.uuid,value]])
        #Not sure what the actual cause of the ssl segfault is, but maybe it's this?
        if (len(d)>128*1024):
            raise ValueError("Data is too large, refusing to send")

        #Yes, I really had a KeyError here. Somehow the dict was replaced with the new version in the middle of iteration
        #So we use an intermediate value so we know it won't change
        x = self.subscriptions_atomic
        for i in x:
            x[i](d)

    def sendTo(self,value,target):
        "Send a value to one subscriber by the connection ID"
        if usingmp:
            d=msgpack.packb([[self.uuid,value]])
        else:
            d = json.dumps([[self.uuid,value]])
        #Not sure what the actual cause of the ssl segfault is, but maybe it's this?
        if (len(d)>128*1024):
            raise ValueError("Data is too large, refusing to send")
        self.subscriptions_atomic[target](d)

    #Lets you add permissions that are required to read or write the widget.
    def require(self,permission):
        self._read_perms.append(permission)

    def requireToWrite(self,permission):
        self._write_perms.append(permission)
    
    def setPermissions(self,read,write):
        self._read_perms= copy.copy(read)
        self._write_perms= copy.copy(write)

#This widget is just a time display, it doesn't really talk to the server, but it's useful to keep the same interface.
class TimeWidget(Widget):
    def onRequest(self,user,uuid):
        return str(unitsofmeasure.strftime())

    def render(self,type='widget'):
        """
        Args:
            type(string): if "widget",  returns it with normal widget styling. If "inline", it jsut looks like a span.
        Returns:
            string: An HTML and JS string that can be directly added as one would add any HTML inline block tag
        """
        if type=='widget':
            return("""<div id="%s" class="widgetcontainer">
            <script type="text/javascript" src="/static/js/strftime-min.js">
            </script>
            <script type="text/javascript">
            var f = function(val)
            {
               var d = new Date();

                document.getElementById("%s").innerHTML=d.strftime("%s");
            }
            setInterval(f,70);
            </script>
            </div>"""%(self.uuid,self.uuid,auth.getUserSetting(pages.getAcessingUser(),'strftime').replace('%l','%I')))

        elif type=='inline':
            return("""<span id="%s">
            <script type="text/javascript" src="/static/js/strftime-min.js">
            </script>
            <script type="text/javascript">
            var f = function(val)
            {
               var d = new Date();

                document.getElementById("%s").innerHTML=d.strftime("%s");
            }
            setInterval(f,70);
            </script>
            </span>"""%(self.uuid,self.uuid,auth.getUserSetting(pages.getAcessingUser(),'strftime').replace('%l','%I')))
        else:
            raise ValueError("Invalid type")

time_widget = TimeWidget(Widget)


class DynamicSpan(Widget):
    def render(self):
        """
        Returns:
            string: An HTML and JS string that can be directly added as one would add any HTML inline block tag
        """
        return("""<span id="%s">
        <script type="text/javascript">
        var upd = function(val)
        {
            document.getElementById("%s").innerHTML=val;
        }
        KWidget_subscribe('%s',upd);
        </script>%s
        </span>"""%(self.uuid,self.uuid,self.uuid,self.value))

class TextDisplay(Widget):
    def render(self,height='4em',width='24em'):
        """
        Returns:
            string: An HTML and JS string that can be directly added as one would add any HTML inline block tag
        """
        #We only want to update the div when it has changed, otherwise some browsers might not let you click the links
        return("""<div style="height:%s; width:%s; overflow-x:auto; overflow-y:scroll;" class="widgetcontainer" id="%s">
        <script type="text/javascript">
        KWidget_%s_prev = "PlaceHolder1234";
        var upd = function(val)
        {
            if(val == KWidget_%s_prev || val==null)
            {

            }
            else
            {
                document.getElementById("%s").innerHTML=val;
                KWidget_%s_prev = val;
            }
        }
        KWidget_subscribe('%s',upd);
        </script>%s
        </div>"""%(height,width, self.uuid, self.uuid, self.uuid, self.uuid,self.uuid,self.uuid,self.value))

#Gram is the base unit even though Si has kg as the base
#Because it makes it *SO* much easier
siUnits={
    "m","Pa","g","V","A"
}
class Meter(Widget):
    def __init__(self,*args,**kwargs):
        self.k = kwargs
        if not 'high' in self.k:
            self.k['high'] = 10000
        if not 'high_warn' in self.k:
            self.k['high_warn'] = self.k['high']
        if not 'low' in self.k:
            self.k['low'] = -10000
        if not 'low_warn' in self.k:
            self.k['low_warn'] = self.k['low']
        if not 'min' in self.k:
            self.k['min'] = 0
        if not 'max' in self.k:
            self.k['max'] = 100
        
        self.displayUnits = None
        if not 'unit' in kwargs:
            self.unit = None
        else:
            try:
                ##Throw an error if you give it a bad unit
                self.unit = kwargs['unit']
                #Do a KeyError if we don't support the unit
                unitTypes[self.unit]+"_format"
            except:
                self.unit = None
                logging.exception("Bad unit")


        Widget.__init__(self,*args,**kwargs)
        self.value = [0,'normal',self.formatForUser(0)]

    def write(self,value,push=True):
        #Decide a class so it can show red or yellow with high or low values.
        self.c = "normal"

        if 'high_warn' in self.k:
            if value >= self.k['high_warn']:
                self.c = 'warning'

        if 'low_warn' in self.k:
            if value <= self.k['low_warn']:
                self.c = 'warning'

        if 'high' in self.k:
            if value >= self.k['high']:
                self.c = 'error'

        if 'low' in self.k:
            if value <= self.k['low']:
                self.c = 'error'
        self.value = [round(value,3),self.c, self.formatForUser(value)]
        Widget.write(self,self.value,push)

    def setup(self,min,max,high,low,unit=None,displayUnits=None):
        "On-the-fly change of parameters"
        d={'high':high,'low':low,'high_warn':high,'low_warn':low,"min":min,"max":max}
        self.k.update(d)

        if not unit:
            self.unit = None
        else:
            self.displayUnits = displayUnits
            try:
                ##Throw an error if you give it a bad unit
                self.unit = unit

                #Do a KeyError if we don't support the unit
                unitTypes[self.unit]+"_format"
            except:
                logging.exception("Bad unit")
                self.unit = None
        Widget.write(self,self.value+[d])

    def onUpdate(self,*a,**k):
        raise RuntimeError("Only the server can edit this widget")

    def formatForUser(self,v):
        """Format the value into something for display, like 27degC, if we have a unit configured.
            Otherwise just return the value
        """
        if self.unit:
            s = ''

            x=unitTypes[self.unit]

            if x in defaultDisplayUnits:
                units = defaultDisplayUnits[x]
            else:
                return str(round(v,3))
            #Overrides are allowed, we ignorer the user specified units
            if self.displayUnits:
                units = self.displayUnits
            else:
                if not self.unit in units:
                    units+="|"+self.unit 
           # else:
            #    units = auth.getUserSetting(pages.getAcessingUser(),dimensionality_strings[self.unit.dimensionality]+"_format").split("|")

            for i in units.split("|"):
                if s:
                    s+=" | "
                #Si abbreviations and symbols work with prefixes
                if i in siUnits:
                    s+=unitsofmeasure.siFormatNumber(convert(v, self.unit, i))+i
                else:
                    #If you need more than three digits,
                    #You should probably use an SI prefix.
                    #We're just hardcoding this for now
                    s += str(round(convert(v, self.unit, i),2))+i
            
            return s
        else:
            return str(round(v,3))
        

    def render(self,unit='',label=None):
        label= label or self.defaultLabel
        return("""
        <div class="widgetcontainer meterwidget">
        <b>{label}</b><br>
        <span class="numericpv" id="{uuid}" style=" margin:0px;">
        <script type="text/javascript">
        var upd = function(val)
        {{
            document.getElementById("{uuid}_m").value=val[0];
            document.getElementById("{uuid}").className=val[1]+" numericpv";
            document.getElementById("{uuid}").innerHTML=val[2]+"<span style="color:grey>{unit}</span>";

            if(val[3])
            {{
                document.getElementById("{uuid}_m").high = val[3].high;
                document.getElementById("{uuid}_m").low = val[3].low;
                document.getElementById("{uuid}_m").min = val[3].min;
                document.getElementById("{uuid}_m").max = val[3].max;
            }}
        }}
        KWidget_subscribe('{uuid}',upd);
        </script>{valuestr}
        </span></br>
        <meter id="{uuid}_m" value="{value:f}" min="{min:f}" max="{max:f}" high="{high:f}" low="{low:f}"></meter>

        </div>""".format(uuid=self.uuid, value=self.value[0], min=self.k['min'],
        max=self.k['max'],high=self.k['high_warn'],low=self.k['low_warn'],label=label,unit=unit,valuestr=self.formatForUser(self.value[0])))

class Button(Widget):

    def render(self,content,type="default"):
        if type=="default":
            return("""
            <button %s type="button" id="%s" onmousedown="KWidget_sendValue('%s','pushed')" onmouseleave="KWidget_sendValue('%s','released')" onmouseup="KWidget_sendValue('%s','released')">%s</button>
             """%(self.isWritable(),self.uuid,self.uuid,self.uuid,self.uuid,content))

        if type=="trigger":
            return("""
            <div class="widgetcontainer">
            <script type="text/javascript">
            function %s_toggle()
            {
                if(!document.getElementById("%s_2").disabled)
                {
                    isarmed_%s = false;
                    document.getElementById("%s_1").innerHTML="ARM";
                    document.getElementById("%s_2").disabled=true;
                    document.getElementById("%s_3").style='';

                }
                else
                {
                    document.getElementById("%s_1").innerHTML="DISARM";
                    document.getElementById("%s_2").disabled=false;
                    document.getElementById("%s_3").style='background-color:red;';
                }
            }



            </script>
            <button type="button" id="%s_1" onmousedown="%s_toggle()">ARM</button><br/>
            <button type="button" class="triggerbuttonwidget" disabled=true id="%s_2" onmousedown="KWidget_setValue('%s','pushed')" onmouseleave="KWidget_setValue('%s','released')" onmouseup="KWidget_setValue('%s','released')" %s>
            <span id="%s_3">%s</span>
            </button>
            </div>
             """%(self.uuid,self.uuid,self.uuid,self.uuid,self.uuid,self.uuid,self.uuid,self.uuid,self.uuid,self.uuid,self.uuid,self.uuid,self.uuid,self.uuid,self.uuid,self.isWritable(),self.uuid,content))

        raise RuntimeError("Invalid Button Type")


class Slider(Widget):
    def __init__(self,min=0,max=100,step=0.1,*args,**kwargs):
        self.min = min
        self.max = max
        self.step = step
        Widget.__init__(self,*args,**kwargs)
        self.value = 0

    def write(self,value):
        self.value = util.roundto(float(value),self.step)
        #Is this the right behavior?
        self._callback("__SERVER__",value)

    def render(self,type="realtime", orient='vertical',unit='', label=''):

        if orient=='vertical':
            orient='class="verticalslider" orient="vertical"'
        else:
            orient = 'class="horizontalslider"'
        if type=='debug':
            return {'htmlid':mkid(),'id':self.uuid, 'min':self.min, 'step':self.step, 'max':self.max, 'value':self.value, 'unit':unit}
        elif type=='realtime':
            return """<div class="widgetcontainer sliderwidget" ontouchmove = function(e) {e.preventDefault()};>
            <b><p>%(label)s</p></b>
            <input %(en)s type="range" value="%(value)f" id="%(htmlid)s" min="%(min)f" max="%(max)f" step="%(step)f"
            %(orient)s
            onchange="KWidget_setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));"
            oninput="
            %(htmlid)s_clean=%(htmlid)s_cleannext=false;
            KWidget_setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));
            document.getElementById('%(htmlid)s_l').innerHTML= document.getElementById('%(htmlid)s').value+'%(unit)s';
            setTimeout(function(){%(htmlid)s_cleannext=true},150);"
            ><br>
            <span
            class="numericpv"
            id="%(htmlid)s_l">%(value)g%(unit)s</span>
            <script type="text/javascript">
            %(htmlid)s_clean =%(htmlid)s_cleannext= true;
            var upd=function(val){
            if(%(htmlid)s_clean)
            {
            document.getElementById('%(htmlid)s').value= val;
            document.getElementById('%(htmlid)s_l').innerHTML= (Math.round(val*1000)/1000).toPrecision(5).replace(/\.?0*$$/, "")+"%(unit)s";
            }
            %(htmlid)s_clean =%(htmlid)s_cleannext;
            }

            KWidget_subscribe("%(id)s",upd);
            </script>

            </div>"""%{'label':label, 'orient':orient,'en':self.isWritable(), 'htmlid':mkid(),'id':self.uuid, 'min':self.min, 'step':self.step, 'max':self.max, 'value':self.value,  'value':self.value,'unit':unit}

        elif type=='onrelease':
            return """<div class="widgetcontainer sliderwidget">
            <b><p">%(label)s</p></b>
            <input %(en)s type="range" value="%(value)f" id="%(htmlid)s" min="%(min)f" max="%(max)f" step="%(step)f"
            %(orient)s
            oninput="document.getElementById('%(htmlid)s_l').innerHTML= document.getElementById('%(htmlid)s').value+'%(unit)s'; document.getElementById('%(htmlid)s').lastmoved=(new Date).getTime();"
            onmouseup="KWidget_setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"
            onmousedown="document.getElementById('%(htmlid)s').jsmodifiable = false;"
            onkeyup="KWidget_setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"
            ontouchend="KWidget_setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"
            ontouchstart="document.getElementById('%(htmlid)s').jsmodifiable = false;"
            ontouchleave="KWidget_setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"


            ><br>
            <span class="numericpv" id="%(htmlid)s_l">%(value)f%(unit)s</span>
            <script type="text/javascript">
            var upd=function(val){

                if(document.getElementById('%(htmlid)s').jsmodifiable & ((new Date).getTime()-document.getElementById('%(htmlid)s').lastmoved > 300))
                {
                document.getElementById('%(htmlid)s').value= val;
                document.getElementById('%(htmlid)s_l').innerHTML= val+"%(unit)s";
                }


            }
            document.getElementById('%(htmlid)s').lastmoved=(new Date).getTime();
            document.getElementById('%(htmlid)s').jsmodifiable = true;
            KWidget_subscribe("%(id)s",upd);
            </script>
            </div>"""%{'label':label, 'orient':orient,'en':self.isWritable(),'htmlid':mkid(), 'id':self.uuid, 'min':self.min, 'step':self.step, 'max':self.max, 'value':self.value, 'unit':unit}
        raise ValueError("Invalid slider type:"%str(type))

class Switch(Widget):
    def __init__(self,*args,**kwargs):
        Widget.__init__(self,*args,**kwargs)
        self.value = False

    def write(self,value):
        self.value = bool(value)
        #Is this the right behavior?
        self._callback("__SERVER__",value)

    def render(self,label):
        if self.value:
            x = "checked=1"
        else:
            x =''

        return """<div class="widgetcontainer">
        <label><input %(en)s id="%(htmlid)s" type="checkbox"
        onchange="
        %(htmlid)s_clean = %(htmlid)s_cleannext= false;
        setTimeout(function(){%(htmlid)s_cleannext = true},350);
        KWidget_setValue('%(id)s',document.getElementById('%(htmlid)s').checked)" %(x)s>%(label)s</label>
        <script type="text/javascript">
        %(htmlid)s_clean=%(htmlid)s_cleannext = true;
        var upd=function(val){
            if(%(htmlid)s_clean)
            {
            document.getElementById('%(htmlid)s').checked= val;
            }
            %(htmlid)s_clean=%(htmlid)s_cleannext;

        }
        KWidget_subscribe("%(id)s",upd);
        </script>
        </div>"""%{'en':self.isWritable(),'htmlid':mkid(),'id':self.uuid,'x':x, 'value':self.value, 'label':label}

class TagPoint(Widget):
    def __init__(self,tag):
        Widget.__init__(self)
        self.tag = tag

    def write(self,value):
        self.value = bool(value)
        #Is this the right behavior?
        self._callback("__SERVER__",value)

    def render(self,label):
        if self.value:
            x = "checked=1"
        else:
            x =''
        if type=='realtime':
            sl= """<div class="widgetcontainer sliderwidget" ontouchmove = function(e) {e.preventDefault()};>
            <b><p>%(label)s</p></b>
            <input %(en)s type="range" value="%(value)f" id="%(htmlid)s" min="%(min)f" max="%(max)f" step="%(step)f"
            oninput="
            %(htmlid)s_clean=%(htmlid)s_cleannext=false;
            KWidget_setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));
            document.getElementById('%(htmlid)s_l').innerHTML= document.getElementById('%(htmlid)s').value+'%(unit)s';
            setTimeout(function(){%(htmlid)s_cleannext=true},150);"
            ><br>
            <span
            class="numericpv"
            id="%(htmlid)s_l">%(value)f%(unit)s</span>
            <script type="text/javascript">
            %(htmlid)s_clean =%(htmlid)s_cleannext= true;
            var upd=function(val){
            if(%(htmlid)s_clean)
            {
            document.getElementById('%(htmlid)s').value= val;
            document.getElementById('%(htmlid)s_l').innerHTML= (Math.round(val*1000)/1000)+"%(unit)s";
            }
            %(htmlid)s_clean =%(htmlid)s_cleannext;
           }

           KWidget_subscribe("%(id)s",upd);
           </script>

            </div>"""%{'label':label,'en':self.isWritable(), 'htmlid':mkid(),'id':self.uuid, 'min':self.tag.min, 'step':self.step, 'max':self.tag.max, 'value':self.value, 'unit':unit}

        if type=='onrelease':
            sl= """<div class="widgetcontainer sliderwidget">
            <b><p">%(label)s</p></b>
            <input %(en)s type="range" value="%(value)f" id="%(htmlid)s" min="%(min)f" max="%(max)f" step="%(step)f"
            oninput="document.getElementById('%(htmlid)s_l').innerHTML= document.getElementById('%(htmlid)s').value+'%(unit)s'; document.getElementById('%(htmlid)s').lastmoved=(new Date).getTime();"
            onmouseup="KWidget_setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"
            onmousedown="document.getElementById('%(htmlid)s').jsmodifiable = false;"
            onkeyup="KWidget_setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"
            ontouchend="KWidget_setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"
            ontouchstart="document.getElementById('%(htmlid)s').jsmodifiable = false;"
            ontouchleave="KWidget_setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"


            ><br>
            <span class="numericpv" id="%(htmlid)s_l">%(value)f%(unit)s</span>
            <script type="text/javascript">
            var upd=function(val){

                if(document.getElementById('%(htmlid)s').jsmodifiable & ((new Date).getTime()-document.getElementById('%(htmlid)s').lastmoved > 300))
                {
                document.getElementById('%(htmlid)s').value= val;
                document.getElementById('%(htmlid)s_l').innerHTML= val+"%(unit)s";
                }


            }
            document.getElementById('%(htmlid)s').lastmoved=(new Date).getTime();
            document.getElementById('%(htmlid)s').jsmodifiable = true;
            KWidget_subscribe("%(id)s",upd);
            </script>
            </div>"""%{'label':label,'en':self.isWritable(),'htmlid':mkid(), 'id':self.uuid, 'min':self.min, 'step':self.step, 'max':self.max, 'value':self.value, 'unit':unit}

        return """<div class="widgetcontainer">"""+sl+"""


        <label><input %(en)s id="%(htmlid)sman" type="checkbox"
        onchange="
        %(htmlid)s_clean = %(htmlid)s_cleannext= false;
        setTimeout(function(){%(htmlid)s_cleannext = true},350);
        KWidget_setValue('%(id)s',(document.getElementById('%(htmlid)sman').checked))" %(x)s>Manual</label>
        <script type="text/javascript">
        %(htmlid)s_clean=%(htmlid)s_cleannext = true;
        var upd=function(val){
            if(%(htmlid)s_clean)
            {
            document.getElementById('%(htmlid)sman').checked= val;
            }
            %(htmlid)s_clean=%(htmlid)s_cleannext;

        }
        KWidget_subscribe("%(id)s",upd);
        </script>
        </div>"""%{'en':self.isWritable(),'htmlid':mkid(),'id':self.uuid,'x':x, 'value':self.value, 'label':label}

class TextBox(Widget):
    def __init__(self,*args,**kwargs):
        Widget.__init__(self,*args,**kwargs)
        self.value = ''

    def write(self,value):
        self.value = str(value)
        #Is this the right behavior?
        self._callback("__SERVER__",value)

    def render(self,label):
        if self.value:
            x = "checked=1"
        else:
            x =''

        return """<div class="widgetcontainer">
        <label>%(label)s<input %(en)s id="%(htmlid)s" type="text"
        onblur="%(htmlid)s_clean= true;"
        onfocus=" %(htmlid)s_clean = false;"
        oninput="
        KWidget_setValue('%(id)s',document.getElementById('%(htmlid)s').value)
        "
                ></label>
        <script type="text/javascript">
 %(htmlid)s_clean = true;
        var upd=function(val){
            if(%(htmlid)s_clean)
            {
            document.getElementById('%(htmlid)s').value= val;
            }
        }
        KWidget_subscribe("%(id)s",upd);
        </script>
        </div>"""%{'en':self.isWritable(),'htmlid':mkid(),'id':self.uuid,'x':x, 'value':self.value, 'label':label}



class ScrollingWindow(Widget):
    """A widget used for chatroom style scrolling text. 
       Only the new changes are ever pushed over the net. To use, just write the HTML to it, it will
       go into a nev div in the log, old entries automatically go away, use the length param to decide
       how many to keep"""
    def __init__(self,length=250,*args,**kwargs):
        Widget.__init__(self,*args,**kwargs)
        self.value = []
        self.maxlen = length
        self.lock = threading.Lock()
        
    def write(self,value):
        with self.lock:
            self.value.append(str(value))
            self.value = self.value[-self.maxlen:]
            self.send(value)
            self._callback("__SERVER__",value)

    def render(self,cssclass='',style=''):
        
        content = ''.join(["<div>"+i+"</div>" for i in self.value])
        
        return """<div class="widgetcontainer" style="display:block;width:90%%;">
        <div id=%(htmlid)s class ="scrollbox %(cssclass)s" style="%(style)s">
        %(content)s
        </div>
        <script type="text/javascript">
        var d=document.getElementById('%(htmlid)s');
        d.scrollTop = d.scrollHeight;
        var upd=function(val){
            var d=document.getElementById('%(htmlid)s');

            //Detect end of scroll, so we can keep it there if that's where we are at
            var isscrolled =d.scrollTop+d.clientHeight+35 >= d.scrollHeight;

            if (d.childNodes.length>%(maxlen)d)
            {
                d.removeChild(d.childNodes[0])
            }
            var n = document.createElement("div");
            n.innerHTML= val;
            d.appendChild(n);
            //Scroll to bottom if user was already there.
            if (isscrolled)
            {
                d.scrollTop = d.scrollHeight;
            }
        }
        KWidget_subscribe("%(id)s",upd);
        </script>
        </div>"""%{'htmlid':mkid(), 'maxlen':self.maxlen, 'content':content, 
                    'cssclass':cssclass, 'style':style, 'id':self.uuid}





class APIWidget(Widget):
        def __init__(self,echo=True,*args,**kwargs):
            Widget.__init__(self,*args,**kwargs)
            self.value = None
            self.echo=echo

        def render(self,htmlid):
            return """
            <script>
                %(htmlid)s = {};
                %(htmlid)s.value = "Waiting..."
                %(htmlid)s.clean = 0;
                %(htmlid)s._maxsyncdelay = 250
                %(htmlid)s.timeSyncInterval = 600*1000;

                %(htmlid)s._timeref = [performance.now()-1000000,%(loadtime)f-1000000]
                var onTimeResponse = function (val)
                {
                    if(Math.abs(val[0]-%(htmlid)s._txtime)<0.1)
                        {
                            var t = performance.now();
                            if(t-%(htmlid)s._txtime<%(htmlid)s._maxsyncdelay)
                                {
                            %(htmlid)s._timeref = [(t+%(htmlid)s._txtime)/2, val[1]]

                            %(htmlid)s._maxsyncdelay = (t-%(htmlid)s._txtime)*1.2;
                            }
                            else
                                {

                                    %(htmlid)s._maxsyncdelay= %(htmlid)s._maxsyncdelay*2;
                                }
                        }
                }

                var _upd = function(val)
                    {
                        if (%(htmlid)s.clean==0)
                            {
                                 %(htmlid)s.value = val;
                            }
                        else
                            {
                                %(htmlid)s.clean -=1;
                            }
                        %(htmlid)s.upd(val)
                    }

                %(htmlid)s.upd = function(val)
                        {
                        }
                %(htmlid)s.getTime = function()
                    {
                        var x = performance.now()
                        %(htmlid)s._txtime =x;
                        KWidget_sendValue("_ws_timesync_channel",x)
                    }


                %(htmlid)s.now = function(val)
                        {
                            var t=performance.now()
                            if(t-%(htmlid)s._txtime>%(htmlid)s.timeSyncInterval)
                                {
                                    %(htmlid)s.getTime();
                                }
                            return((t-%(htmlid)s._timeref[0])+%(htmlid)s._timeref[1])
                        }

                %(htmlid)s.set = function(val)
                    {
                         KWidget_setValue("%(id)s", val);
                         %(htmlid)s.clean = 2;
                    }

                %(htmlid)s.send = function(val)
                    {
                         KWidget_sendValue("%(id)s", val);
                         %(htmlid)s.clean = 2;
                    }

                    KWidget_subscribe("_ws_timesync_channel",onTimeResponse)
                    KWidget_subscribe("%(id)s",_upd);
                    setTimeout(%(htmlid)s.getTime,500)
                    setTimeout(%(htmlid)s.getTime,1500)
                    setTimeout(%(htmlid)s.getTime,3000)
                    setTimeout(%(htmlid)s.getTime,10000)


            </script>
            """%{'htmlid':htmlid, 'id' :self.uuid, 'value': json.dumps(self.value),'loadtime':time.time()*1000}


t = APIWidget(echo=False,id='_ws_timesync_channel')
def f(s,v,id):
    t.sendTo([v,time.time()*1000],id)
t.attach2(f)