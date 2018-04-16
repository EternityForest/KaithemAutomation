#Copyright Daniel Dunn 2018
#This file is part of 

#Pavillion is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Pavillion is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Pavillion.  If not, see <http://www.gnu.org/licenses/>.

import weakref, types, collections, struct, time, socket,threading,random,os,logging,traceback

from .common import ciphers,DEFAULT_MCAST_ADDR,DEFAULT_PORT,nonce_from_number,pavillion_logger



SESSION_TIMEOUT = 300


class Register():
    def __init__(self, name,type,flags="rwc", value=b'', description=None,restrict=None):
        self.name = name
        self.description = description
        self.restrict = None
    
    def read(self,client):
        return self.value
    
    def write(self,client,value):
        self.value = value
        
    def call(self,client,value):
        self.value = value
        return self.value


class MessageTarget():
    def __init__(self,target,callback):
        self.callback = callback
        self.target = target

class _ServerClient():
    "Server uses this class to track clients"
    def __init__(self,server,address,plaintext=False):
        self.nonce = os.urandom(32)
        self.address = address
        self.ckey = None
        self.skey = None
        self.server = server
        self.client_counter =0
        self.clientID = None

        #ServerChallenge in the docs
        self.challenge = os.urandom(16)
        self.plaintext = plaintext

        self.counter = 0

        #we don't yet know the cipher
        self.decrypt=None
        self.encrypt=None

        self.ignore = 0

        self.created = time.time()
        #The last time we actually got a proper message from them
        self.lastSeen =0


    def sendSetup(self, counter, opcode, data):
        "Send an unsecured packet"
        m = struct.pack("<Q",counter)+struct.pack("<B",opcode)+data
        self.server.sock.sendto(b"PavillionS0"+m,self.address)

    def sendSecure(self, counter, opcode, data):
        "Send a secured packet"
        n = b'\x00'*(24-8)+struct.pack("<Q",counter)
        m = struct.pack("<B",opcode)+data
        m=self.encrypt(m,self.skey,n)
        self.server.sock.sendto(b"PavillionS0"+struct.pack("<Q",counter)+m,self.address)

    def send(self, counter, opcode, data):
        #No risk of accidentally responding to a secure message with a plaintext one.
        #Servers don't originate messages and we cant recieve messages without ckey
        if self.ckey:
            self.sendSecure(counter,opcode,data)
        else:
            self.sendPlaintext(counter,opcode,data)

    def onRawMessage(self,addr, msg):
        "Handle a raw UDP packet from the client"
        s = b"PavillionS0"
        unsecure = b"Pavillion0"

        #Header checks
        if not msg.startswith(s):
            #A regular message. Check if we're accepting unsecured messages, and if so pass it to
            #Application. Not much reason to use these though.
            if self.plaintext and s.startswith(unsecure):
                msg=msg[len(unsecure):]
                counter = struct.unpack("<Q",msg[:8])[0]
                opcode=msg[8]
                msg = msg[9:]
                if opcode==10:
                    self.clientID = msg
                    self.client_counter = 0
                    self.send(self.counter, 11, b'')
                else:
                    self.server.onMessage(addr, counter,opcode,msg,self.clientID)
                return
            else:
                 raise ValueError("No valid header")


        msg=msg[len(s):]
        counter = struct.unpack("<Q",msg[:8])[0]


        if not self.ignore>time.time() and counter:
            ciphertext = msg[8:]
            if self.ckey:
                plaintext = self.decrypt(ciphertext,  self.ckey, nonce_from_number(counter))
                self.lastSeen = time.time()
                #Duplicate protection
                if self.client_counter>=counter:
                    return
                self.client_counter = counter
                self.server.onMessage(addr,counter,plaintext[0],plaintext[1:],self.clientID)

            #We don't know how to process this message. So we send
            #an unrecognized client
            else:
                self.sendSetup(0, 5, b'')
                self.ignore = time.time()+5

        else:
            opcode=msg[8]
            msg = msg[9:]
            #Nonce request, send a nonce
            if opcode==1:
                cipher = msg[0]
                clientID = msg[1:17]
                challenge = msg[17:]


                if not ciphers[cipher].asym_setup:
                    if not clientID in self.server.keys:

                        if self.ignore<time.time():
                            #Send the invalid message
                            self.sendSetup(0, 6,challenge)

                        self.ignore = time.time()+10*60
                        return

                    clientkey = self.server.keys[clientID]
                    m = self.nonce+challenge+ciphers[cipher].keyedhash(self.nonce+challenge,clientkey)
                    self.sendSetup(0, 2,m)
                
                else:
                    if not clientID in self.server.pubkeys:
                        if self.ignore<time.time():
                            #Send the invalid message
                            self.sendSetup(0, 6,challenge)

                        self.ignore = time.time()+10*60
                        return

                    clientkey = self.server.pubkeys[clientID]
                    m = self.nonce+challenge
                    n= os.urandom(24)
                    m = n+ciphers[cipher].pubkey_encrypt(m,n,clientkey,self.server.ecc_keypair[1])
                    self.sendSetup(0, 11,m)

            #In the ignore state, we will ignore messages aside from Nonce requests.
            if self.ignore >time.time():
                return


            if opcode==3:
                ciphernumber,clientid,clientnonce,servernonce,clientcounter,h = struct.unpack("<B16s32s32sQ32s",msg)
                if not servernonce == self.nonce:
                    logging.warning("Non matching nonce in client info packet"+str(servernonce)+'||'+str(self.nonce))
                    return

                cipher = ciphers[ciphernumber]
                #Validate challenge response
                psk = self.server.keys[clientid]
                if cipher.keyedhash(msg[:-32],psk)==h:
                    self.clientID = clientid

                    keyedhash = cipher.keyedhash
                    self.encrypt = cipher.encrypt
                    self.decrypt = cipher.decrypt                  
                    #Client to server session key
                    self.ckey= keyedhash(clientnonce,psk)
                    self.lastseen = time.time()
                    #Server to client session key
                    self.skey= keyedhash(servernonce+clientnonce,psk)

                    self.client_counter = clientcounter

                    #Make sure that nonce isn't reused
                    self.nonce = os.urandom(32)
                else:
                    raise RuntimeError(str((s)))
            
            ## ECC Client info
            if opcode == 12:
                clientID = msg[0:16]
                cipher = msg[16]

                decrypt = ciphers[cipher].pubkey_decrypt
                msg= decrypt(msg[17+24:],msg[17:17+24],self.server.pubkeys[clientID],self.server.ecc_keypair[1])

                nonce, ckey,skey, counter= struct.unpack("<32s32s32sQ",msg)
                if nonce==self.nonce:
                   #Make sure that nonce isn't reused
                    self.nonce = os.urandom(32)
                    self.clientID = clientID
                    self.ckey, self.skey, self.client_counter = ckey,skey,counter
                    self.decrypt = ciphers[cipher].decrypt
                    self.encrypt = ciphers[cipher].encrypt
                    logging.info("Setup connection with client via ECC")

class _Server():
    def __init__(self,port=DEFAULT_PORT,keys=None,pubkeys=None,address='',multicast=None, ecc_keypair=None, handle=None):
        """The private server object that the user should not see except via the interface.
           This is because we don't want to
        
           
           keys maps client IDs to either 32 byte preshared keys or 32 byte ECC keys. A client can only have one type of key configured.

           multicast is a multicast IP address that the server will listen on if specified. Adress is the local IP to bind to.

           ecc_keypair is a tuple of raw binary (public,private) keys. If not supplied, the server is symmetric-only. 
           
        """


        #Not implemented yet
        self.broker=False


        self.keys = keys or {}
        self.pubkeys= pubkeys or {}

        self.port = port

        self.address = (address, port)

        def cl(*args):
            self.close()
        self.clfun = cl
        #If we have a handle, make it so that if the handle gets collected the server thread stops
        if handle:
            self.handle = weakref.ref(handle,cl)
    
        # Create the socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) 
        # Bind to the server address
        self.sock.bind(self.address)
        self.sock.settimeout(1)

        self.mcastgroup = multicast
        #Subscribe to any requested mcast group
        if multicast:
            group = socket.inet_aton(multicast)
            mreq = struct.pack('4sL', group, socket.INADDR_ANY)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        #A list of all the registers and functions indexed by number
        self.registers = {}


        self.ecc_keypair = ecc_keypair
        self.running = True
        t = threading.Thread(target=self.loop)
        t.start()


        self.knownclients = collections.OrderedDict()

        self.counter = random.randint(2**63,2**63+1000000000)

        self.messageTargets = {}

        self.targetslock = threading.Lock()
        self.lock = threading.Lock()

        #Max number of clients we keep track of, icluding ignored ones
        self.maxclients = 512

    def onRPCCall(self, f, data,clientID):
        pass

    def close(self):
        pavillion_logger.info("Closing server "+str(self))
        self.running=False

    def messageTarget(self,target,callback):
        m = MessageTarget(target,callback)
        with self.targetslock:
            self.cleanupTargets()
            if not target in self.messageTargets:
                self.messageTargets[target]=[]
            self.messageTargets[target].append(weakref.ref(m))
        return m


    def cleanupTargets(self):
        for i in self.messageTargets:
                j = self.messageTargets[i]
                for k in j:
                    if not k():
                        j.remove(k)
                if not self.messageTargets[i]:
                    del self.messageTargets[i]



    def onMessage(self,addr, counter, opcode, data,clientID=None):
        "Handle a message after decoding"
        #reliable message
        if  opcode==1:
            d = data.split(b'\n',2)
            #If we have a listener for that message target
            if d[0].decode('utf-8') in self.messageTargets:

                #No counter race conditions allowed
                with self.lock:
                    #Do an acknowledgement
                    self.counter += 1
                    self.knownclients[addr].send(self.counter,2,struct.pack("<Q",counter))


                #Repeat messages to all the other clients if broker mode is enabled.
                if self.broker:
                    try:
                        for i in self.knownclients:
                            if not i == addr:
                                if d[0] in self.knownclients[i].subscriptions:
                                    self.counter+=1
                                    self.knownclients[addr].send(self.counter,i,data)
                    except:
                        pass

                s = self.messageTargets[d[0].decode('utf-8')]
                with self.targetslock:
                    for i in s:
                        i = i()
                        if not i:
                            continue
                        i.callback(d[1].decode('utf-8') ,d[2],clientID)

        #Unreliable message, don't ack
        elif  opcode==3:
            d = data.split(b'\n',2)
            #If we have a listener for that message target
            if d[0].decode('utf-8') in self.messageTargets:
                s = self.messageTargets[d[0].decode('utf-8')]
                with self.targetslock:
                    for i in s:
                        i = i()
                        if not i:
                            continue
                        i.callback(d[1].decode('utf-8') ,d[2],clientID)
        
        #RPC Call
        elif  opcode==4:
            try:
                r = struct.unpack("<H",data[0:2])[0]
                f = self.registers[r]
                if callable(f):
                    d = f(clientID, data[2:])
                else:
                    d = f.call(clientID, data[2:])
                self.counter +=1
                self.knownclients[addr].send(self.counter,5,struct.pack("<Q",counter)+b'\x00\x00'+bytes(d))
            except:
                #If an exception happens, then send the traceback to the client.
                print(traceback.format_exc())
                self.counter += 1
                self.knownclients[addr].send(self.counter,5,struct.pack("<Q",counter)+b'\x01\x01Exception on remote server\r\n'+traceback.format_exc(6).encode('utf-8'))
                


    def loop(self):
        while(self.running):
            try:
                m,addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
         
            try:
                if addr==self.address:
                    continue
                if not addr in self.knownclients:
                    #If we're out of space for new clients, go through and find one we haven't seen in a while.
                    if len(self.knownclients)>self.maxclients:
                        torm=False
                        for i in sorted(list(self.knownclients.items()),key=lambda x: x[1].created):
                            if i[1].lastSeen < time.time()-SESSION_TIMEOUT:
                                torm=i[0]
                        if torm:
                            del self.knownclients[torm]
                        else:
                            #Don't drop old sessions for new ones
                            continue

                    self.knownclients[addr] = _ServerClient(self, addr)
                self.knownclients[addr].onRawMessage(addr,m)
            except:
                pavillion_logger.exception("Exception in server loop")

        #Close sock at end
        self.sock.close()



class Server():
    """The public interface object that a user might interact with for a Server object"""
    def __init__(self,port=DEFAULT_PORT, keys=None,pubkeys=None, address='',multicast=None,ecc_keypair=None):
        keys = keys or {}
        #Yes, we want the objects to share the mutable dict, 
        self.keys = keys
        self.pubkeys = pubkeys
        self.server = _Server(port=port,keys=keys,pubkeys=pubkeys,address=address,multicast=multicast,ecc_keypair=ecc_keypair,handle=self)
        self.registers = self.server.registers
    def messageTarget(self,target,function):
        "Subscibe function to target, and return a messageTarget object that you must retain in order to keep the subscription alive"
        return self.server.messageTarget(target,function)
    
    def close(self):
        self.server.close()