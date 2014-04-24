from . import registry,workers
import smtplib,email

from collections import deque

q = deque()
 
# Import the email modules we'll need
from email.mime.text import MIMEText



def send(*x):
    def f():
        raw_send(*x)
    workers.do(f)
    

def raw_send(msg,to,subject):
    smtp_host = registry.get("system/mail/server")
    smtp_port = registry.get("system/mail/port")
    fromaddr = registry.get("system/mail/address")
    server = smtplib.SMTP()
    server.connect(smtp_host,smtp_port)
    server.ehlo()
    server.starttls()
    server.login(fromaddr,registry.get("system/mail/password"))
    tolist = [to]
    sub = subject
   
    msg = MIMEText(msg)
    # me == the sender's email address
    # you == the recipient's email address
    msg['Subject'] = sub
    msg['From'] = fromaddr
    msg['To'] = ', '.join(msg)
    server.sendmail(fromaddr,tolist,msg.as_string())
