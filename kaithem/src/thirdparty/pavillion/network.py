#Copyright Daniel Dunn 2018
#This file is part of 

#ShowMessage is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#ShowMessage is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with ShowMessage.  If not, see <http://www.gnu.org/licenses/>.


import weakref, types, collections, struct, time, socket,threading,random,os,logging
showmessage_logger = logging.getLogger("ShowMessage")





def universal_weakref(f):
    "Create a weakref to an object that works even if the object is a bound method"
    if isinstance(f,types.MethodType):
        if hasattr(weakref,"WeakMethod"):
            return weakref.WeakMethod(f)
        else:
            raise ValueError("Your version of python does not support weak refs to bound methods, upgrade to 3.4+")
    else:
        return weakref.ref(f)



import collections





ShowMessage = collections.namedtuple("ShowMessage",['counter', 'opcode','data'])
ShowMessage_message = collections.namedtuple("ShowMessage",['target', 'opcode','name','data','mid'])





def showMessage_message(target,name, data,counter,reliable=True):
    "Encodes a showmessage message(as opposed to a showmessage rpc call or the like)"
    return(ShowMessage(counter, 1 if reliable else 3, target.encode('utf-8')+b'\n'+name.encode('utf-8')+b'\n'+data))
    


def parseShowMessage(m,raw=False):
    if raw:
        if startswith(b'ShowMessage\x00'):
            m = m[len(b'ShowMessage\x00'):]
        else:
            raise RuntimeError("No header")


    mid = struct.unpack("<Q",m[:8])[0]

    ts = struct.unpack("<Q",m[8:16])[0]
    opcode =m[16]
    if opcode in [1,2]:       
        s = m[17:].split(b"\n",2)
        return ShowMessage(s[0].decode('utf-8'),opcode,s[1].decode('utf-8'),s[2],mid, ts/1000000.0)


def parseShowMessage(m):
    if m.startswith(b'ShowMessage\x00'):
        m = m[len(b'ShowMessage\x00'):]
        counter = struct.unpack("<Q",m[:8])[0]
        opcode =m[8]
        data=m[9:]
        return ShowMessage(counter, opcode, data)

def makeShowMessage(counter, opcode,data):
    m = (b'ShowMessage\x00'+struct.pack("<Q", counter )+struct.pack("<B", opcode)+data)
    return m




