# # This file is a global key store wherein we can globally manage DrayerDB Keys



# from typing_extensions import runtime


# class Address():
#     def __init__(self, keyseed='', pubkey=''):
#         """We don't need the pubkey if we have the key seed.

        
#         """


#         if keyseed:
#             if '-' in keyseed:
#                 raise ValueError("- is a reserved character for the future error correction feature")

#             import nacl.pwhash

#             key = nacl.pwhash.argon2id.kdf(32,keyseed, nacl.pwhash.OPSLIMIT_MODERATE, nacl.pwhash.MEMLIMIT_MODERATE)

    
#     def encrypt(self, msg,senderAddress=None):
#         """Encrypted data format: recieverKeyHint, senderKey, type(0 for pubkey only, 1 for sym layer), crypto box keypair data
#             When sending to self, additionally hash the private key, forming a symmetric key, which we use with crypto_secretbox.
#         """
#         from nacl.bindings.crypto_box import crypto_box,crypto_box_keypair
#         import os

#         if senderAddress:
#             senderKey = senderAddress.secretKey
#             senderAddress=senderAddress.address
#         else:
#             senderAddress,senderKey= crypto_box_keypair()

#         msg= crypto_box(msg,os.urandom(32),self.address,senderKey)
#         if self.secretKey:
#             from nacl.bindings import cr
#             msg = cr
    