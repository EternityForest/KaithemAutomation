#Copyright Daniel Dunn 2017
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


import logging,textwrap,os,re
import cherrypy
from . import pages,widgets,pylogginghandler,directories,util
from cherrypy.lib.static import serve_file



syslogwidget = widgets.ScrollingWindow(2500)
syslogwidget.require('/users/logs.view')


try:
    try:
        import html
        esc= html.escape
    except:
        import cgi
        esc=cgi.escape
except:
    esc = lambda t:t


class WidgetHandler(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.widget = widgets.ScrollingWindow(2500)

    def handle(self,record):
        r = self.filter(record)
        if r:
            self.emit(record)
        return r
    def emit(self,r):
        if r:
            t = textwrap.fill(pylogginghandler.syslogger.format(r),120)
            t = esc(t)
            if r.levelname in ["ERROR", "CRITICAL"]:
                self.widget.write('<pre class="error">'+t+"</pre>")
            elif r.levelname in ["WARNING"]:
                self.widget.write('<pre class="error">'+ t+"</pre>")
            elif r.name =='system.notifications.important':
                self.widget.write('<pre class="highlight">'+ t+"</pre>")
            else:
                self.widget.write('<pre>'+ t+"</pre>")
            
dbg = WidgetHandler()

logging.getLogger().addHandler(dbg)
def f(r):
    t =  textwrap.fill(pylogginghandler.syslogger.format(r),120)
    if r.levelname in ["ERROR","CRITICAL"]:
        syslogwidget.write('<pre class="error">'+t+"</pre>")
    elif r.levelname in ["WARNING"]:
        syslogwidget.write('<pre class="error">'+ t+"</pre>")
    elif r.name =='system.notifications.important':
        syslogwidget.write('<pre class="highlight">'+ t+"</pre>")
    else:
        syslogwidget.write('<pre>'+ t+"</pre>")

pylogginghandler.syslogger.callback = f


def listlogdumps():
    where =os.path.join(directories.logdir,'dumps')
    logz = []
    r = re.compile(r'^.+_([0-9]*\.[0-9]*)\.log(\.gz|\.bz2)?$')
    for i in util.get_files(where):
        m = r.match(i)
        if not m == None:
            #Make time,fn,ext,size tuple
            #I have no clue how this line is suppoed to work.
            logz.append((float(m.groups('')[0]), i,m.groups('Uncompressed')[1],os.path.getsize(os.path.join(where,i))))
    return logz

class WebInterface(object):
    @cherrypy.expose
    def index(self,*args,**kwargs ):
        pages.require('/users/logs.view')
        return pages.get_template('syslog/index.html').render()
        
    @cherrypy.expose
    def servelog(self,filename):
        pages.require('/users/logs.view')
        #Make sure the user can't acess any file on the server like this

        #First security check, make sure there's no obvious special chars
        if ".." in filename:
            raise RuntimeError("Security Violation")
        if "/" in filename:
            raise RuntimeError("Security Violation")
        if "\\" in filename:
            raise RuntimeError("Security Violation")
        if "~" in filename:
            raise RuntimeError("Security Violation")
        if "$" in filename:
            raise RuntimeError("Security Violation")

        filename = os.path.join(directories.logdir,'dumps',filename)
        filename = os.path.normpath(filename)
        #Second security check, normalize the abs path and make sure it is what we think it is.
        if not filename.startswith(os.path.normpath(os.path.abspath(os.path.join(directories.logdir,'dumps')))):
            raise RuntimeError("Security Violation")
        return serve_file(filename, "application/x-download",os.path.split(filename)[1])
    @cherrypy.expose
    def archive(self):
        pages.require('/users/logs.view')
        return pages.get_template('syslog/archive.html').render(files = listlogdumps())
        
    @cherrypy.expose
    def flushlogs(self):
        pages.require('/admin/logging.edit')
        return pages.get_template('syslog/dump.html').render()

    @cherrypy.expose
    def dumpfiletarget(self):
        pages.require('/admin/logging.edit')
        pages.postOnly()
        pylogginghandler.syslogger.flush()
        return pages.get_template('syslog/index.html').render()


