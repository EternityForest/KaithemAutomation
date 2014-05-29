import weakref,time,json,base64,cherrypy,os
from . import auth,pages,unitsofmeasure

widgets = weakref.WeakValueDictionary()

class WebInterface():
    @cherrypy.expose
    def index(self,**k):
        j = json.loads(k['json'])
        resp = {}
        user = pages.getAcessingUser()
        req = j['req']
        upd = j['upd']

        for i in req:
            resp[i] = widgets[i]._onRequest(user)
            
        for i in j['upd']:
            widgets[i]._onUpdate(user,upd[i])
        
        return json.dumps(resp)
             

class Widget():
    def __init__(self,id=None):
        self._value = None
        self._read_perms = []
        self._write_perms=[]
        
        def f(u,v):
            pass
        
        self._callback = f
        
        self.uuid = "id"+base64.b64encode(os.urandom(16)).decode().replace("/",'').replace("-",'').replace('+','')[:-2]
        widgets[self.uuid] = self

    
    def _onRequest(self,user):
        """Widgets on the client side send AJAX requests for the new value. This function must
        return the value for the widget. For example a slider might request the newest value
        """
        for i in self._read_perms:
            if not auth.canUserDoThis(user,i):
                return
            
        return self.onRequest(user)
            
    def onRequest(self,user):   
        return self._value
    
    def _onUpdate(self,user,value):
        for i in self._read_perms:
            if not auth.canUserDoThis(user,i):
                return
            
        for i in self._read_perms:
            if not auth.canUserDoThis(user,i):
                return
            
        self.onUpdate(user,value)
        self._callback(user,value)
    
    def attach(self,f):
        self._callback = f
        
    def onUpdate(self,user,value):
        self._value = value
        
    def read(self):
        return self._value
    
    def write(self,value):
        self._value = str(value)
        
class TimeWidget(Widget):
    def onRequest(self,user):
        return str(unitsofmeasure.strftime())
    
    def render(self):
        return("""<span id="%s">
        <script type="text/javascript">
        var upd = function(val)
        {
            document.getElementById("%s").innerHTML=val;
        }
        KWidget_register('%s',upd);
        </script>
        </span>"""%(self.uuid,self.uuid,self.uuid))
            
class DynamicSpan(Widget):
    def render(self):
        return("""<span id="%s">
        <script type="text/javascript">
        var upd = function(val)
        {
            document.getElementById("%s").innerHTML=val;
        }
        KWidget_register('%s',upd);
        </script>
        </span>"""%(self.uuid,self.uuid,self.uuid))

class Button(Widget):

    def render(self,content,type="default"):
        if type=="default":
            return("""
            <button type="button" id="%s" onmousedown="KWidget_sendValue('%s','pushed')" onmouseleave="KWidget_sendValue('%s','released')" onmouseup="KWidget_sendValue('%s','released')">%s</button>
             """%(self.uuid,self.uuid,self.uuid,self.uuid,content))
            
        raise RuntimeError("Invalid Button Type")

    