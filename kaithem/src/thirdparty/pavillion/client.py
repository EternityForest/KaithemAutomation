
import weakref, types, collections, struct, time, socket,threading,random,os,logging,traceback,queue

from .common import nonce_from_number,pavillion_logger,DEFAULT_PORT,DEFAULT_MCAST_ADDR,ciphers,MAX_RETRIES
from . import common


debug_mode = False
def dbg(*a):
    if debug_mode:
        print (a)

def is_multicast(addr):
    if not ":" in addr:
        a = addr.split(".")
        if 224>= int(a[0]) >= 239:
            return True
        return False
    else:
        if addr.startswith('ff') or addr.startswith("FF"):
            return True
    return False

import queue


class ReturnChannel():
    def __init__(self,q=None):
        self.queue = q or queue.Queue(64)
        #It's not a message target thing
        self.target = None
    
    def onResponse(self,data):
        self.queue.put(data,True,3)

class ExpectedAckCounter():
    #TODO track specific servers
    def __init__(self,e,counter):
        self.e = e
        self.counter = counter
        self.target = None

    def onResponse(self, data):
        self.counter-=1
        if not self.counter:
            self.e.set()




class _RemoteServer():
    """This class is used to keep track of the remote servers.
       It handles most of the security setup steps, and keeps track of individual
       S>C session keys. The client object itself handles C>S keys, as the client is pretending they
       are all one server and there's only that key.

       It is also used to handle incoming packets from servers.
    """


    def __init__(self,clientObject):
        self.server_counter = 0
        self.clientObject = clientObject

        self.challenge = os.urandom(16)


        #Each server has an individual key they use to send to us.
        #We only have one key, because it's multicastable.clientObject

        #So we just read that from the client object as needed
        self.skey=None


        #Last activity relating to this server, for knowing when to garbage collect it
        self.lastused = time.time()

        #Last activity relating to this server, for knowing when to garbage collect it
        #Only counting activity originating on the client,
        #Or activity from the server that is encrypted.
        self.secure_lastused = time.time()

    def sendSetup(self, counter, opcode, data,addr=None):
        "Send an unsecured packet"
        m = struct.pack("<Q",counter)+struct.pack("<B",opcode)+data
        self.clientObject.sock.sendto(b"PavillionS0"+m, self.clientObject.server_address)

    def sendNonceRequest(self):
        if self.clientObject.keypair:
            self.sendSetup(0, 1, struct.pack("<B",self.clientObject.cipher.id)+self.clientObject.clientID+self.challenge+self.clientObject.keypair[1])
        else:
            dbg("challenge", self.challenge)
            self.sendSetup(0, 1, struct.pack("<B",self.clientObject.cipher.id)+self.clientObject.clientID+self.challenge)


    def onRawMessage(self, msg,addr):
        self.lastused = time.time()
        s = b"PavillionS0"
        if msg.startswith(s):
            msg=msg[len(s):]
            counter = struct.unpack("<Q",msg[:8])[0]
        

            #Normal Pavillion, pass through to application layer
            if counter:
                if self.skey:
                    try:
                        msg2 = self.clientObject.cipher.decrypt(msg[8:], self.skey,nonce_from_number(counter))
                    except Exception as e:
                        #MOst of the time this is going to be not something we can do anything about.
                        return


                    #Duplicate protection
                    if self.server_counter>=counter:
                        pavillion_logger.debug("Duplicate Pavillion")
                        return
                    self.server_counter = counter

                                
                    opcode =msg2[0]
                    data=msg2[1:]
                    self.secure_lastused = time.time()
                    self.clientObject.onMessage(addr,counter,opcode,data)

                #We don't know how to process this message. So we send
                #a nonce request to the server
                else:
                    pavillion_logger.debug("uks")
                    pavillion_logger.warning("Recieved packet from unknown server, attempting setup")
                    self.sendNonceRequest()

            #Counter 0 indicates protocol setup messages
            else:
                opcode = msg[8]
                data = msg[9:]
                #Message 5 is an "Unrecognized Client" message telling us to redo the whole auth process.
                #Send a nonce request.
                if opcode==5:
                    self.sendNonceRequest()

        
                if opcode==6:
                    if data==self.challenge:
                        self.backoff_until = time.time()+10
                        logging.error("Client attempted to connect with invalid client ID")

                        #Refresh the challenge
                        self.challenge = os.urandom(16)


                if opcode==2:
     
                    if self.clientObject.psk:
                        servernonce,challenge,h = struct.unpack("<32s16s32s",data)
                        if not challenge==self.challenge:
                            dbg("client recieved bad challenge response", challenge, self.challenge)
                            logging.debug("Client recieved bad challenge response")
                        dbg("Valid response")
                        #Ensure the nonce we get is real, or else someone could DoS us with bad nonces.
                        if self.clientObject.cipher.keyedhash(servernonce+challenge,self.clientObject.psk)==h:
                        
                                #overwrite old string to Ensure challenge only used once
                                self.challenge = os.urandom(16)
                                
                                #send client info
                                m = struct.pack("<B16s32s32sQ",self.clientObject.cipher.id,self.clientObject.clientID,self.clientObject.nonce,servernonce,self.clientObject.counter)
                                self.clientObject.counter +=3
                                v = self.clientObject.cipher.keyedhash(m,self.clientObject.psk)
                                self.skey = self.clientObject.cipher.keyedhash(self.clientObject.nonce+servernonce,self.clientObject.psk)
                                self.sendSetup(0, 3, m+v,addr=addr)

                        else:
                            dbg(servernonce+challenge,self.clientObject.psk)
                            dbg("client recieved bad challenge response hash",  self.clientObject.cipher.keyedhash(servernonce+challenge,self.clientObject.psk), h)

                            logging.debug("Client recieved bad challenge response")
                            
                if opcode == 11:
                    if  self.clientObject.keypair:
                        data = self.clientObject.cipher.pubkey_decrypt(data[24:],data[:24],self.clientObject.server_pubkey,self.clientObject.keypair[1])
                       
                        servernonce,challenge = struct.unpack("<32s16s",data)

                        m = struct.pack("<B",self.clientObject.cipher.id)
                        self.skey=os.urandom(32)

                        n=os.urandom(24)

                        #Send an ECC Client Info
                        p = struct.pack("<32s32s32sQ",servernonce, self.clientObject.key, self.skey,self.clientObject.counter)
                        p = self.clientObject.cipher.pubkey_encrypt(p, n,self.clientObject.server_pubkey,self.clientObject.keypair[1])
                        self.sendSetup(0, 12, self.clientObject.clientID+m+n+p,addr=addr)



                # print(msg,addr)
                # x = parsePavillion(msg)
                # print(x)
                # if x:
                #     self.onMessage(m,addr)
        else:
            unsecure = b'Pavillion0'

            #Only if PSK is None do we accept these unsecured messages
            if self.clientObject.server.psk is None and s.startswith(unsecure):
                msg=msg[len(unsecure):]
                counter = struct.unpack("<Q",msg[:8])[0]
                opcode=msg[8]
                msg = msg[9:]
                if opcode==11:
                    self.synced = True
                else:
                    self.clientObject.server.onMessage(addr, counter,opcode,msg)
                return

            logging.warning("Bad header "+str(msg))

class _Client():
    def __init__(self, address=('255.255.255.255',DEFAULT_PORT),clientID=None,psk=None,cipher=1,server=None,keypair=None, serverkey=None, handle=None):
        "Represents a Pavillion client that can both initiate and respond to requests"
        #The address of our associated server
        self.server_address = address

        #Our message counter
        self.counter = random.randint(1024,1000000000)

        self.server_counter = 0

        self.cipher= ciphers[cipher]

        self.keypair = keypair
        self.server_pubkey = serverkey

        #Clients can be associated with a server
        self.server = server

        self.psk = psk
        self.clientID = clientID



        #Conceptually, there is exactly one server, but in the case of multicast there's
        #multiple machines even if they all have the same key.
        self.max_servers = 128

        #Known servers, indexed by (addr,port)
        self.known_servers = {}

        #Last send message to each target that we have subs for
        self._keepalive_times = {}

        self.skey = None
        self.nonce = os.urandom(32)
        self.challenge = os.urandom(16)

        if self.keypair == "guest":
            self.keypair = libnacl.crypto_box_keypair()

        
        if self.psk:
            self.key = self.cipher.keyedhash(self.nonce,psk)
        
        elif  self.keypair:
            self.key = os.urandom(32)
        else:
            self.key= None

  
        if not self.clientID:
            if self.keypair:
                self.clientID = libnacl.generic_hash(self.keypair[0])

        
        

        self_address = ('', 0)

        self.lock=threading.Lock()

        # Create the socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) 
        # Bind to the server address
        self.sock.bind(self_address)
        self.sock.settimeout(1)


        if is_multicast(address[0]):
            # Create the socket
            self.msock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.msock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)  
            self.msock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  
            self.msock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) 
            # Bind to the server address
            self.msock.bind(self_address)
            self.msock.settimeout(1)
            group = socket.inet_aton(address[0])
            mreq = struct.pack('4sL', group, socket.INADDR_ANY)
            self.msock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)


        
        self.running = True

        def cl(*args):
            self.close()
        self.clfun = cl
        #If we have a handle, make it so that if the handle gets collected the server thread stops
        if handle:
            self.handle = weakref.ref(handle,cl)

        #lastseen time  dicts indexed by the name of what you are subscribing to, then indexed by subscriber IP
        #This is a list of *other* machines that are subscribing. All a "subscription" is, is a response to a multicast packet.
        #If we get less responses than usual, we know we should retry.
        self.knownSubscribers = {}

        self.subslock = threading.Lock()
        self.waitingForAck = weakref.WeakValueDictionary()
        self.backoff_until = time.time()


        t = threading.Thread(target=self.loop)
        t.name+=":PavillionClient"

        t.start()

        if is_multicast(address[0]):
            t = threading.Thread(target=self.mcast_loop)
            t.name+=":PavillionClient"
            t.start()


        if self.psk and self.clientID:
            self.sendSetup(0, 1, struct.pack("<B",self.cipher.id)+self.clientID+self.challenge)
        elif self.keypair:
            self.sendSetup(0, 1, struct.pack("<B",self.cipher.id)+self.clientID+self.challenge)

        else:
            self.synced = False
            counter = 8
            while not self.synced and counter:
                self.sendSetup(0, 1, struct.pack("<B",self.cipher.id)+self.clientID+self.challenge)
                time.sleep(0.05)
                counter-=1




    def close(self):
        with self.lock:
            if self.running:
                self.counter+=1
                self.sendSecure(self.counter,12,b'')
                self.running = False

        with common.lock:
            if self in common.cleanup_refs:
                common.cleanup_refs.append(weakref.ref(self))

    def send(self, counter, opcode, data,addr=None):
        if self.psk or self.keypair:
            self.sendSecure(counter,opcode,data,addr)
        else:
            self.sendPlaintext(counter,opcode,data,addr)


    def sendPlaintext(self, counter, opcode, data,addr=None):
        "Send an unsecured packet"
        m = struct.pack("<Q",counter)+struct.pack("<B",opcode)+data
        self.sock.sendto(b"Pavillion0"+m,addr or self.server_address)

    def sendSetup(self, counter, opcode, data,addr=None):
        "Send an unsecured packet"
        m = struct.pack("<Q",counter)+struct.pack("<B",opcode)+data
        self.sock.sendto(b"PavillionS0"+m,self.server_address)

    def sendSecure(self, counter, opcode, data,addr=None):
        "Send a secured packet"
        self.lastSent = time
        q = struct.pack("<Q",counter)
        n = b'\x00'*(24-8)+struct.pack("<Q",counter)
        m = struct.pack("<B",opcode)+data
        m = self.cipher.encrypt(m,self.key,n)
        self.sock.sendto(b"PavillionS0"+q+m,addr or self.server_address)


    #Get rid of old subscribers, only call from _seenSubscriber
    def _cleanSubscribers(self):
            try:
                torm_o = []
                for i in self.knownSubscribers:
                    torm = []
                    for j in self.knownSubscribers[i]:
                        if self.knownSubscribers[i](j)[1]<time.time()-240:
                            torm.append(j)
                    for j in torm:
                            self.knownSubscribers[i].pop(j)
                            self.handle().onRemoveSubscriber(i,j)
                    if not self.knownSubscribers[i]:
                        torm_o.append(i)
                for i in torm_o:
                    del self.knownSubscribers[i]
                    try:
                        del self._keepalive_times[i]
                    except:
                        pass
            except:
                pass

    def _doKeepAlive(self):
        for i in self._keepalive_times:
            if self._keepalive_times[i]<time.time()-30:
                self.sendMessage(i,'',b'', reliable=False)
                self._keepalive_times[i]=time.time()

    def countBroadcastSubscribers(self,target):
        with self.subslock:
            if not target in self.knownSubscribers:
                return 0
            else:
                return len(self.knownSubscribers[target])


    


    def loop(self):
        "Main loop that should always be running in a thread"
        l = time.time()
        while(self.running):
            try:
                msg,addr = self.sock.recvfrom(4096)
            except socket.timeout:
                #Send keepalive messages, remove those who have not
                #responded for 240s, which is probably about 6 packets.

                if time.time()-l>30:
                    self._doKeepAlive()
                    with self.subslock:
                        self._cleanSubscribers()
                continue

            try:
                if addr in self.known_servers:
                    self.known_servers[addr].onRawMessage(msg,addr)
                else:
                    with self.lock:
                        if len(self.known_servers)>self.max_servers:
                            x = sorted(self.known_servers.values(), key=lambda x:x.secure_lastused)[0]

                            if (x.secure_lastused<time.time()-300) and (x.lastused<time.time()-10):
                                self.known_servers.remove(x.machine_addr)

                        if not len(self.known_servers)>self.max_servers:
                            self.known_servers[addr] = _RemoteServer(self)
                            self.known_servers[addr].machine_addr = addr
                            self.known_servers[addr].onRawMessage(msg,addr)

            except:
                logging.exception("Exception in client loop")
     
        #Close socket at loop end
        self.sock.close()

    def mcast_loop(self):
        "If we are connecting to a server on a multicast server, we need this other loop to listen to traffic there"
        while(self.running):
            try:
                msg,addr = self.msock.recvfrom(4096)
            except socket.timeout:
                continue
            try:
                if addr in self.known_servers:
                    self.known_servers[addr].onRawMessage(msg,addr)
                else:
                    with self.lock:
                        if len(self.known_servers)>self.max_servers:
                            x = sorted(self.known_servers.values(), key=lambda x:x.secure_lastused)[0]

                            if (x.secure_lastused<time.time()-300) and (x.lastused<time.time()-10):
                                self.known_servers.remove(x.machine_addr)

                        if not len(self.known_servers)>self.max_servers:
                            self.known_servers[addr] = _RemoteServer(self)
                            self.known_servers[addr].machine_addr = addr
                            self.known_servers[addr].onRawMessage(msg,addr)

            except:
                logging.exception("Exception in client loop")
     
        #Close socket at loop end
        self.sock.close()

    def onMessage(self,addr,counter,opcode,data):
        #If we've recieved an ack or a call response
        if opcode==0:
            print(data)
        if opcode==2 or opcode==5:
            #Get the message number it's an ack for
            d = struct.unpack("<Q",data[:8])[0]

            if d in self.waitingForAck:
                #We've seen a subscriber for that target
                if self.waitingForAck[d].target:
                    self._seenSubscriber(addr,self.waitingForAck[d].target)

                try:
                    #Decrement the counter that started at 0
                    self.waitingForAck[d].onResponse(data[8:])
                except Exception:
                    print(traceback.format_exc(6))
                    pass

    #Call this with addr, target when you get an ACK from a packet you sent
    #It uses a lock so it's probably really slow, but that's fine because
    #This protocol isn't meant for high data rate stuff.
    def _seenSubscriber(self,s, t):
        with self.subslock:
            if not t in self.knownSubscribers or( not s in self.knownSubscribers[t]):
                self.handle().onNewSubscriber(t,s)
            if t in self.knownSubscribers:
                x = self.knownSubscribers[t]
                if not s in x:
                    self.cleanSubscribers()
                x[s] = time.time()
            else:
                self._cleanSubscribers()
                self.knownSubscribers[t]={s:time.time()}



    def sendMessage(self, target, name, data, reliable=True, timeout = 10,addr=None):
        "Attempt to send the message to all subscribers. Does not raise an error on failure, but will attempt retries"
        with self.lock:
            self.counter+=1
            counter = self.counter
        self._keepalive_times[target]=time.time()

        if reliable:
            try:
                expected = len([i for i in self.knownSubscribers[t] if i>120])
            except:
                expected = 1

            e = threading.Event()
            w = ExpectedAckCounter(e,expected)
            w.target = target
            self.waitingForAck[counter] =w
        
        self.send(counter, 1 if reliable else 3, target.encode('utf-8')+b"\n"+name.encode('utf-8')+b"\n"+data,addr=addr)


        #Resend loop
        if reliable:
            x = 0.010
            ctr = MAX_RETRIES
            if e.wait(x):
                return
            while ctr and (not e.wait(x)):
                x=min(1, x*1.1)
                ctr-=1
                time.sleep(x)
                if e.wait(x):
                    return
                self.send(counter, 1 if reliable else 3, target.encode('utf-8')+b"\n"+name.encode('utf-8')+b"\n"+data)
        if reliable:
            #Return how many subscribers definitely recieved the message.
            return max(0,expected-w.counter)
        else:
            return

    def call(self,name,data, timeout=10):
        "Call a function by it's register ID"
        return self._call(name,data,timeout)

    def _call(self, name, data, timeout = 10):
        with self.lock:
            self.counter+=1
            counter = self.counter


        w = ReturnChannel()
        self.waitingForAck[counter] =w
        
        self.send(counter, 4, struct.pack("<H",name)+data)

        x = 0.003
        ctr = 24
        time.sleep(x)

        q = w.queue
        
        while ctr and q.empty():
            x=min(1, x*1.1)
            ctr-=1
            time.sleep(x)
            self.send(counter, 4, struct.pack("<H",name)+data)

        if q.empty():
            raise RuntimeError("Server did not respond")
        
        d = q.get()
        returncode = struct.unpack("<H",d[:2])[0]
        if  returncode >0:
            raise RuntimeError("Error code "+str(returncode)+d[2:].decode("utf-8","backslashreplace"))
        return d[2:]




class Client():
    def __init__(self, address=('255.255.255.255',1783),clientID=None,psk=None,cipher=1,keypair=None, serverkey=None, server=None):
        "Represents a public handle for  Pavillion client that can initiate requests"
        self.client= _Client(address,clientID,psk,cipher=cipher, server=server,keypair=keypair,serverkey=serverkey,handle=self)
        self.clientID = clientID
        self.knownSubscribers = self.client.knownSubscribers
        if psk and not isinstance(psk,bytes):
            raise TypeError("PSK must be bytes")
        
      

    @property
    def address(self):
        return self.client.sock.getsockname()

    def sendMessage(self,target,name,value,reliable=True, timeout=5,addr=None):
        """
            Send a message to the associated server(s) for this client. Addr may be a (ip,port) tuple
            Allowing multicast clienys to send to a specific server
        """
        return self.client.sendMessage(target,name,value,reliable, timeout, addr)

    def close(self):
        self.client.close()    
       

    def call(self,function,data=b''):
        return self.client.call(function, data)

    def countBroadcastSubscribers(self,topic):
        return self.client.countBroadcastSubscribers(topic)

    def onNewSubscriber(self, target, addr):
        """
            Meant for subclassing. Used for detecting when a new server begins listening to a message target.
        """

    def onRemoveSubscriber(self, target, addr):
        """
            Meant for subclassing. Used for detecting when a server is no longer listening to a message target
        """