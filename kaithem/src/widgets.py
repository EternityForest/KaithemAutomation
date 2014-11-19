import weakref,time,json,base64,cherrypy,os
from . import auth,pages,unitsofmeasure,config
from src.config import config
if config['enable-websockets']:
    from ws4py.websocket import WebSocket
widgets = weakref.WeakValueDictionary()
n = 0

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
    
if config['enable-websockets']:
    class websocket(WebSocket):        
        def received_message(self,message):
            try:
                o = json.loads(message.data.decode('utf8'))
                resp = {}
                user = self.user
                req = o['req']
                upd = o['upd']
                
                for i in upd:
                    widgets[i]._onUpdate(user,upd[i])
        
                for i in req:
                    resp[i] = widgets[i]._onRequest(user)
                
                self.send(json.dumps(resp))
            except Exception as e:
                self.send(repr(e)+ " xyz")

class Widget():
    def __init__(self,*args,**kwargs):
        self._value = None
        self._read_perms = []
        self._write_perms=[]
        
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
        return the value for the widget. For example a slider might request the newest value
        """
        for i in self._read_perms:
            if not auth.canUserDoThis(user,i):
                return
            
        return self.onRequest(user)
    
    #This function is meant to be overridden or used as is
    def onRequest(self,user):   
        return self._value
    
    #This function is called by the web interface whenever this widget is written to
    def _onUpdate(self,user,value):
        for i in self._read_perms:
            if not auth.canUserDoThis(user,i):
                return
            
        for i in self._write_perms:
            if not auth.canUserDoThis(user,i):
                return
            
        self.onUpdate(user,value)
        self._callback(user,value)
        
    #Return True if this user can write to it
    def isWritable(self):
        for i in self._write_perms:
            if not auth.canUserDoThis(pages.getAcessingUser(),i):
                return "disabled"
        return ""
        
    #Set a callback if it ever changes
    def attach(self,f):
        self._callback = f
    
    #meant to be overridden or used as is
    def onUpdate(self,user,value):
        self._value = value
    
    #Read and write are called by code on the server
    def read(self):
        return self._value
    
    def write(self,value):
        self._value = str(value)
        #Is this the right behavior?
        self._callback("__SERVER__",value)
    
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
        return("""<span id="%s">
        <script type="text/javascript">
        var upd = function(val)
        {
            document.getElementById("%s").innerHTML=val;
        }
        KWidget_register('%s',upd);
        </script>%s
        </span>"""%(self.uuid,self.uuid,self.uuid,self._value))

class TextDisplay(Widget):
    def render(self,height='4em',width='24em'):
        return("""<div style="height:%s; width:%s; overflow-x:auto; overflow-y:scroll;" class="widgetcontainer" id="%s">
        <script type="text/javascript">
        var upd = function(val)
        {
            document.getElementById("%s").innerHTML=val;
        }
        KWidget_register('%s',upd);
        </script>%s
        </span>"""%(height,width, self.uuid,self.uuid,self.uuid,self._value))


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
                
        self._value=[round(value,3),self.c]
        
    def render(self,unit=''):
        return("""
        <div class="widgetcontainer meterwidget">
        <span class="numericpv" id="%s" style=" margin:0px;">
        <script type="text/javascript">
        var upd = function(val)
        {
            document.getElementById("%s").innerHTML=val[0]+"%s";
            document.getElementById("%s_m").value=val[0];
            document.getElementById("%s").className=val[1]+" numericpv";
        }
        KWidget_register('%s',upd);
        </script>%s
        </span></br>
        <meter id="%s_m" value="%d" min="%d" max="%d" high="%d" low="%d"></meter>

        </div>"""%(self.uuid,
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
            <button type="button" class="triggerbuttonwidget" disabled=true id="%s_2" onmousedown="KWidget_sendValue('%s','pushed')" onmouseleave="KWidget_sendValue('%s','released')" onmouseup="KWidget_sendValue('%s','released')" %s>
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

    
    def render(self,type="realtime", orient='vertical',unit=''):
        
        if orient=='vertical':
            orient='class="verticalslider" orient="vertical"'
        else:
            orient = 'class="horizontalslider"'
        if type=='debug':
            return {'htmlid':mkid(),'id':self.uuid, 'min':self.min, 'step':self.step, 'max':self.max, 'value':self._value, 'unit':unit}
        if type=='realtime':
            return """<div class="widgetcontainer sliderwidget">
            <input %(en)s type="range" value="%(value)f" id="%(htmlid)s" min="%(min)f" max="%(max)f" step="%(step)f"
            %(orient)s
           oninput="
           %(htmlid)s_clean=false;
           KWidget_setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));
           document.getElementById('%(htmlid)s_l').innerHTML= document.getElementById('%(htmlid)s').value+'%(unit)s';
           setTimeout(function(){%(htmlid)s_clean=true},150);"
           ><br>
           <span
           class="numericpv"
           id="%(htmlid)s_l">%(value)f%(unit)s</span>
           <script type="text/javascript">
           %(htmlid)s_clean = true;
           var upd=function(val){
           if(%(htmlid)s_clean)
           {
            document.getElementById('%(htmlid)s').value= val;
            document.getElementById('%(htmlid)s_l').innerHTML= val+"%(unit)s";
            }
           }
                    
           KWidget_register("%(id)s",upd);
           </script>
     
            </div>"""%{'orient':orient,'en':self.isWritable(), 'htmlid':mkid(),'id':self.uuid, 'min':self.min, 'step':self.step, 'max':self.max, 'value':self._value, 'unit':unit}
        
        if type=='onrelease':
            return """<div class="widgetcontainer sliderwidget">
            <input %(en)s type="range" value="%(value)f" id="%(htmlid)s" min="%(min)f" max="%(max)f" step="%(step)f"
            %(orient)s
            onchange="document.getElementById('%(htmlid)s_l').innerHTML= document.getElementById('%(htmlid)s').value+'%(unit)s'; document.getElementById('%(htmlid)s').lastmoved=(new Date).getTime();"
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
            KWidget_register("%(id)s",upd);
            </script>
            </div>"""%{'orient':orient,'en':self.isWritable(),'htmlid':mkid(), 'id':self.uuid, 'min':self.min, 'step':self.step, 'max':self.max, 'value':self._value, 'unit':unit}
            raise ValueError("Invalid slider type:"%str(type))
        
class Switch(Widget):
    def __init__(self,min=0,max=100,step=0.1,*args,**kwargs):
        Widget.__init__(self,*args,**kwargs)
        self._value = False

    
    def render(self,label):
        if self._value:
            x = "checked=1"
        else:
            x =''
            
        return """<div class="widgetcontainer">
        <label><input %(en)s id="%(htmlid)s" type="checkbox" 
        onchange="
        %(htmlid)s_clean = false;
        setTimeout(function(){%(htmlid)s_clean = true},350);
        KWidget_setValue('%(id)s',document.getElementById('%(htmlid)s').checked)" %(x)s>%(label)s</label>
        <script type="text/javascript">
        %(htmlid)s_clean = true;
        var upd=function(val){
            if(%(htmlid)s_clean)
            {
            document.getElementById('%(htmlid)s').checked= val;
            }
        }
        KWidget_register("%(id)s",upd);
        </script>
        </div>"""%{'en':self.isWritable(),'htmlid':mkid(),'id':self.uuid,'x':x, 'value':self._value, 'label':label}
        

