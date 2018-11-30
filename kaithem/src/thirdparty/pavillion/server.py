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

import weakref, types, collections, struct, time, socket,threading,random,os,logging,traceback,select

from .common import ciphers,DEFAULT_MCAST_ADDR,DEFAULT_PORT,nonce_from_number,pavillion_logger,preprocessKey
from . import common

import pavillion

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

class _ServerClient():
    "Server uses this class to track clients"
    def __init__(self,server,address,plaintext=False):
        self.nonce = os.urandom(32)
        self.address = address
        self.ckey = None
        self.skey = None
        self.server = server
        self.client_counter =0
        #Used to keep track of an unused number we can still accept even
        #If it's lower than the expected counter value
        self.unusedOutOfOrderCounterValue =None
        self.clientID = None
        self.guest_key = None
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

        #What topics has this client subscribed to.
        self.subscriptions = {}

        #Sessions IDs are initialized to random values.
        #It's used so that servers can detect if they are still connected
        self.sessionID = os.urandom(16)


    def sendSetup(self, counter, opcode, data):
        "Send an unsecured packet"
        m = struct.pack("<Q",counter)+struct.pack("<B",opcode)+data
        self.server.sendsock.sendto(b"PavillionS0"+m,self.address)

    def sendSecure(self, counter, opcode, data):
        "Send a secured packet"
        n = b'\x00'*(24-8)+struct.pack("<Q",counter)
        m = struct.pack("<B",opcode)+data
        m=self.encrypt(m,self.skey,n)
        self.server.sendsock.sendto(b"PavillionS0"+struct.pack("<Q",counter)+m,self.address)

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
                try:
                    plaintext = self.decrypt(ciphertext,  self.ckey, nonce_from_number(counter))
                except:
                    self.sendSetup(0, 4, b'')
                    #If we have recieved a valid message recently,
                    #don't ignore just because there's random line garbage,
                    if self.lastSeen<(time.time()-100):
                        self.ignore = time.time()+5
                    return
                
                self.lastSeen = time.time()
                #Duplicate protection, make sure the counter increments.
                #Do some minor out-of-order counter value handling.
                #If we detect that the counter has incremented by more than exactly 1,
                #The unused value may be accepted.
                
                #TODO: Support keeping track of multiple unused values. One
                #should be much better than none for now.
                if self.client_counter>=counter:
                    with self.server.lock:
                        if counter == self.unusedOutOfOrderCounterValue:
                            self.unusedOutOfOrderCounterValue = None
                        else:
                            return
                
                if counter > self.client_counter+1:
                    with self.server.lock:
                        self.unusedOutOfOrderCounterValue = self.client_counter+1
                    
                self.client_counter = counter
                self.server.onMessage(addr,counter,plaintext[0],plaintext[1:],self.clientID)

            #We don't know how to process this message. So we send
            #an unrecognized client
            else:
                self.sendSetup(0, 4, b'')
                self.ignore = time.time()+5
                return

        else:
            opcode=msg[8]
            msg = msg[9:]
            #Nonce request, send a nonce
            if opcode==1:
                cipher, clientID, challenge, sessionID, client_pubkey= struct.unpack("<B16s16s16s32s", msg)

                if self.sessionID == sessionID:
                    #We're already connected,
                    return


                if self.server.allow_guest and not clientID in self.server.pubkeys:
                    #Don't let someone else mess up the connection
                    if self.guest_key and not self.guest_key == client_pubkey:
                        return

                    self.guest_key = client_pubkey
                    self.guest_id = clientID


                if not ciphers[cipher].asym_setup:
                    if not clientID in self.server.keys:

                        if self.ignore<time.time():
                            #Send the invalid message
                            self.sendSetup(0, 6,challenge)

                        self.ignore = time.time()+10*60
                        return

                    clientkey = preprocessKey(self.server.keys[clientID])
                    m = self.nonce+challenge+ciphers[cipher].keyedhash(self.nonce+challenge,clientkey)
                    self.sendSetup(0, 2,m)
                
                else:
                    if (not clientID in self.server.pubkeys) and not self.guest_key:
                        if self.ignore<time.time():
                            #Send the invalid message
                            self.sendSetup(0, 6,challenge)

                        self.ignore = time.time()+10*60
                        return

                    clientkey = self.guest_key or self.server.pubkeys[clientID]
                    m = self.nonce+challenge
                    n= os.urandom(24)
                    m = n+ciphers[cipher].pubkey_encrypt(m,n,clientkey,self.server.ecc_keypair[1])
                    self.sendSetup(0, 11,m)



            if opcode==3:
                ciphernumber,clientid,clientnonce,servernonce,clientcounter,h = struct.unpack("<B16s32s32sQ32s",msg)
                if not servernonce == self.nonce:
                    return

                cipher = ciphers[ciphernumber]
                #Validate challenge response
                psk = preprocessKey(self.server.keys[clientid])
                if cipher.keyedhash(msg[:-32],psk)==h:
                    self.clientID = clientid

                    keyedhash = cipher.keyedhash
                    self.encrypt = cipher.encrypt
                    self.decrypt = cipher.decrypt                  
                    #Client to server session key
                    self.ckey= keyedhash(clientnonce,psk)

                    #Rehash to get the sessoin ID
                    self.sessionID = keyedhash(self.ckey, psk)[:16]

                    self.lastseen = time.time()
                    #Server to client session key
                    self.skey= keyedhash(clientnonce+servernonce,psk)

                    self.client_counter = clientcounter

                    #Make sure that nonce isn't reused
                    self.nonce = os.urandom(32)
                    self.sendSetup(0, 7, self.sessionID)
                    self.ignore=0
                else:
                    raise RuntimeError(str((s)))
            
            ## ECC Client info
            if opcode == 12:
                clientID = msg[0:16]
                cipher = msg[16]
                keyedhash = ciphers[cipher].keyedhash

                decrypt = ciphers[cipher].pubkey_decrypt

                cpubkey = self.guest_key or self.server.pubkeys[clientID]

                msg= decrypt(msg[17+24:],msg[17:17+24],cpubkey,self.server.ecc_keypair[1])

                nonce, ckey,skey, counter= struct.unpack("<32s32s32sQ",msg)
                if nonce==self.nonce:
                   #Make sure that nonce isn't reused
                    self.clientID = clientID
                    self.ckey, self.skey, self.client_counter = ckey,skey,counter
                    self.sessionID = keyedhash(self.ckey, nonce)[:16]
                    self.nonce = os.urandom(32)

                    self.decrypt = ciphers[cipher].decrypt
                    self.encrypt = ciphers[cipher].encrypt

                    #If we used a guest key, report the hash of said guest key
                    if self.guest_key:
                        self.clientID = common.libnacl.generic_hash(self.guest_key)
                    self.ignore = 0
                    self.sendSetup(0, 7, self.sessionID)
                    logging.info("Setup connection with client via ECC")

class _Server():
    def __init__(self,port=DEFAULT_PORT,keys=None,pubkeys=None,address='',multicast=None, 
    ecc_keypair=None, handle=None, allow_guest=False,daemon=False,execute=None):
        """The private server object that the user should not see except via the interface.
           This is because we don't want to
        
           
           keys maps client IDs to either 32 byte preshared keys or 32 byte ECC keys. A client can only have one type of key configured.

           multicast is a multicast IP address that the server will listen on if specified. Adress is the local IP to bind to.

           ecc_keypair is a tuple of raw binary (public,private) keys. If not supplied, the server is symmetric-only.

           daemon specifies the daemon status of the server's listening thread. Defaults to false,
           but you might want this to be True if you can accept the server not getting to finish executing a function,
           or if the handle's execute function already takes care of that.
           
        """


        #Not implemented yet
        self.broker=False
        self.ignore = {}


        self.keys = keys or {}
        self.pubkeys= pubkeys or {}

        self.port = port
        self.address = (address, port)


        self.guest_key = None
        self.allow_guest = allow_guest


        def cl(*args):
            self.close()
        self.clfun = cl
        #If we have a handle, make it so that if the handle gets collected the server thread stops
        if handle:
            self.handle = weakref.ref(handle,cl)
    
     
        self.waitingForAck = weakref.WeakValueDictionary()

        # Create the socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)  
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) 
        # Bind to the server address
        self.sock.bind(self.address)
        self.sock.settimeout(1)

        self.sendsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sendsock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) 
        self.sendsock.bind((self.address[0],0))
        self.sendsock.settimeout(1)

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
     

        self.knownclients = collections.OrderedDict()

        self.counter = random.randint(2**63,2**63+1000000000)

        self.messageTargets = {}

        self.targetslock = threading.Lock()
        self.lock = threading.Lock()

        with common.lock:
            if not common.allow_new:
                raise RuntimeError("System shutting down")
            common.cleanup_refs.append(weakref.ref(self))

        #Function used to execute RPC callbacks and handlers and such

        self.execute = execute or pavillion.execute

        #Max number of clients we keep track of, including ignored ones
        self.maxclients = 512
        t = threading.Thread(target=self.loop)
        t.name+=":PavillionServer"
        t.daemon = daemon
        t.start()

        




    def onRPCCall(self, f, data,clientID):
        pass

    def close(self):
        with self.lock:
            pavillion_logger.info("Closing server "+str(self))

            if self.running:
                try:
                    for i in self.knownclients:
                        if self.knownclients[i].encrypt:
                            self.knownclients[i].sendSecure(self.knownclients[i].counter+1,12,b'')
                except:
                    pavillion_logger.exception("Error sending close message")
            self.running=False

            with common.lock:
                if self in common.cleanup_refs:
                    common.cleanup_refs.remove(self)
        try:
            self.sendsock.close()
        except:
            pass

    def messageTarget(self,target,callback):
        m = common.MessageTarget(target,callback)
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

    def broadcast(self, counter, opcode, data, filt=None):
        with self.lock:
            for i in self.knownclients:
                if time.time()> self.knownclients[i].ignore:
                    if(filt == None or self.knownclients[i].clientID in filt or self.knownclients[i].addr in filt):
                        self.knownclients[i].send(counter, opcode, data)

    def sendMessage(self, target, name, data, reliable=True, timeout = 10, filt=None):
            "Attempt to send the message to all subscribers. Does not raise an error on failure, but will attempt retries"
            with self.lock:
                self.counter+=1
                counter = self.counter

            if reliable:
                try:
                    expected = len([i for i in self.knownSubscribers[t] if i>120])
                except:
                    expected = 1

                e = threading.Event()
                w = common.ExpectedAckCounter(e,expected)
                w.target = target
                self.waitingForAck[counter] =w
            
            self.broadcast(counter, 1 if reliable else 3, target.encode('utf-8')+b"\n"+name.encode('utf-8')+b"\n"+data, filt)


            #Resend loop
            if reliable:
                x = 0.010
                ctr = 20
                if e.wait(x):
                    return
                while ctr and (not e.wait(x)):
                    x=min(1, x*1.1)
                    ctr-=1
                    time.sleep(x)
                    if e.wait(x):
                        return
                    self.broadcast(counter, 1 if reliable else 3, target.encode('utf-8')+b"\n"+name.encode('utf-8')+b"\n"+data,filt)
            if reliable:
                #Return how many subscribers definitely recieved the message.
                return max(0,expected-w.counter)
            else:
                return


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
                    with self.lock:
                        try:
                            for i in self.knownclients:
                                if not i == addr:
                                    if d[0] in self.knownclients[i].subscriptions:
                                        self.counter+=1
                                        self.knownclients[addr].send(self.counter,1,i,data)
                        except:
                            pass

                s = self.messageTargets[d[0].decode('utf-8')]
                with self.targetslock:
                    for i in s:
                        i = i()
                        if not i:
                            continue
                        i.callback(d[1].decode('utf-8') ,d[2],clientID)
        
        elif opcode ==2:
            d = struct.unpack("<Q",data)[0]
            if d in self.waitingForAck:
                self.waitingForAck[d].onResponse(data[8:])

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

        elif opcode==12:
            try:
                with self.lock:
                    del self.knownclients[addr]
            except:
                logging.exception("error closing connection")
                    
    def _cleanupSessions(self):
        torm=[]
        for i in sorted(list(self.knownclients.items()),key=lambda x: x[1].created):
            if i[1].lastSeen < time.time()-SESSION_TIMEOUT:
                torm.append(i[1].address)
        for i in torm:
            del self.knownclients[i]
            break

    def loop(self):

        #If we are in multicast mode, when we first start up, send some
        #unrecognized client announcements in hopes that someone notices us
        #This is why clients are supposed to listen on any multicast grops they send on.

        #We don't know if anyone is listening so we can't retry, so we send 3 times and hope at least
        #one gets through.

        #This is just an optimization, the client can also initiate the connection
        if self.mcastgroup:
            m = struct.pack("<Q",0)+struct.pack("<B",4)+b''
            self.sendsock.sendto(b"PavillionS0"+m,(self.mcastgroup,self.port))
            time.sleep(0.003)
            self.sendsock.sendto(b"PavillionS0"+m,(self.mcastgroup,self.port))
            time.sleep(0.025)
            self.sendsock.sendto(b"PavillionS0"+m,(self.mcastgroup,self.port))

        while(self.running):
            try:
                r,w,x= select.select([self.sock,self.sendsock],[],[],5)
            except:
                continue
            for i in r:
                try:
                    m,addr = i.recvfrom(4096)
                except socket.timeout:
                    continue
                except:
                    print(traceback.format_exc())
                if addr in self.ignore:
                    continue

                #There's a possibility of dropped packets in a race condition between getting rid of
                #and remaking a server. It doesn't matter, UDP is unreliable anyway
                try:
                    if addr==self.address:
                        continue
                    if not addr in self.knownclients:
                        #If we're out of space for new clients, go through and find one we haven't seen in a while.
                        if len(self.knownclients)>self.maxclients:
                            with self.lock:
                                self._cleanupSessions()
                        if len(self.knownclients)>self.maxclients:
                            continue

                        self.knownclients[addr] = _ServerClient(self, addr)
                    self.knownclients[addr].onRawMessage(addr,m)
                except OSError:
                    #Ignore errors if it's just messages recieved while closing but before
                    #the thread stops
                    if self.running:
                        pavillion_logger.exception("Exception in server loop")

                except:
                    pavillion_logger.exception("Exception in server loop")

        #Close sock at end
        self.sock.close()
        try:
            self.sendsock.close()
        except:
            pass


class Server():
    """The public interface object that a user might interact with for a Server object"""
    def __init__(self,port=DEFAULT_PORT, keys=None,pubkeys=None, address='',multicast=None,ecc_keypair=None,allow_guest=False,daemon=None,execute=None):
        keys = keys or {}
        #Yes, we want the objects to share the mutable dict, 
        self.keys = keys
        self.pubkeys = pubkeys
        if daemon is None:
            daemon = pavillion.daemon
        self.server = _Server(port=port,keys=keys,pubkeys=pubkeys,address=address,multicast=multicast,ecc_keypair=ecc_keypair,handle=self,allow_guest=allow_guest,daemon=daemon,execute=execute)
        self.registers = self.server.registers
        self.ignore = self.server.ignore

    def sendMessage(self, target, name, data, reliable=True, timeout = 10,addr=None):
        return self.server.sendMessage(target, name, data, reliable, timeout,addr)
    
    def messageTarget(self,target,function):
        "Subscibe function to target, and return a messageTarget object that you must retain in order to keep the subscription alive"
        return self.server.messageTarget(target,function)
    
    def close(self):
        self.server.close()