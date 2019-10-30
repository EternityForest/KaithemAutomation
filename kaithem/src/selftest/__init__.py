#Copyright Daniel Dunn 2019
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

#This file runs a self test when python starts. Obviously we do
#Not want to clutter up the rraw

import threading,traceback,logging,os,time


def memtest():
    "Test a small segment of memory. Possibly enought to know if it's really messed up"
    for i in range(5):
        x=os.urandom(128)

        x1=x*1024*128
        x2=x*1024*128
        #Wait a bit, in case it's a time retention thing
        time.sleep(10)
        if not x1==x2:
            messagebus.postMessage("/system/notifications/errors","Memory may be corrupt")


def mathtest():
    import random
    old = -1
    for i in range(256):
        if not i>old:
            raise RuntimeError("Numbers appear to have been redefined or something")
        if not i-1==old:
            raise RuntimeError("Numbers appear to have been redefined or something")
   
        old = i

    for i in range(1,1024):
        x = 1/i


        r = max(random.random(),0.1)
        x2 = ((i*i)/i)*5000*r
        x2=x2/ 5000
        x2 = x2/r
        x2 = (2/x2)/2


        if not abs(x-x2)<0.001:
            raise RuntimeError("Floating point numbers seem to have an issue")
    
    if False:
        raise RuntimeError("If False should never run")


def netTest():
    "BUGGY, NOT READY, "
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s2.bind(("",18552))
    except:
        #Prob just port not free
        s.close()
        s2.close()
        return
   
    s.settimeout(3)
    x = 1
    while x:
        s.sendto(b'test',('127.0.0.1',18552))
        s.sendto(b'test',('127.0.0.1',18552))
        s.sendto(b'test',('127.0.0.1',18552))
        s.sendto(b'test',('127.0.0.1',18552))
        s.sendto(b'test',('127.0.0.1',18552))
        s.sendto(b'test',('127.0.0.1',18552))
        try:
            x,addr = s.recvfrom()
            if x==b'test':
                s.close()
                s2.close()
                return
        except:
            #Cach timeouts
            x=0
    s.close()
    s2.close()
    raise RuntimeError("UDP Loopback networking doesn't seem to work")

def runtest():
    from .. import messagebus
    try:
        from . import eventsystem,statemachinestest,messagebustest,tagpointstest,testpersist

        eventsystem.eventSystemTest()
        statemachinestest.stateMachinesTest()
        messagebustest.test()
        tagpointstest.testTags()
        testpersist.test()
        mathtest()
        #netTest()
        t= threading.Thread(target=memtest)
        t.daemon=True
        t.start()
        logging.info("Self test was sucessful")
    except:
        messagebus.postMessage("/system/notifications/errors",    "Self Test Error\n"+traceback.format_exc(chain=True))
    finally:
       pass

t = threading.Thread(daemon=True,name="KaithemBootSelfTest", target=runtest)
t.start()