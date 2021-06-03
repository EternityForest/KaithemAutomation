

import socket, threading,struct, logging,collections

msock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
msock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
msock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
msock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
msock.bind(("0.0.0.0", 40556))
group = socket.inet_aton("224.168.5.200")
mreq = struct.pack('4sL', group, socket.INADDR_ANY)
msock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
msock.settimeout(5)

sentCodes = collections.OrderedDict()
import random
c = int((random.random()*10000000))


def loop(cb,nick):
    while(1):
        try:        
            d,addr= msock.recvfrom(4096)

            d=d.decode()
            m = parseMessage(d)
            if m:
                if not cb(m):
                    break
        except socket.timeout:
            pass
            
        except:
            logging.exception("err parsing KouChat message")
        if not cb(None):
            break

lock = threading.Lock()
        
def send(nick,message):
    m=str(c)+"!MSG#"+nick.replace("#",'').replace(":",'')+":[-15987646 ]"+message
    m=m.encode()
    with lock:
        msock.sendto(m,("224.168.5.200",40556))

def sendIdle(nick):
    m=str(c)+"!IDLE#"+nick.replace("#",'').replace(":",'')
    m=m.encode()
    with lock:
        msock.sendto(m,("224.168.5.200",40556))

def listen(cb,nick):
    t =threading.Thread(target=loop,args=(cb,nick))
    t.start()

def parseMessage(m=''):

    msgCode, m = m.split("!",1)
    msgCode = int(msgCode)

    type, m = m.split("#",1)
    if not type=="MSG":
        return 0

    if msgCode==c:
        return


    nick, m = m.split(":",1)

    rgb1, m = m.split("[",1)
    rgb,  message = m.split("]",1)
    return {'nick':nick,'msg':message, 'type':'msg'}


def cb(a):
    print(a)
    if a:
        send("Autojerk","reply")
    return True
    
listen(cb,"Autojerk")

import time
while(1):
    time.sleep(1)
