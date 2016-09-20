#Copyright Daniel Dunn 2014-2015
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
import weakref,time,json,base64,cherrypy,os, traceback,random,threading
from . import auth,pages,unitsofmeasure,config,util,messagebus
from src.config import config

#Modify lock for any websocket's subscriptions
subscriptionLock = threading.Lock()
if config['enable-websockets']:
    from ws4py.websocket import WebSocket
widgets = weakref.WeakValueDictionary()
n = 0

server_session_ID= str(time.time())+str(os.urandom(8))
def mkid():
    global n
    n=(n+1)%10000
    return('id'+str(n))


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
            widgets[i]._onUpdate(user,upd[i])

        for i in req:
            resp[i] = widgets[i]._onRequest(user)

        return json.dumps(resp)

    @cherrypy.expose
    def ws(self):
        # you can access the class instance through
        if not config['enable-websockets']:
            raise RuntimeError("Websockets disabled in server config")
        handler = cherrypy.request.ws_handler
        if cherrypy.request.scheme == 'https':
            handler.user = pages.getAcessingUser()
        else:
            handler.user = "__guest__"

    @cherrypy.expose
    def ws_allowed(self):
        return str(config['enable-websockets'])

    @cherrypy.expose
    def session_id(self):
        return server_session_ID

def subsc_closure(self,i):
    def f(msg):
        try:
            self.send(json.dumps([[i,msg]]))
        except:
            messagebus.postMessage("system/errors/widgets/websocket", traceback.format_exc(6))
    return f

if config['enable-websockets']:
    class websocket(WebSocket):
        def __init__(self,*args,**kwargs):
            self.subscriptions = []
            self.lastPushedNewData = 0
            WebSocket.__init__(self,*args,**kwargs)

        def closed(self,code,reason):
            with subscriptionLock:
                for i in self.subscriptions:
                    try:
                        widgets[i].subscriptions.pop(self.user)
                        widgets[i].subscriptions_atomic = widgets[i].subscriptions.copy()
                    except:
                        pass

        def received_message(self,message):
            try:
                o = json.loads(message.data.decode('utf8'))
                resp = []
                user = self.user
                req = o['req']
                upd = o['upd']

                for i in upd:
                    widgets[i[0]]._onUpdate(user,i[1])

                for i in req:
                    resp.append([i, widgets[i]._onRequest(user)])

                if 'subsc' in o:
                    for i in o['subsc']:
                        if i in self.subscriptions:
                            continue
                        if i == "__WIDGETERROR__":
                            continue

                        with subscriptionLock:
                            widgets[i].subscriptions[self.user] = subsc_closure(self,i)
                            widgets[i].subscriptions_atomic = widgets[i].subscriptions.copy()
                        self.subscriptions.append(i)
                        resp.append([i, widgets[i]._onRequest(user)])
                        self.send(json.dumps(resp))

            except Exception as e:
                messagebus.postMessage("system/errors/widgets/websocket", traceback.format_exc(6))
                self.send(json.dumps({'__WIDGETERROR__':repr(e)}))

class Widget():
    def __init__(self,*args,**kwargs):
        self._value = None
        self._read_perms = []
        self._write_perms=[]
        self.errored_function = None
        self.errored_getter = None
        self.subscriptions = {}
        self.subscriptions_atomic = {}

        def f(u,v):
            pass

        self._callback = f

        #Give the widget an ID for the client to refer to it by
        if not 'id' in kwargs:
            self.uuid = "id"+base64.b64encode(os.urandom(16)).decode().replace("/",'').replace("-",'').replace('+','')[:-2]
        else:
            self.uuid = kwargs['id']

        #Insert self into the widgets list
        widgets[self.uuid] = self

    #This function is called by the web interface code
    def _onRequest(self,user):
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
            return self.onRequest(user)
        except Exception as e:
            messagebus.postMessage("/system/errors/widgets", traceback.format_exc(6))
            if not (self.errored_getter == id(self._callback)):
                messagebus.postMessage("/system/notifications/errors", "Error in widget getter function %s defined in module %s, see logs for traceback.\nErrors only show the first time a function has an error until it is modified or you restart Kaithem."
                                        %(self._callback.__name__, self._callback.__module__))
                self.errored_getter = id(self._callback)

    #This function is meant to be overridden or used as is
    def onRequest(self,user):
        """This function is called after permissions have been verified when a client requests the current value. Usually just returns self._value

        Args:
            user(string):
                The username of the acessung client
        """
        return self._value

    #This function is called by the web interface whenever this widget is written to
    def _onUpdate(self,user,value):
        """Called internally to write a value to the widget. Responisble for verifying permissions. Returns if user does not have permission"""
        for i in self._read_perms:
            if not auth.canUserDoThis(user,i):
                return

        for i in self._write_perms:
            if not auth.canUserDoThis(user,i):
                return

        self.onUpdate(user,value)
        try:
            self._callback(user,value)
        except Exception as e:
            messagebus.postMessage("/system/errors/widgets", traceback.format_exc(6))
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

    #meant to be overridden or used as is
    def onUpdate(self,user,value):
        self._value = value
        self.push(value)

    #Read and write are called by code on the server
    def read(self):
        return self._value

    def write(self,value):
        self._value = value
        self.push(value)

    def push(self,value,users=None):
        #Is this the right behavior?
        self._callback("__SERVER__",value)
        for i in self.subscriptions_atomic:
            self.subscriptions_atomic[i](value)

    #Lets you add permissions that are required to read or write the widget.
    def require(self,permission):
        self._read_perms.append(permission)

    def requireToWrite(self,permission):
        self._write_perms.append(permission)


#This widget is just a time display, it doesn't really talk to the server, but it's useful to keep the same interface.
class TimeWidget(Widget):
    def onRequest(self,user):
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
            <script type="text/javascript" src="/static/strftime-min.js">
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

        if type=='inline':
            return("""<span id="%s">
            <script type="text/javascript" src="/static/strftime-min.js">
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
        </span>"""%(self.uuid,self.uuid,self.uuid,self._value))

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
        </div>"""%(height,width, self.uuid, self.uuid, self.uuid, self.uuid,self.uuid,self.uuid,self._value))


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


        Widget.__init__(self,*args,**kwargs)
        self._value = [0,'normal']

    def write(self,value):
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

        Widget.write(self,[round(value,3),self.c])

    def render(self,unit='',label=''):
        return("""
        <div class="widgetcontainer meterwidget">
        <b>%s</b><br>
        <span class="numericpv" id="%s" style=" margin:0px;">
        <script type="text/javascript">
        var upd = function(val)
        {
            document.getElementById("%s").innerHTML=val[0]+"%s";
            document.getElementById("%s_m").value=val[0];
            document.getElementById("%s").className=val[1]+" numericpv";
        }
        KWidget_subscribe('%s',upd);
        </script>%s
        </span></br>
        <meter id="%s_m" value="%d" min="%d" max="%d" high="%d" low="%d"></meter>

        </div>"""%(label,self.uuid,
                          self.uuid,unit,self.uuid,self.uuid,self.uuid,self._value[0],
                          self.uuid,self._value[0], self.k['min'],self.k['max'],self.k['high_warn'],self.k['low_warn']

                          ))

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
            <button type="button" class="triggerbuttonwidget" disabled=true id="%s_2" onmousedown="KWidget_setValue('%s','ped')" onmouseleave="KWidget_setValue('%s','released')" onmouseup="KWidget_setValue('%s','released')" %s>
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
        self._value = 0

    def write(self,value):
        self._value = util.roundto(float(value),self.step)
        #Is this the right behavior?
        self._callback("__SERVER__",value)

    def render(self,type="realtime", orient='vertical',unit='', label=''):

        if orient=='vertical':
            orient='class="verticalslider" orient="vertical"'
        else:
            orient = 'class="horizontalslider"'
        if type=='debug':
            return {'htmlid':mkid(),'id':self.uuid, 'min':self.min, 'step':self.step, 'max':self.max, 'value':self._value, 'unit':unit}
        if type=='realtime':
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

            </div>"""%{'label':label, 'orient':orient,'en':self.isWritable(), 'htmlid':mkid(),'id':self.uuid, 'min':self.min, 'step':self.step, 'max':self.max, 'value':self._value, 'unit':unit}

        if type=='onrelease':
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
            </div>"""%{'label':label, 'orient':orient,'en':self.isWritable(),'htmlid':mkid(), 'id':self.uuid, 'min':self.min, 'step':self.step, 'max':self.max, 'value':self._value, 'unit':unit}
            raise ValueError("Invalid slider type:"%str(type))

class Switch(Widget):
    def __init__(self,*args,**kwargs):
        Widget.__init__(self,*args,**kwargs)
        self._value = False

    def write(self,value):
        self._value = bool(value)
        #Is this the right behavior?
        self._callback("__SERVER__",value)

    def render(self,label):
        if self._value:
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
        </div>"""%{'en':self.isWritable(),'htmlid':mkid(),'id':self.uuid,'x':x, 'value':self._value, 'label':label}

class TagPoint(Widget):
    def __init__(self,tag):
        Widget.__init__(self)
        self.tag = tag

    def write(self,value):
        self._value = bool(value)
        #Is this the right behavior?
        self._callback("__SERVER__",value)

    def render(self,label):
        if self._value:
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

            </div>"""%{'label':label,'en':self.isWritable(), 'htmlid':mkid(),'id':self.uuid, 'min':self.tag.min, 'step':self.step, 'max':self.tag.max, 'value':self._value, 'unit':unit}

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
            </div>"""%{'label':label,'en':self.isWritable(),'htmlid':mkid(), 'id':self.uuid, 'min':self.min, 'step':self.step, 'max':self.max, 'value':self._value, 'unit':unit}

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
        </div>"""%{'en':self.isWritable(),'htmlid':mkid(),'id':self.uuid,'x':x, 'value':self._value, 'label':label}

class TextBox(Widget):
    def __init__(self,*args,**kwargs):
        Widget.__init__(self,*args,**kwargs)
        self._value = ''

    def write(self,value):
        self._value = str(value)
        #Is this the right behavior?
        self._callback("__SERVER__",value)

    def render(self,label):
        if self._value:
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
        </div>"""%{'en':self.isWritable(),'htmlid':mkid(),'id':self.uuid,'x':x, 'value':self._value, 'label':label}

class APIWidget(Widget):
        def __init__(self,*args,**kwargs):
            Widget.__init__(self,*args,**kwargs)
            self._value = None

        def render(self,htmlid):
            return """
            <script>
                %(htmlid)s = {};
                %(htmlid)s.value = "Waiting..."
                %(htmlid)s.clean = 0;

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


                %(htmlid)s.set = function(val)
                    {
                         KWidget_setValue("%(id)s", val);
                         %(htmlid)s.clean = 2;
                    }

                    KWidget_subscribe("%(id)s",_upd);
            </script>
            """%{'htmlid':htmlid, 'id' :self.uuid, 'value': json.dumps(self._value)}
