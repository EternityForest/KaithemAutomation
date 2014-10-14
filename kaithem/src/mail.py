from . import registry,workers,auth,pages,messagebus
import smtplib,email

from collections import deque

q = deque()
 
# Import the email modules we'll need
from email.mime.text import MIMEText



def send(*x):
    def f():
        raw_send(*x)
    workers.do(f)
    
def rawlistsend(subject,message,list):
    l = []
    for i in auth.Users:
        x = auth.getUserSetting(i,'mailinglists')
        if list in x:
            if auth.canUserDoThis(i,"/users/mail/lists/"+list+"/subscribe"):
                l.append(auth.getUserSetting(i,'email'))
    raw_send(message,l,subject,registry.get('system/mail/lists')[list]['name'])
    
def raw_send(msg,to,subject,recipientName=None):
    smtp_host = registry.get("system/mail/server")
    smtp_port = registry.get("system/mail/port")
    fromaddr = registry.get("system/mail/address")
    server = smtplib.SMTP()
    server.connect(smtp_host,smtp_port)
    server.ehlo()
    server.starttls()
    server.login(fromaddr,registry.get("system/mail/password"))
    if isinstance(to,str):
        tolist = [to]
    else:
        tolist = to
    sub = subject
   
    msg = MIMEText(msg)
    # me == the sender's email address
    # you == the recipient's email address
    msg['Subject'] = sub
    msg['From'] = fromaddr
    msg['To'] = ', '.join(msg)
    if recipientName:
        msg['to'] = recipientName
    server.sendmail(fromaddr,tolist,msg.as_string())
    
def check_credentials():
    if not registry.get("system/mail/server",False):
        return    
    try:
        smtp_host = registry.get("system/mail/server")
        smtp_port = registry.get("system/mail/port")
        fromaddr = registry.get("system/mail/address")
        server = smtplib.SMTP()
        server.connect(smtp_host,smtp_port)
        server.ehlo()
        server.starttls()
        server.login(fromaddr,registry.get("system/mail/password"))
    except smtplib.SMTPAuthenticationError as e:
        messagebus.postMessage("/system/errors/mail/login",repr(e))
        messagebus.postMessage("/system/notifications/errors","Bad username or password for system email account\n"+repr(e))
    finally:
        try:
            server.quit()
        except:
            pass
        
   

        
        
