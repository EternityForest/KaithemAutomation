#Copyright Daniel Black 2013
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
import cherrypy
from . import pages, util,messagebus,config

class Settings():
    @cherrypy.expose 
    def index(self):
        pages.require("/admin/settings.view")
        return pages.get_template("settings/index.html").render()
        
    @cherrypy.expose    
    def save(self):
        pages.require("/admin/settings.edit")
        return pages.get_template("settings/save.html").render()
        
    @cherrypy.expose    
    def savetarget(self):
        pages.require("/admin/settings.edit")
        util.SaveAllState()
        messagebus.postMessage("/system/notifications","Global server state was saved to disk")
        raise cherrypy.HTTPRedirect('/')
    
    @cherrypy.expose    
    def restart(self):
        pages.require("/admin/settings.edit")
        return pages.get_template("settings/restart.html").render()
        
    @cherrypy.expose    
    def restarttarget(self):
        pages.require("/admin/settings.edit")
        #This log won't be seen by anyone unless they set up autosaving before resets
        messagebus.postMessage("/system/notifications", "User "+ pages.getAcessingUser() + ' reset the system.')
        cherrypy.engine.restart()#(!)
        #It might come online fast enough for this to work, otherwise they see an error.
        return  """
                <HTML>
                <HEAD>
                …
                <META HTTP-EQUIV="refresh" CONTENT="30;URL=/">
                </HEAD>
                <BODY>
                <p>Reloading. If you get an error, try again.</p>
                </BODY>
                </HTML> """
                