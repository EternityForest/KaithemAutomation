import pages
import weblogin
import auth
import cherrypy
import ManageUsers
import directories
import os,sys
import modules
import settings
import usrpages


#2 and 3 have basically the same module with diferent names
if sys.version_info < (3,0):
    import urllib2
    #Yes, This really is the only way i know of to get your public IP.
    try:
        u= urllib2.urlopen("http://ipecho.net/plain")
        MyExternalIPAdress = u.read()
    except:
        MyExternalIPAdress = "unknown"
    finally:
        u.close()
else:
    MyExternalIPAdress = "unknown"
    


auth.initializeAuthentication(os.path.join(directories.cfgdir,'users.json'))
modules.loadAll()

class webapproot():

    @cherrypy.expose 
    def index(self,*path,**data):
        #Was there a reason not to use pages.require
        if 'auth' in cherrypy.request.cookie.keys():
            if auth.checkTokenPermission(cherrypy.request.cookie['auth'].value,"/admin/mainpage.view"):
                return pages.get_template('index.html').render(
                user = cherrypy.request.cookie['user'].value,
                myip = MyExternalIPAdress
                                )
        return self.login.index()

    @cherrypy.expose 
    def docs(self,*path,**data):
        return pages.get_template('help/help.html').render()
    @cherrypy.expose 
    def about(self,*path,**data):
        return pages.get_template('help/about.html').render()
    @cherrypy.expose 
    def helpmenu(self,*path,**data):
        return pages.get_template('help/index.html').render()

class Errors():
    @cherrypy.expose 
    def permissionerror(self,):
        return pages.get_template('errors/permissionerror.html').render()
        
root = webapproot()
root.login = weblogin.LoginScreen()
root.auth = ManageUsers.ManageAuthorization()
root.modules = modules.WebInterface()
root.settings = settings.Settings()
root.errors = Errors()
root.pages = usrpages.KaithemPage()

dn = os.path.dirname(os.path.realpath(__file__))
if __name__ == '__main__':
    server_config={
        'server.socket_host': '0.0.0.0',
        'server.socket_port':8001,
        'server.ssl_module':'builtin',
        'server.ssl_certificate':os.path.join(dn,'ssl/certificate.cert'),
        'server.ssl_private_key':os.path.join(dn,'ssl/certificate.key'),

    }

conf = {
        '/static':{'tools.staticdir.on': True,
        'tools.staticdir.dir':os.path.join(dn,'static'),
        'tools.expires.on' : True,
        'tools.expires.secs' : 1000,
        "tools.sessions.on": False
        }
        }
cherrypy.config.update(server_config)
cherrypy.quickstart(root,'/',config=conf)
