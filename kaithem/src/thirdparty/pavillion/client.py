
import weakref, types, collections, struct, time, socket,threading,random,os,logging,traceback,queue,libnacl,select


from typing import Sequence, Optional, Tuple

from .common import nonce_from_number,pavillion_logger,DEFAULT_PORT,DEFAULT_MCAST_ADDR,ciphers,MAX_RETRIES,preprocessKey
from . import common
import pavillion

class RemoteError(Exception):
    pass

class BadInput(RemoteError):
    pass

class NonexistentFile(RemoteError):
    pass

class NoResponseError(RemoteError):
    pass
rerrs = {
    1: RemoteError,
    3: BadInput,
    4: NonexistentFile
}
debug_mode = False
def dbg(*a):
    if debug_mode:
        print (a)

def is_multicast(addr):
    if not ":" in addr:
        a = addr.split(".")
        if 224<= int(a[0]) <= 239:
            return True
        return False
    else:
        if addr.startswith('ff') or addr.startswith("FF"):
            return True
    return False

import queue



class _RemoteServer():
    """This class is used to keep track of the remote servers.
       It handles most of the security setup steps, and keeps track of individual
       S>C session keys. The client object itself handles C>S keys, as the client is pretending they
       are all one server and there's only that key.

       It is also used to handle incoming packets from servers.
    """


    def __init__(self,clientObject):

        #This is set on the first incoming message.
        #We trust it because we know it could not have been older than the key exchange
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

    def sendSetup(self, counter: int, opcode: int, data: bytes ,addr=None):
        "Send an unsecured packet"
        m = struct.pack("<Q",counter)+struct.pack("<B",opcode)+data
        self.clientObject.sock.sendto(b"PavillionS0"+m, self.clientObject.server_address)

    def sendNonceRequest(self):
        if self.clientObject.keypair:
            self.sendSetup(0, 1, struct.pack("<B",self.clientObject.cipher.id)+self.clientObject.clientID+self.clientObject.challenge+self.clientObject.sessionID+self.clientObject.keypair[1])
        else:
            dbg("challenge", self.challenge)
            self.sendSetup(0, 1, struct.pack("<B",self.clientObject.cipher.id)+self.clientObject.clientID+self.clientObject.challenge+self.clientObject.sessionID+b'\0'*32)


    def onRawMessage(self, msg: bytes ,addr: tuple):
        self.lastused = time.time()
        s = b"PavillionS0"
        clientobj = self.clientObject

        if msg.startswith(s):
            msg=msg[len(s):]
            counter = struct.unpack("<Q",msg[:8])[0]

            #Normal Pavillion, pass through to application layer
            if counter:
                if self.skey:
                    try:
                        msg2 = clientobj.cipher.decrypt(msg[8:], self.skey,nonce_from_number(counter))
                    except Exception as e:
                        #MOst of the time this is going to be not something we can do anything about.
                        return
                               
                    opcode =msg2[0]
                    data=msg2[1:]


                    #acknowlegement happens even for old messages, so long as they aren't too old.
                    #That's why we do them here in this section.
                    #We do this because if the ack gets lost they shouldn't just resend till it times out.
                    if opcode == 1:
                        if self.server_counter<(counter+250):
                            #No counter race conditions allowed
                            with clientobj.lock:
                                #Do an acknowledgement. Send it unicast back where it came
                                clientobj.counter += 1
                                recievedcounter = clientobj.counter
                            clientobj.send(recievedcounter,2,struct.pack("<Q",counter),addr)

                    #Duplicate protection. 
                    if self.server_counter>=counter:
                        pavillion_logger.debug("Duplicate Pavillion")
                        return
                    self.server_counter = counter

 
                    self.secure_lastused = time.time()
                    clientobj.onMessage(addr,counter,opcode,data)

                #We don't know how to process this message. So we send
                #a nonce request to the server
                else:
                    pavillion_logger.debug("Recieved packet from unknown server, attempting setup")
                    self.sendNonceRequest()

            #Counter 0 indicates protocol setup messages
            else:
                opcode = msg[8]
                data = msg[9:]
                #Message 4 is an "Unrecognized Client" message telling us to redo the whole auth process.
                #Send a nonce request.
                if opcode==4:
                    self.sendNonceRequest()
                #Message 5 is a "New server join" message, which is sent by a server to the multicast
                #Address when if first joins. It may also be unicast back to the last known addresses of clients,
                #To provide for fast reconnection if the server is powered off. Don't wear out flash memory though.
                if opcode==5:
                    self.sendNonceRequest()                
                
                if opcode==7:
                    pass
        
                if opcode==6:
                    if data==self.challenge:
                        self.backoff_until = time.time()+10
                        logging.error("Client attempted to connect with invalid client ID")

                        #Refresh the challenge
                        self.challenge = os.urandom(16)


                if opcode==2:
                    if clientobj.psk:
                        with clientobj.challengelock:
                            servernonce,challenge,h = struct.unpack("<32s16s32s",data)
                            if not challenge==clientobj.challenge:
                                dbg("client recieved bad challenge response", challenge, clientobj.challenge, data)
                                logging.debug("Client recieved bad challenge response")
                                return
                            dbg("Valid response")
                            #Ensure the nonce we get is real, or else someone could DoS us with bad nonces.
                            if time.time()-clientobj.lastChangedChallenge>30:
                                clientobj.usedServerNonces = {}
                                clientobj.challenge = os.urandom(16)
                                clientobj.lastChangedChallenge = time.time()


                            if clientobj.cipher.keyedhash(servernonce+challenge,clientobj.psk)==h:
                                    #We can accept more than one response per challenge, but each particular
                                    #is only usable once
                                    dbg("valid hash",addr)
                
                                    #send client info. Maybe a race condition here with old messages. I doubt it matters.
                                    m = struct.pack("<B16s32s32sQ",clientobj.cipher.id,clientobj.clientID,clientobj.nonce,servernonce,clientobj.counter)
                                    clientobj.counter +=1
                                    v = clientobj.cipher.keyedhash(m,clientobj.psk) 
                                    #Send the message even with used nonces, but only change state for new ones.
                                    self.sendSetup(0, 3, m+v,addr=addr)
         
                                    if servernonce in clientobj.usedServerNonces:
                                        dbg("already used that nonce,bye")
                                        return
                                    
                                    clientobj.usedServerNonces[servernonce] = True
                                    self.skey = clientobj.cipher.keyedhash(clientobj.nonce+servernonce,clientobj.psk)
                                    #Any message they send can't have been older than this handshake,
                                    #So we accept all counter values.
                                    self.server_counter =0
                                    self.sessionID = clientobj.cipher.keyedhash(clientobj.key, servernonce)[:16]

                                    clientobj.handle().onServerConnect(addr,None)

                            else:
                                dbg(servernonce+challenge,clientobj.psk)
                                dbg("client recieved bad challenge response hash",  clientobj.cipher.keyedhash(servernonce+challenge,clientobj.psk), h,data)

                                logging.debug("Client recieved bad challenge response")
                            
                if opcode == 11:
                    if  clientobj.keypair:
                        data = clientobj.cipher.pubkey_decrypt(data[24:],data[:24],clientobj.server_pubkey,clientobj.keypair[1])
                       
                        servernonce,challenge = struct.unpack("<32s16s",data)

                        m = struct.pack("<B",clientobj.cipher.id)
                        self.skey=os.urandom(32)

                        n=os.urandom(24)
                        self.server_counter =0

                        #Send an ECC Client Info
                        p = struct.pack("<32s32s32sQ",servernonce, clientobj.key, self.skey,clientobj.counter)
                        p = clientobj.cipher.pubkey_encrypt(p, n,clientobj.server_pubkey,clientobj.keypair[1])
                        self.sendSetup(0, 12, clientobj.clientID+m+n+p,addr=addr)
                        clientobj.handle().onServerConnect(addr,clientobj.server_pubkey)



                # print(msg,addr)
                # x = parsePavillion(msg)
                # print(x)
                # if x:
                #     self.onMessage(m,addr)
        else:
            unsecure = b'Pavillion0'

            #Only if PSK is None do we accept these unsecured messages
            if clientobj.server.psk is None and s.startswith(unsecure):
                msg=msg[len(unsecure):]
                counter = struct.unpack("<Q",msg[:8])[0]
                opcode=msg[8]
                msg = msg[9:]
                if opcode==11:
                    self.synced = True
                else:
                    clientobj.server.onMessage(addr, counter,opcode,msg)
                return

            logging.warning("Bad header "+str(msg))

class _Client():
    def __init__(self, address:Tuple[str,int]=('255.255.255.255',DEFAULT_PORT),clientID=None,psk=None,cipher=1,server=None,keypair=None, serverkey=None, handle=None,daemon=None):
        "Represents a Pavillion client that can both initiate and respond to requests"
        
        if daemon is None:
            daemon=pavillion.daemon

        #The address of our associated server
        self.server_address = address

        #The default timeout.
        self.timeout = 2

        #Used for optimizing the response timing
        self.fastestOverallCallResponse = 0.05

        #Average response time for each type of call we know about
        #Listed by the RPC number
        self.averageResponseTimes = {}


        #Used to keeo track of the optimization where some broadcasts are converted to unicasts.
        #We occasionally send real broadcasts for new server discovery.
        self.lastActualBroadcast = 0

        #Our message counter
        self.counter = random.randint(1024,1000000000)
        self.server_counter = 0

        self.cipher= ciphers[cipher]

        self.keypair = keypair
        self.server_pubkey = serverkey

        #Clients can be associated with a server
        self.server = server

        psk = preprocessKey(psk)
        self.psk = psk
        self.clientID = clientID

        self.lastChangedChallenge = time.time()
        self.challengelock = threading.Lock()
        self.targetslock = threading.Lock()
        self.lock = threading.Lock()
        self.nonce = os.urandom(32)
        self.challenge = os.urandom(16)
        self.usedServerNonces = {}

        #Conceptually, there is exactly one server, but in the case of multicast there's
        #multiple machines even if they all have the same key.
        self.max_servers = 128

        #Known servers, indexed by (addr,port)
        self.known_servers = {}

        #Last sent message that was sent to the default address
        self._keepalive_time = time.time()

        self.skey = None
        self.messageTargets = {}

        if self.keypair == "guest":
            self.keypair = libnacl.crypto_box_keypair()

        
        if self.psk:
            self.key = self.cipher.keyedhash(self.nonce,psk)
            self.sessionID = self.cipher.keyedhash(self.key, self.nonce)[:16]

        
        elif  self.keypair:
            self.key = os.urandom(32)
            self.sessionID = os.urandom(16)
        else:
            self.key= None
            self.sessionID = os.urandom(16)


        if not self.clientID:
            if self.keypair:
                self.clientID = libnacl.crypto_generichash(self.keypair[0])

        
        

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
            self.msock.bind((self_address[0],self.server_address[1]))
            self.msock.settimeout(1)
            group = socket.inet_aton(address[0])
            mreq = struct.pack('4sL', group, socket.INADDR_ANY)
            self.msock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        else:
            self.msock = False

        
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
        t.daemon = daemon
        t.name+=":PavillionClient"

        t.start()

        #Attempt to connect. The protocol has reconnection built in,
        #But this lets us connect in advance
        if self.psk and self.clientID:
            pass
            self.sendNonceRequest()
        elif self.keypair:
            self.sendNonceRequest()
            pass

        else:
            self.synced = False
            counter = 8
            while not self.synced and counter:
                self.sendSetup(0, 1, struct.pack("<B",self.cipher.id)+self.clientID+self.challenge)
                time.sleep(0.05)
                counter-=1


    def sendNonceRequest(self):
        if self.keypair:
            self.sendSetup(0, 1, struct.pack("<B",self.cipher.id)+self.clientID+self.challenge+self.sessionID+self.keypair[1])
        else:
            self.sendSetup(0, 1, struct.pack("<B",self.cipher.id)+self.clientID+self.challenge+self.sessionID+b'\0'*32)



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
        
        ##Experimental optimization to send to the only known server most of the time if there's only one
        #We want to send a real broadcast if we haven't done one in 3s, this is really just
        #An optimization for if we ever send frequent bursts of data
        
        #Don't override the address setting though, if manually given

        #TODO: decide if this is actually a good idea, and for what opcodes.
        try:
            if addr==None and len(self.known_servers)==1:
                if self.lastActualBroadcast> time.time()-0.1:
                    for i in self.known_servers:
                        addr = i
                else:
                    self.lastActualBroadcast = time.time()
        except:
            pass
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
        self.sock.sendto(b"PavillionS0"+m,addr or self.server_address)

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
            except:
                pass

    def _doKeepAlive(self):
        if self._keepalive_time<time.time()-30:
            try:
                self.sendMessage('','',b'', reliable=False)
            except:
                pavillion_logger.exception("Error sending keepalive")
            self._keepalive_time=time.time()

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
                if self.msock:
                    r,w,x = select.select([self.sock,self.msock],[],[],5)
                else:
                    r,w,x = select.select([self.sock],[],[],5)
            except:
                continue
            for sock in r:
                try:
                    msg,addr = sock.recvfrom(4096)
                except socket.timeout:
                    #Send keepalive messages, remove those who have not
                    #responded for 240s, which is probably about 6 packets.

                    if time.time()-l>30:
                        l=time.time()
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

    def onMessage(self,addr,counter,opcode,data):
        #If we've recieved an ack or a call response
        if opcode==0:
            print(data,addr)
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

        #Handle S->C messages
        if  opcode==3:
            d = data.split(b'\n',2)
            #If we have a listener for that message target
            if d[0].decode('utf-8') in self.messageTargets:
                s = self.messageTargets[d[0].decode('utf-8')]
                with self.targetslock:
                    #Look for weakrefs that haven't expired
                    for i in s:
                        i = i()
                        if not i:
                            continue
                        def f():
                            i.callback(d[1].decode('utf-8') ,d[2],addr)
                        self.handle().execute(f)
        #Handle S->C messages. Note that we send ack even for old messges, 
        #So we do that at a lower level.
        if  opcode==1:
            d = data.split(b'\n',2)
            #If we have a listener for that message target
            if d[0].decode('utf-8') in self.messageTargets:


                s = self.messageTargets[d[0].decode('utf-8')]
                with self.targetslock:
                    for i in s:
                        i = i()
                        if not i:
                            continue
                        def f():
                            i.callback(d[1].decode('utf-8') ,d[2],addr)
                        self.handle().execute(f)

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
                    self._cleanSubscribers()
                x[s] = time.time()
            else:
                self._cleanSubscribers()
                self.knownSubscribers[t]={s:time.time()}



    def sendMessage(self, target, name, data, reliable=True, timeout = 10,addr=None):
        "Attempt to send the message to all subscribers. Does not raise an error on failure, but will attempt retries"
        with self.lock:
            self.counter+=1
            counter = self.counter
        #If an address was specified, it doesn't count as a keepalive
        #Because it might be aimed at only one of many servers on multicast
        if addr==None:
            self._keepalive_time=time.time()

        if reliable:
            with self.subslock:
                try:
                    expected = len([ i for i in self.knownSubscribers[target] if self.knownSubscribers[target][i]>240])
                except:
                    expected = 1

            e = threading.Event()
            w = common.ExpectedAckCounter(e,expected)
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

    def call(self,name,data, timeout=None, retry=None):
        """Call a function by it's register ID. Retry is a hint for how fast to retry.
           It will never use a value slower but may speed up if it detects that it should be optimized.

           By default, it will 
        """
        retry = retry or 0.075
        if name in self.averageResponseTimes:
            #We can go to 8x faster than the specified retry time if the algorithm says to retry faster.
            #The algorithm being to go 2.5 standard deviations above what we expect
            #I believe that stil will result in approximately 
            delay = min(retry,(self.averageResponseTimes[name]+ self.stdDevResponseTimes[name]*2))
        timeout = timeout or self.timeout
        start = time.time()
        callset = []
        while time.time()-start<timeout:
            try:
                x= self._call(name,data,retry,callset)
                totaltime = time.time()-start

                #Calculate approximate average and std deviation
                if name in self.averageResponseTimes:
                    #Assumptions: nothing is ever deleted from the dict, and 
                    #we don't care if a sample gets ignored because of thread unsafeness
                    avg =  self.averageResponseTimes[name]
                    self.averageResponseTimes[name] = (avg*4+totaltime)/5
                    deviation = abs(totaltime-avg)
                    if name in self.stdDevResponseTimes:
                        #Outlier resistance
                        if deviation<(self.stdDevResponseTimes[name]*5):
                            self.stdDevResponseTimes[name] = (self.stdDevResponseTimes[name]*4+deviation)/5
                        else:
                            self.stdDevResponseTimes[name] = (self.stdDevResponseTimes[name]*24+deviation)/25
                    
                    else:
                        self.stdDevResponseTimes[name] = deviation
                else:
                    self.averageResponseTimes[name] =totaltime
                self.fastestOverallCallResponse = min(self.fastestOverallCallResponse,time.time()-start)
                #It creeps up if not smashed back down to account for changing delays
                self.fastestOverallCallResponse += 0.0005
                return x
            except NoResponseError:
                delay*=2
                pass
        raise NoResponseError("Server did not respond")


    def _call(self, name, data, timeout = None, idempotent=True, callset=None):
        """Perform one attempt at a call, without a retry"""
        with self.lock:
            self.counter+=1
            counter = self.counter
        timeout = timeout or self.timeout

        w = common.ReturnChannel()
        if callset:
            callset.append(w.queue)
        self.waitingForAck[counter] =w
        self.send(counter, 4, struct.pack("<H",name)+data)

        q = w.queue

        #The callset feature lets us check all earlier calls in the same set of attempts,
        #by passing it a list that is reused for all calls.
        d =None
        try:
            d = q.get(True,timeout)
        except:
            if callset:
                for i in reversed(callset):
                    if not i.empty():
                        d = i.get(False)
                        break
        if d==None:
            raise NoResponseError("Server did not respond")


        del self.waitingForAck[counter]
        returncode = struct.unpack("<H",d[:2])[0]
        if  returncode >0:
            raise rerrs.get(returncode,RemoteError)("Error code "+str(returncode)+d[2:].decode("utf-8","backslashreplace"))
        return d[2:]


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



class Client():
    def __init__(self, address=('255.255.255.255',1783),clientID=None,psk=None,cipher=1,keypair=None, 
    serverkey=None, server=None,execute=None,daemon=None):
        "Represents a public handle for  Pavillion client that can initiate requests"
        self.client= _Client(address,clientID,psk,cipher=cipher, server=server,keypair=keypair,serverkey=serverkey,handle=self,daemon=daemon)
        self.clientID = clientID
        self.knownSubscribers = self.client.knownSubscribers
        self.execute = execute or pavillion.execute



    def messageTarget(self,target,callback):
        return self.client.messageTarget(target, callback)
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

    def __del__(self):
        try:
            self.client.close()
        except:
            pass

    def listDir(self, path, start=0):
        "List dir size on remote, starting at the nth file, because of limited message size."
        path = path.encode("utf8")
        return[i[1:] for i in (self.call(14, struct.pack("<H",start)+path)).split(b"\x00")]



    def uploadFile(self, localName, remoteName):
        with open(localName) as f:
            self.writeFile(remoteName, f.read(),0, truncate=True)
    
    def deleteFile(self, fileName):
        "Delete a file on the remote device"
        fileName = fileName.encode("utf8")
        self.call(13, fileName)


    def writeFile(self, fileName, data, pos=0, truncate = False):
        if isinstance(data, str):
            data = data.encode("utf8")
        if isinstance(fileName, str):
            fileName = fileName.encode("utf8")
    
        first = True
        while data:
            d = data[:1024]
            x = struct.pack("<IH", pos, len(d))
            x+=d
            x+= fileName
            if first and truncate:
                self.call(11,x)
                first = False
            else:
                self.call(12,x)
            data = data[1024:]
            pos +=1024
    
    def readFile(self, fileName,pos=0,maxbytes=1024000):
        r=b''
        while 1:
            x = struct.pack("<IH", pos, min(1024,maxbytes))
            x+= fileName.encode("utf-8")
            d =self.call(10,x)
            pos+= len(d)
            r+=d
            if not d:
                return(r)    
    def getFunctionName(self,idx):
        return self.call(1,struct.pack("<B",idx)).decode('utf8', errors='ignore')


    def analogRead(self,pin):
        return struct.unpack("<i",self.call(23,struct.pack("<B",pin)))[0]


    def digitalRead(self,pin):
        return struct.unpack("<B",self.call(21,struct.pack("<B",pin)))[0]

    def pinMode(self,pin,mode):
        return self.call(20,struct.pack("<BB",pin,mode))


    def call(self,function,data=b''):
        return self.client.call(function, data)

    def countBroadcastSubscribers(self,topic):
        return self.client.countBroadcastSubscribers(topic)

    
    def onServerConnect(self, addr, pubkey):
        """
            Meant for subclassing. Used to detect whenever a secure connection to a new server happens.
            Note that this fires anytime a connection is re established. Pubkey is none if PSK
        """

    def onNewSubscriber(self, target, addr):
        """
            Meant for subclassing. Used for detecting when a new server begins listening to a message target.
        """

    def onRemoveSubscriber(self, target, addr):
        """
            Meant for subclassing. Used for detecting when a server is no longer listening to a message target
        """