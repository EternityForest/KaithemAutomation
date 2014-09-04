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
import cherrypy,base64,os,time,subprocess,time,shutil
from cherrypy.lib.static import serve_file
from . import pages, util,messagebus,config,auth,registry,mail,kaithemobj

class Settings():
    @cherrypy.expose 
    def index(self):
        return pages.get_template("settings/index.html").render()
    
    
    @cherrypy.expose 
    def stopsounds(self,*args,**kwargs):
        pages.require("/admin/settings.edit")
        kaithemobj.kaithem.sound.stopAll()
        raise cherrypy.HTTPRedirect("/settings")
    
    @cherrypy.expose 
    def files(self,*args,**kwargs):
        pages.require("/admin/settings.edit")
        dir=os.path.join('/',*args)
        
        if 'del' in kwargs:
            node = os.path.join(dir,kwargs['del'])
            if os.path.isfile(node):
                os.remove(node)
            else:
                shutil.rmtree(node)
            raise cherrypy.HTTPRedirect(cherrypy.request.path_info.split('?')[0])
                
        if 'file' in kwargs:
            if os.path.exists(os.path.join(dir,kwargs['file'].filename)):
                raise RuntimeError("Node with that name already exists")
            with open(os.path.join(dir,kwargs['file'].filename),'wb') as f:
                while True:
                    data = kwargs['file'].file.read(8192)
                    if not data:
                        break
                    f.write(data)
                    
        if os.path.isdir(dir):
            return pages.get_template("settings/files.html").render(dir=dir)
        else:
            return serve_file(dir)
        
    
    @cherrypy.expose 
    def cnfdel(self,*args,**kwargs):
        pages.require("/admin/settings.edit")
        path=os.path.join('/',*args)
        return pages.get_template("settings/cnfdel.html").render(path=path)
        
    @cherrypy.expose 
    def console(self,**kwargs):
        pages.require("/admin/settings.edit")
        if 'script' in kwargs:
            x = ''
            p = subprocess.Popen("bash -i",universal_newlines=True, shell=True,stdout=subprocess.PIPE,stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            t =  p.communicate(bytes(kwargs['script'],'utf8'))
            x+= t[0] + t[1]
            try:
                time.sleep(0.1)
                t = p.communicate(b'')
                x+= t[0]+t[1]
                p.kill()
            except:
                pass
            return pages.get_template("settings/console.html").render(output=x)
        else:
            return pages.get_template("settings/console.html").render(output="Kaithem BASH Shell")

    
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
        pages.require("/admin/settings.edit")
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
    def processes(self):
        pages.require("/admin/settings.view")
        return pages.get_template("settings/processes.html").render()
    
    @cherrypy.expose    
    def clearerrorstarget(self):
        pages.require("/admin/settings.edit")
        util.clearErrors()
        messagebus.postMessage("/system/notifications","All errors were cleared by" + pages.getAcessingUser())
        raise cherrypy.HTTPRedirect('/')
    
    class profiler():
        @cherrypy.expose    
        def index():
            pages.require("/admin/settings.edit")
            return pages.get_template("settings/profiler/index.html").render(sort='')
        @cherrypy.expose
        def bytotal():
            pages.require("/admin/settings.edit")
            return pages.get_template("settings/profiler/index.html").render(sort='total')  
        @cherrypy.expose    
        def start():
            pages.require("/admin/settings.edit")
            import yappi
            if not yappi.is_running():
                yappi.start()
            time.sleep(0.5)
            raise cherrypy.HTTPRedirect("/settings/profiler")
       
        @cherrypy.expose    
        def stop():
            pages.require("/admin/settings.edit")
            import yappi
            if yappi.is_running():
                yappi.stop()
            raise cherrypy.HTTPRedirect("/settings/profiler")
        
        @cherrypy.expose    
        def clear():
            pages.require("/admin/settings.edit")
            import yappi
            yappi.clear_stats()
            raise cherrypy.HTTPRedirect("/settings/profiler/")


        
