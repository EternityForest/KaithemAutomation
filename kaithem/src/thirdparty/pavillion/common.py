
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


import hashlib,logging,struct

DEFAULT_PORT=1783
DEFAULT_MCAST_ADDR="239.255.28.12"

MAX_RETRIES=8

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

