import weakref,time,json,base64,cherrypy,os
from . import auth,pages

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
            resp[i] = widgets[i].onRequest(user)
            
        for i in j['upd']:
            widgets[i].onUpdate(user,upd[i])
        
        return json.dumps(resp)
             

class Widget():
    def __init__(self):
        self._value = None
        self._read_perms = []
        self._write_perms=[]
        self.uuid = base64.b64encode(os.urandom(16)).decode()
        widgets[self.uuid] = self
    
    def onRequest(self,user):
        """Widgets on the client side send AJAX requests for the new value. This function must
        return the value for the widget. For example a slider might request the newest value
        """
        for i in self._read_perms:
            if not auth.canUserDoThis(user,i):
                return
            
        return self._value
    
    def onUpdate(self,user,value):
        for i in self._read_perms:
            if not auth.canUserDoThis(user,i):
                return
            
        for i in self._read_perms:
            if not auth.canUserDoThis(user,i):
                return
        self._value = value
        
class TimeWidget(Widget):
        def onRequest(self,user):
            return str(time.time())
        def render(self):
            return("""<span id="%s">
            <script type="text/javascript">
            function upd(val)
            {
                document.getElementById("%s").innerHTML=val;
            }
            KWidget_register(%s,upd);
            </script>
            </span>)"""%(self.uuid,self.uuid,self.uuid))

    