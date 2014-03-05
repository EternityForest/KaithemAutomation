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
from . import pages, util,messagebus,config,auth

class Settings():
    @cherrypy.expose 
    def index(self):
        return pages.get_template("settings/index.html").render()
    
    @cherrypy.expose 
    def account(self):
        pages.require("/users/accountsettings.edit")
        return pages.get_template("settings/user_settings.html").render()
    
    @cherrypy.expose 
    def changeprefs(self,**kwargs):
        pages.require("/users/accountsettings.edit")
        for i in kwargs:
            if i.startswith("pref_"):
                auth.setUserSetting(pages.getAcessingUser(),i[5:],kwargs[i])
        
        raise cherrypy.HTTPRedirect("/settings/account")

    @cherrypy.expose 
    def changepwd(self,**kwargs):
        pages.require("/users/accountsettings.edit")
        t = cherrypy.request.cookie['auth'].value
        u = auth.whoHasToken(t)
        if not auth.userLogin(u,kwargs['old']) == "failure":
            if kwargs['new']==kwargs['new2']:
                auth.changePassword(u,kwargs['new'])
            else:
                raise cherrypy.HTTPRedirect("/errors/mismatch")
        else:
            raise cherrypy.HTTPRedirect("/errors/loginerror")
        
        raise cherrypy.HTTPRedirect("/")

                
                
    
    @cherrypy.expose 
    def system(self):
        pages.require("/admin/settings.view")
        return pages.get_template("settings/global_settings.html").render()
        
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
                <META HTTP-EQUIV="refresh" CONTENT="30;URL=/">
                </HEAD>
                <BODY>
                <p>Reloading. If you get an error, try again.</p>
                </BODY>
                </HTML> """
    
    @cherrypy.expose    
    def clearerrors(self):
        pages.require("/admin/settings.edit")
        return pages.get_template("settings/clearerrors.html").render()
    
    @cherrypy.expose    
    def clearerrorstarget(self):
        pages.require("/admin/settings.edit")
        util.clearErrors()
        messagebus.postMessage("/system/notifications","All errors were cleared by" + pages.getAcessingUser())
        raise cherrypy.HTTPRedirect('/')