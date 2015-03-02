#Copyright Daniel Dunn 2013
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


#This file handles the display of user-created pages
import time,os,threading,traceback
from .import kaithemobj,util,pages,directories,messagebus,systasks,modules_state
import mako, cherrypy

from .config import config

errors = {}

def url_for_resource(module,resource):
    s = "/pages/"
    s += util.url(module)
    s+= "/"
    s+= "/".join([util.url(i) for i in util.split_escape(resource,"/")])
    return s

class CompiledPage():
    def __init__(self, resource,m='unknown',r='unknown'):
        
        template = resource['body']
        self.errors = []
        #For compatibility with older versions, we provide defaults
        #In case some attributes are missing
        if 'require-permissions' in resource:
             self.permissions = resource["require-permissions"]
        else:
            self.permissions = []
        
        if 'allow-xss' in resource:
             self.xss = resource["allow-xss"]
        else:
            self.xss = False
            
        if 'allow-origins' in resource:
            self.origins = resource["allow-origins"]
        else:
            self.origins = []
            
        if 'require-method' in resource:
            self.methods = resource['require-method']
        else:
            self.methods = ['POST','GET']
        
        #Yes, I know this logic is ugly.
        if 'no-navheader' in resource:
            if resource['no-navheader']:
                header = util.readfile(os.path.join(directories.htmldir,'pageheader_nonav.html'))
            else:
                header = util.readfile(os.path.join(directories.htmldir,'pageheader.html'))
        else:
            header = util.readfile(os.path.join(directories.htmldir,'pageheader.html'))
            
        if 'no-header' in resource:
            if resource['no-header']:
                header = ""
        
        if 'auto-reload' in resource:
            if resource['auto-reload']:
                header += '<meta http-equiv="refresh" content="%d">' % resource['auto-reload-interval']
        
        footer = util.readfile(os.path.join(directories.htmldir,'pagefooter.html'))
        
        templatesource = header + template + footer
        self.template = mako.template.Template(templatesource,uri="Template"+m+'_'+r)
            
            
def getPageErrors(module,resource):
    return _Pages[module][resource].errors


_Pages = {}
_page_list_lock = threading.Lock()

#Delete a event from the cache by module and resource
def removeOnePage(module,resource):
    #Look up the eb
    with _page_list_lock:
        if module in _Pages:
            if resource in _Pages[module]:
                    del _Pages[module][resource]
                    
#Delete all __events in a module from the cache
def removeModulePages(module):
    #There might not be any pages, so we use the if
    if module in _Pages:
        del _Pages[module]

#This piece of code will update the actual event object based on the event resource definition in the module
#Also can add a new page
def updateOnePage(resource,module):
    #This is one of those places that uses two different locks
    with modules_state.modulesLock:
        if module not in _Pages:
            _Pages[module]={}
            
        #Get the page resource in question
        j = modules_state.ActiveModules[module][resource]
        _Pages[module][resource] = CompiledPage(j)

def makeDummyPage(resource,module):
        if module not in _Pages:
            _Pages[module]={}
    
        #Get the page resource in question
        j = {
                    "resource-type":"page",
                    "body":"Content here",
                    'no-navheader':True}
        _Pages[module][resource] = CompiledPage(j)
        

#look in the modules and compile all the event code
def getPagesFromModules():
    global _Pages
    with modules_state.modulesLock:
        with _page_list_lock:
            #Set __events to an empty list we can build on
            _Pages = {}
            for i in modules_state.ActiveModules.copy():
                #For each loaded and active module, we make a subdict in _Pages
                _Pages[i] = {} # make an empty place for pages in this module
                #now we loop over all the resources o the module to see which ones are pages 
                for m in modules_state.ActiveModules[i].copy():
                    j=modules_state.ActiveModules[i][m]
                    if j['resource-type']=='page':
                        try:
                            _Pages[i][m] = CompiledPage(j,i,m)
                        except Exception as e:
                            makeDummyPage(m,i)
                            tb = traceback.format_exc()
                            #When an error happens, log it and save the time
                            #Note that we are logging to the compiled event object
                            _Pages[i][m].errors.append([time.strftime(config['time-format']),tb])
                            try:
                                messagebus.postMessage('system/errors/pages/'+
                                                   i+'/'+
                                                   m,str(tb))
                            except Exception as e:
                                print (e)
                            #Keep only the most recent 25 errors
                            
                            #If this is the first error(high level: transition from ok to not ok)
                            #send a global system messsage that will go to the front page.
                            if len(_Pages[i][m].errors)==1:
                                messagebus.postMessage('/system/notifications/errors',
                                                       "Page \""+m+"\" of module \""+i+
                                                       "\" may need attention")

#kaithem.py has come config option that cause this file to use the method dispatcher.
class KaithemPage():
    
    #Class encapsulating one request to a user-defined page
    exposed = True;
    
    def GET(self,module,*args,**kwargs):
        #Workaround for cherrypy decoding unicode as if it is latin 1
        #Because of some bizzare wsgi thing i think.
        module=module.encode("latin-1").decode("utf-8")
        args = [i.encode("latin-1").decode("utf-8") for i in args]
        return self._serve(module,*args, **kwargs)
    
    def POST(self,module,*args,**kwargs):
        #Workaround for cherrypy decoding unicode as if it is latin 1
        #Because of some bizzare wsgi thing i think.
        module=module.encode("latin-1").decode("utf-8")
        args = [i.encode("latin-1").decode("utf-8") for i in args]
        return self._serve(module,*args, **kwargs)
    
    def OPTION(self,module,resource,*args,**kwargs):
        #Workaround for cherrypy decoding unicode as if it is latin 1
        #Because of some bizzare wsgi thing i think.
        module=module.encode("latin-1").decode("utf-8")
        args = [i.encode("latin-1").decode("utf-8") for i in args]
        self._headers(self.lookup(module,args))
        return ""
                
    def _headers(self,page):
        x = ""
        for i in page.methods:
            x+= i + ", "
        x=x[:-2]
        
        cherrypy.response.headers['Allow'] = x + ", HEAD, OPTIONS"
        if page.xss:
            if 'Origin' in cherrypy.request.headers:
                if cherrypy.request.headers['Origin'] in page.origins or '*' in page.origins:
                    cherrypy.response.headers['Access-Control-Allow-Origin'] = cherrypy.request.headers['Origin']
                cherrypy.response.headers['Access-Control-Allow-Methods'] = x 
    
    def lookup(self,module,args):
        resource_path = [i.replace("\\","\\\\").replace("/","\\/") for i in args]
        print(resource_path)
        m = _Pages[module]
        if "/".join(resource_path) in m:
            return _Pages[module]["/".join(resource_path)]
            
        if "/".join(resource_path+['__index__']) in m:
            return _Pages[module][ "/".join(resource_path+['__index__'])]

        while resource_path:
            resource_path.pop()
            if "/".join(resource_path+['__default__']) in m:
                return m["/".join(resource_path+['__default__']) ]
            
        return None

                        
    def _serve(self,module,*args,**kwargs):
        global _page_list_lock
        with _page_list_lock:
            page = self.lookup(module,args)
            if None==page:
                messagebus.postMessage("/system/errors/http/nonexistant", "Someone tried to access a page that did not exist in module %s with path %s"%(module,args))
                raise cherrypy.NotFound()
            page.lastaccessed = time.time()
            #Check user permissions
            for i in page.permissions:
                pages.require(i)
            
            self._headers(page)
            #Check HTTP Method
            if cherrypy.request.method not in page.methods:
                #Raise a redirect the the wrongmethod error page
                raise cherrypy.HTTPRedirect('/errors/wrongmethod')
            try:
                return page.template.render(
                   kaithem = kaithemobj.kaithem,
                   request = cherrypy.request,
                   module = modules_state.scopes[module],
                   path = args,
                   kwargs = kwargs
                   )
            except Exception as e:
                #The HTTPRedirect is NOT an error, and should not be handled like one.
                #So we just reraise it unchanged
                if isinstance(e,cherrypy.HTTPRedirect):
                    raise e
                
                #The way we let users securely serve static files is to simply
                #Give them a function that raises this special exception
                if isinstance(e,kaithemobj.ServeFileInsteadOfRenderingPageException):
                    return cherrypy.lib.static.serve_file(e.f_filepath,e.f_MIME,e.f_name)
                
                tb = traceback.format_exc()
                #When an error happens, log it and save the time
                #Note that we are logging to the compiled event object
                page.errors.append([time.strftime(config['time-format']),tb])
                try:
                    messagebus.postMessage('system/errors/pages/'+
                                       module+'/'+
                                       pagename,str(tb))
                except Exception as e:
                    print (e)
                #Keep only the most recent 25 errors
                
                #If this is the first error(high level: transition from ok to not ok)
                #send a global system messsage that will go to the front page.
                if len(page.errors)==1:
                    messagebus.postMessage('/system/notifications/errors',
                                           "Page \""+pagename+"\" of module \""+module+
                                           "\" may need attention")
                raise (e)
