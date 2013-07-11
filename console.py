
_user_interpreters = {}

import cherrypy
import pages
import auth
import kaithem
import sys,time

    

class UserConsole():
    def __init__(self,user):
        self.buffer = []
        self.locals = {'kaithem':kaithem.kaithem}
        self.lastactivity = time.time()
        
    def push(self,line):
        self.lastactivity = time.time()
        x = eval(line,self.locals)
        self.buffer.append('>>>'+line)
        self.buffer.append(x)
        self.buffer=self.buffer[-50:]
        return x
    
class Console(object):
    @cherrypy.expose
    def console(self,**kwargs):
        pages.require("/admin/console.acess")
        user = auth.whoHasToken(cherrypy.request.cookie['auth'].value)
        if user not in _user_interpreters:
            _user_interpreters[user] = UserConsole(user)
        
        if 'line' in kwargs:
            _user_interpreters[user].push(kwargs['line'])
            
        return pages.get_template('console.html').render(console = _user_interpreters[user])
    
    def resetlocals(self,**kwargs):
        pages.require("/admin/console.acess")
        user = auth.whoHasToken(cherrypy.request.cookie['auth'].value)
        _user_interpreters[user].locals={'kaithem':kaithem.kaithem}
        return pages.get_template('console.html').render(console = _user_interpreters[user]) 