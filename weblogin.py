import auth
import cherrypy
import pages

auth.initializeAuthentication('auth.txt')


class LoginScreen():
    @cherrypy.expose
    def index(self,**kwargs):
        return pages.get_template("login.html").render()
        
    @cherrypy.expose
    def login(self,**kwargs):
        x = auth.userLogin(kwargs['username'],kwargs['pwd'])
        if not x=='failure':
            #Give the user the security token
            cherrypy.response.cookie['auth'] = x
            cherrypy.response.cookie['auth']['path'] = '/'
            cherrypy.response.cookie['user'] = kwargs['username']
            cherrypy.response.cookie['user']['path'] = '/'
            raise cherrypy.HTTPRedirect("/")
        else:
            return "fail"
            
    @cherrypy.expose
    def logout(self,**kwargs):
        #Change the securit token to make the old one invalid and thus log user out.
        if cherrypy.request.cookie['auth'].value in auth.Tokens:
            auth.assignNewToken(auth.whoHasToken(cherrypy.request.cookie['auth'].value))
        raise cherrypy.HTTPRedirect("/")