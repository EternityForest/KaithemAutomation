import logging
import cherrypy
from . import pages,widgets,pylogginghandler



syslogwidget = widgets.ScrollingWindow(2500)
syslogwidget .require('/users/logs.view')

class WidgetHandler(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.widget =  widgets.ScrollingWindow(2500)

    def handle(self,record):
        r = self.filter(record)
        if r:
            self.emit(record)
        return r
    def emit(self,r):
        if r.levelname in ["ERROR","CRITICAL"]:
            self.widget.write('<pre class="error">'+ pylogginghandler.syslogger.format(r)+"</pre>")
        elif r.levelname in ["WARNING"]:
            self.widget.write('<pre class="error">'+ pylogginghandler.syslogger.format(r)+"</pre>")
        elif r.name =='system.notifications.important':
            self.widget.write('<pre class="highlight">'+ pylogginghandler.syslogger.format(r)+"</pre>")
        else:
            self.widget.write(pylogginghandler.syslogger.format(r))
dbg = WidgetHandler()

logging.getLogger().addHandler(dbg)
def f(r):
    if r.levelname in ["ERROR","CRITICAL"]:
        syslogwidget.write('<pre class="error">'+ pylogginghandler.syslogger.format(r)+"</pre>")
    elif r.levelname in ["WARNING"]:
        syslogwidget.write('<pre class="error">'+ pylogginghandler.syslogger.format(r)+"</pre>")
    elif r.name =='system.notifications.important':
        syslogwidget.write('<pre style="width:90%"  sclass="highlight">'+ pylogginghandler.syslogger.format(r)+"</pre>")
    else:
        syslogwidget.write(pylogginghandler.syslogger.format(r))

pylogginghandler.syslogger.callback = f

class WebInterface(object):
    @cherrypy.expose
    def index(self,*args,**kwargs ):
        pages.require('/users/logs.view')
        return pages.get_template('syslog/index.html').render()
