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
import cherrypy,base64,os
from . import pages, util,messagebus,config,auth,registry,mail

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
        lists = []
        for i in kwargs:
            if i.startswith("pref_"):
                auth.setUserSetting(pages.getAcessingUser(),i[5:],kwargs[i])
            if i.startswith("list_"):
                if kwargs[i] == "subscribe":
                    lists.append(i[5:])
        auth.setUserSetting(pages.getAcessingUser(),'mailinglists',lists)
        
        auth.setUserSetting(pages.getAcessingUser(),'useace','useace' in kwargs)

        raise cherrypy.HTTPRedirect("/settings/account")
    
    @cherrypy.expose 
    def changeinfo(self,**kwargs):
        pages.require("/users/accountsettings.edit")
        auth.setUserSetting(pages.getAcessingUser(),'email',kwargs['email'])
        
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
    def testmail(self,*a,**k):
        pages.require("/users/accountsettings.edit")
        mail.raw_send("testing",k['to'],'test mail')
        raise cherrypy.HTTPRedirect("/")
    
    @cherrypy.expose
    def listmail(self,*a,**k):
        pages.require("/admin/settings.edit")
        mail.rawlistsend(k['subj'],k['msg'],k['list'])
        raise cherrypy.HTTPRedirect("/")
        
        
    @cherrypy.expose
    def savemail(self,*a,**k):
        pages.require("/admin/settings.edit")
        registry.set("system/mail/server",  k['smtpserver'])
        registry.set("system/mail/port",  k['smtpport'])
        registry.set("system/mail/address" ,k['smtpaddress'])
        
        if not k['smtpassword1'] == '':
            if k['smtpassword1'] == k['smtpassword2'] :
                registry.set("system/mail/password" ,k['smtpassword1'])
            else:
                raise exception("Passwords must match")
        mail = registry.get("system/mail/lists",{})
        
        for i in k:
            if i.startswith('mlist_name'):
                uuid = i[10:]
                newname = k[i]
                mail[uuid]['name'] = newname
                    
            if i.startswith("mlist_desc"):
                list = i[10:]
                mail[list]['description'] = k[i]
        for i in k:
            if i.startswith("del_"):
                list = i[4:]
                del mail[list]
                
        if 'newlist' in k:
            mail[base64.b64encode(os.urandom(16)).decode()[:-2]] = {'name':'Untitled', 'description': "Insert Description"}
        
        registry.set("system/mail/lists",mail)
        auth.getPermissionsFromMail()
        raise cherrypy.HTTPRedirect("/settings/system")

                
    
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