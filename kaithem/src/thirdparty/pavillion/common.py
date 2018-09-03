
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


import hashlib,logging,struct,threading,atexit,base64,queue

DEFAULT_PORT=1783
DEFAULT_MCAST_ADDR="239.255.28.12"

MAX_RETRIES=8

lock = threading.RLock()

allow_new = True

cleanup_refs = []


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

class MessageTarget():
    def __init__(self,target,callback):
        self.callback = callback
        self.target = target





#Allow use of bin, hex, etc PSKs 
def preprocessKey(k):
    #ECC doesn't use psk
    if k==None:
        return k
    if isinstance(k,bytes):
        if len(k)==32:
            return k
    elif isinstance(k,str):
        if len(k)==64:
            return bytes.fromhex(k)
        k = base64.b64decode(k)
        if len(k)==32:
            return k

    else:
        raise TypeError("Key must be bytes or str")
    
    raise ValueError("Key must be 32 bytes, or b64/hex encoded 32 bytes")

def cleanup():
    global allow_new
    allow_new = False
    with lock:
        #Close function mutates the list, copy first
        c = cleanup_refs[:]
        for i in c:
            try:
                i().close()
            except:
                pass

atexit.register(cleanup)

pavillion_logger = logging.getLogger("pavillion")

def nonce_from_number(n):
    return b'\x00'*(24-8)+struct.pack("<Q",n)

class testcipher():
    id=0
    def encrypt(self, d,k,nonce):
        return d+k+nonce
    def decrypt(self,d,k,nonce):
        return d[:-len(k+nonce)]
    def keyedhash(self,d,k):
        return hashlib.md5(d+k).digest()*2


#Attempt to import the crypto library.
try:
    import libnacl
    import libnacl.public
except:
    pavillion_logger.exception("Could not import libnacl, will not be able to handle encrypted messages")


class SodiumCipher():
    "Object providing a Pavillion cipher interface to libsodium"
    id=1
    asym_setup = False
    def encrypt(self,d,k,nonce):
        return libnacl.crypto_secretbox(d, nonce, k)

    def decrypt(self,d,k,nonce):
        return libnacl.crypto_secretbox_open(d, nonce, k)

    def keyedhash(self,d,k):
        return libnacl.crypto_generichash(d,k)

    def pubkey_encrypt(self,data,nonce,pk,sk):
        return libnacl.crypto_box(data,nonce,pk,sk)

    def pubkey_decrypt(self,data,nonce,pk,sk):
        return libnacl.crypto_box_open(data,nonce,pk,sk)

class libnacl_ecc(SodiumCipher):
    id=2
    asym_setup = True


#Don't actually use testcipher
ciphers = { 1:SodiumCipher(), 2:libnacl_ecc()}

