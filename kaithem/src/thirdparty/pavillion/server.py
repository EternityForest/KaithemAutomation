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

        #The send counter we use to send stuff to clients.
        #Note that since we're unicasting stuff to each client,
        #We have a separate counter for each client
        self.counter = random.randint(2**63,2**63+1000000000)

        #we don't yet know the cipher
        self.decrypt=None
        self.encrypt=None

        self.ignore = 0

        self.created = time.time()
        #The last time we actually got a proper message from them
        #This does not count messages that aren't secure
        self.secureLastSeen =0
        self.lastSeen =0

        #What topics has this client subscribed to.
        self.subscriptions = {}

        #Sessions IDs are initialized to random values.
        #It's used so that servers can detect if they are still connected
        self.sessionID = os.urandom(16)

        #Tells us if we've completed the setup process.
        self.setupCompleted = False

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
        #TODO: Maybe someday have unsecured support?
        if True:
            self.sendSecure(counter,opcode,data)
        else:
            self.sendPlaintext(counter,opcode,data)

    def onRawMessage(self,addr, msg):
        "Handle a raw UDP packet from the client"
        s = b"PavillionS0"
        unsecure = b"Pavillion0"

        self.lastSeen = time.time()
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
                    self.server.onMessage(self, counter,opcode,msg,self.clientID)
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

                    #If we recieved a valid message from them within 1s, then
                    #this message is likely just random crap, and we can ignore it.
                    #This prevents a whole bunch of reconnect attemps when we get older
                    #messages that used a different key.
                    if self.secureLastSeen<(time.time()-1):
                        self.sendSetup(0, 4, b'')

                    #If we have recieved a valid message recently,
                    #don't ignore just because there's random line garbage,
                    if self.secureLastSeen<(time.time()-100):
                        self.ignore = time.time()+5
                    return
                
                self.secureLastSeen = time.time()
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
                            if self.client_counter< counter-250:
                                self.server.onOldMessage(self,counter,plaintext[0],plaintext[1:],self.clientID)
                            return
                    
                    if counter > self.client_counter+1:
                        with self.server.lock:
                            self.unusedOutOfOrderCounterValue = self.client_counter+1
                else:        
                    self.client_counter = counter
                
                self.server.onMessage(self,counter,plaintext[0],plaintext[1:],self.clientID)

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



                    self.secureLastSeen = time.time()
                    #Server to client session key
                    self.skey= keyedhash(clientnonce+servernonce,psk)

                    #Rehash to get the sessoin ID
                    self.sessionID = keyedhash(self.ckey, psk)[:16]

                    self.client_counter = clientcounter

                    #Make sure that nonce isn't reused
                    self.nonce = os.urandom(32)
                    self.sendSetup(0, 7, self.sessionID)
                    self.ignore=0
                    self.setupCompleted = True
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
                    self.secureLastSeen = time.time()
                    #Make sure that nonce isn't reused
                    self.clientID = clientID
                    self.ckey, self.skey, self.client_counter = ckey,skey,counter
                    self.sessionID = keyedhash(self.ckey, cpubkey)[:16]
                    self.nonce = os.urandom(32)

                    self.decrypt = ciphers[cipher].decrypt
                    self.encrypt = ciphers[cipher].encrypt

                    #If we used a guest key, report the hash of said guest key
                    if self.guest_key:
                        self.clientID = common.libnacl.crypto_generichash(self.guest_key, b'')
                    self.ignore = 0
                    self.sendSetup(0, 7, self.sessionID)
                    self.setupCompleted = True
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

        #If we should send system info like battery status,
        #wifi signal, and temperature
        self.enableStatusReporting = False

        self.ecc_keypair = ecc_keypair
        self.running = True
     

        self.knownclients = collections.OrderedDict()

        self.counter = "don'tusethis"

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
            self.sock.close()
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
            with self.lock:
                #Tell clients that the server is interested in that kind of message
                #Not all that important at the moment, just treat like an optimization
                self.broadcast(13,target.encode("utf8"))
        return m


    def cleanupTargets(self):
        for i in self.messageTargets:
                j = self.messageTargets[i]
                for k in j:
                    if not k():
                        j.remove(k)
                if not self.messageTargets[i]:
                    del self.messageTargets[i]


    #The way broadcasting works is you broadcast something and then rebriadcast it until
    #Every server has it's waitingForBroadcastAck cleared. The entire thing must be under lock.
    #Because nothing else can touch the flags or counters.
    def broadcast(self, opcode, data, filt=None):
        for i in self.knownclients:
            self.knownclients[i].waitingForBroadcastAck = False
            if self.knownclients[i].setupCompleted:
                if time.time()> self.knownclients[i].ignore:
                    if(filt == None or self.knownclients[i].clientID in filt or self.knownclients[i].addr in filt):
                        #We could be blocking for quite a while, so be sure not
                        #To even bother sending things to untrusted.
                        if self.knownclients[i].secureLastSeen> time.time()-SESSION_TIMEOUT:
                            self.knownclients[i].counter+=1
                            counter = self.knownclients[i].counter
                            self.knownclients[i].send(counter, opcode, data)
                            self.knownclients[i].waitingForBroadcastAck = counter
                       

    #Sends a message to all clients but does not increment counters.
    def rebroadcast(self, opcode, data, filt=None):
        for i in self.knownclients:
            if self.knownclients[i].setupCompleted:
                if time.time()> self.knownclients[i].ignore:
                    if(filt == None or self.knownclients[i].clientID in filt or self.knownclients[i].addr in filt):
                        #No need to send to anyone who isn't waiting for the broadcast ACK
                        if self.knownclients[i].waitingForBroadcastAck:
                            counter = self.knownclients[i].counter
                            self.knownclients[i].send(counter, opcode, data)

    def sendMessage(self, target, name, data, reliable=True, timeout = 10, filt=None):
            """
            Attempt to send the message to all subscribers. Does not raise an error on failure, but will attempt retries.
            Note that 
            """
            with self.lock:
                self.broadcast(1 if reliable else 3, target.encode('utf-8')+b"\n"+name.encode('utf-8')+b"\n"+data, filt)
            if reliable:
                x = 0.010
                ctr = 20
    
                while ctr and ([i for i in self.knownclients if  self.knownclients[i].waitingForBroadcastAck ]):
                    x=min(1, x*1.1)
                    ctr-=1
                    time.sleep(x)
                    self.rebroadcast( 1 if reliable else 3, target.encode('utf-8')+b"\n"+name.encode('utf-8')+b"\n"+data,filt)

    def onOldMessage(self,client, counter, opcode, data,clientID=None):
        addr=client.address
        if  opcode==1:
            #No counter race conditions allowed
            with self.lock:
                #Do an acknowledgement
                self.knownclients[addr].counter += 1
                if self.enableStatusReporting:
                    sb = common.getStatusBytes()
                else:
                    sb = b''
                self.knownclients[addr].send(self.knownclients[addr].counter,2,struct.pack("<Q",counter)+sb)


    def onMessage(self,client, counter, opcode, data,clientID=None):
        "Handle a message after decoding"
        addr = client.address
        #reliable message
        if  opcode==1:
            d = data.split(b'\n',2)
            target = d[0].decode('utf-8')
            name = d[1].decode('utf-8')
            payload = d[2]

            #If we have a listener for that message target
            if target in self.messageTargets:
                s = self.messageTargets[target]
                with self.targetslock:
                    for i in s:
                        i = i()
                        if not i:
                            continue
                        i.callback(name ,payload,clientID)

            #No counter race conditions allowed
            with self.lock:
                #Do an acknowledgement
                self.knownclients[addr].counter += 1
                if self.enableStatusReporting:
                    sb = common.getStatusBytes()
                else:
                    sb = b''
                self.knownclients[addr].send(self.knownclients[addr].counter,2,struct.pack("<Q",counter)+sb)

            #Repeat messages to all the other clients if broker mode is enabled.
            if self.broker:
                try:
                    self.sendMessage(target,name,data)
                except:
                    pass
        
        ##This is an ack. It doesn't need a response,
        ##So we don't need the lock
        elif opcode ==2:
            d = struct.unpack("<Q",data)[0]
            if d in self.waitingForAck:
                self.waitingForAck[d].onResponse(data[8:])

            if d == self.knownclients[addr].waitingForBroadcastAck:
                self.knownclients[addr].waitingForBroadcastAck = False
        
        #Unreliable message, don't ack. For that reason, we don't need  
        #To get the lock.
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
            with self.lock:
                try:
                    r = struct.unpack("<H",data[0:2])[0]
                    f = self.registers[r]
                    if callable(f):
                        d = f(clientID, data[2:])
                    else:
                        d = f.call(clientID, data[2:])
                    self.knownclients[addr].counter += 1
                    self.knownclients[addr].send(self.knownclients[addr].counter,
                    5,struct.pack("<Q",counter)+b'\x00\x00'+bytes(d))
                except:
                    #If an exception happens, then send the traceback to the client.
                    print(traceback.format_exc())
                    self.knownclients[addr].counter += 1
                    self.knownclients[addr].send(self.knownclients[addr].counter,
                    5,struct.pack("<Q",counter)+b'\x01\x01Exception on remote server\r\n'+
                    traceback.format_exc(6).encode('utf-8'))

        elif opcode==12:
            try:
                with self.lock:
                    del self.knownclients[addr]
            except:
                logging.exception("error closing connection")
    
        #Handle time sync requests
        if opcode==20:
            t = time.monotonic()*1000_000
            t2 = time.time()*1000_000
            with self.lock:
                self.knownclients[addr].counter +=1
                self.knownclients[addr].send(self.knownclients[addr].counter, 21,struct.pack("<QQQ",counter, int(t), int(t2)))
                    
    def _cleanupSessions(self, who=None):
        torm=[]

        for i in sorted(list(self.knownclients.items()),key=lambda x: x[1].created):
            t=time.time()

            #Give new clients five seconds to connect
            if (i[1].secureLastSeen < t-SESSION_TIMEOUT) and (i[1].lastSeen< t-5):
                torm.append(i[1].address)
            
            #But if the reason we're cleaning is to make room for a LAN client
            #We can garbage collect any unconnected non-LAN client.
            #We don't need to do this more than once to make room.

            #This is just a heuristic, we assume that our LAN will have less DDoS
            #Than the WAN.
            if not torm:
                if who and who.split('.') in ['192','10','127']:
                    if i[1].secureLastSeen < t-SESSION_TIMEOUT:
                        if not i[0][0].split('.') in ['192','10','127']:
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
                    if self.running:
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
                                #The address tells it who it's cleanig up for,
                                #So we can have anti ddos heuristics
                                self._cleanupSessions(addr)
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

        try:
            #Close sock at end
            self.sock.close()
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

    def setStatusReporting(self,s):
        "Enable or disable sending battery, temperature, and RSSI data to clients"
        self.server.enableStatusReporting = s
    def sendMessage(self, target, name, data, reliable=True, timeout = 10,addr=None):
        return self.server.sendMessage(target, name, data, reliable, timeout,addr)
    
    def messageTarget(self,target,function):
        "Subscibe function to target, and return a messageTarget object that you must retain in order to keep the subscription alive"
        return self.server.messageTarget(target,function)
    
    def close(self):
        self.server.close()
    def __del__(self):
        try:
            self.close()
        except:
            pass