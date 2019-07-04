## The Pavillion security layer

The security layer for Pavillion consists of a simple encapsulation format as follows:


PavillionS0 : Fixed ASCII
1 byte 0: Fixed 0 byte
8 Byte counter value
Payload: [Encrypted message or setup data]

The counter value from the unencrypted Pavillion is used as the counter, effectively moved outside the message to the unsecured header. 
As counter values always increment and session keys are used, we also use this value for the cryptographic nonce. It is translated from an int
to binary in a cipher-dependant manner.

Counter value 0 is reserved for protocol setup messages, which are sent unencrypted(Because they contain only hash values and the like)

The first byte of the payload is the opcode, which has a different meaning for packets with a 0 counter.

## PSK Security Model

Every client has both a 16 byte "client ID" and a 32 byte preshared key. This client ID is arbitrary and should be considered like a username.

Pavillion security does not attempt to hide the client ID even from casual snooping, and the protocol expects that the 32 byte key is a full-strength random key, as the setup process exposes nodes to high performance offline attacks.

Do not derive the key from anything but an extremely strong passphrase or random data if security matters to you.

One server may serve multiple clients with different keys. As usual, a server and client may share the same port.

This protocol does not intend to provide forward secrecy. A session key compromise compromises all past and future messages. Session keys are not changed once established if it can be avoided.




## security setup process




## Summary

The client sends a challenge response containing a 16 byte random value, and it's client ID, and the selected cipher.

The server sends a challenge response containing the server's nonce, signed with the appropriate key for that client.
The client records this nonce, and no longer accepts it in challenge responses,
to avoid replay attacks.

The client now knows that nonce goes to a trusted server. It sends an info packet signed with the PSK containing the nonce, which functions as the server's challenge. This packet also contains the client nonce, which unlike the server's is per-session and doesn't change until the client reboots.

The info packet also contains the clients counter value, and the server does not accept packets older than this after setup.

The client sends using a key derived from the PSK and it's nonce, meaning that if there are multiple servers listening on a multicast port, they can use the same key to recieve data.

The server's key is additionally derived from the server's nonce. Only one response per server nonce is allowed. Because of this, servers must be able to track multiple sessions with different nonces, or else there may be issues with multiple clients trying to connect.


The client's idea of what the server's counter should be is set the first time it gets a message,
because it could not be older than the key exchange. Thereafter messages must increment.

### Nonce Request(Client to server, Security opcode 1)
When a client wants to send a message to a server, it first sends a Nonce Request, which is simply
a message with counter 0 followed by a single 1 byte as the opcode, then the client's 1 byte cipher number, then the client's 16 byte Client ID, then a 16 byte challenge. Servers recieving this should reply with a PSK Nonce if the cipher number specifies PSK encryption,
or with an ECC Nonce otherwise.

The client pubkey is optional and used to allow "guests" not previously known by the system to connect. In this case, the library should
report a client ID derived from the first 16 bytes of the blake2b hash of the client's pubkey to the application layer, and the
actual client ID sent should be ignored. If not used it should be all zeros.

Because of multicasting, a client should accept multiple responses to a challenge, but should only accept one particular response once.
This will involve recording each the nonce or hash for each response and clearing the list when you generate a new challenge.

Challenges should change at least once a minute.


A server can use the sessionID to ignore messages if the client is already connected. The session ID
is the server to client session key, hashed with either the PSK or the client's public key, depending on
what encryption the session uses.

So long as the server is still accepting messages on that session key, the connection can be considered
in some sense "open", because there's no reason a server should change it's server to client key
while still using the old client to server key.

If this is not set up, any manner of random garbage data may be used.

It should be all zeros or random if there is no active session to check.

`CipherNumber[1], ,ClientID[16],ClientChallenge[16] sessionID[16] ClientPubkey[32]]`

### PSK Nonce(S>C, Opcode 2)

This is a message with a 0 counter, and 2 opcode, followed by a 32 byte random server nonce, followed by the 16 byte challenge found in the client's request,
followed by a 16 byte random server challenge, followed by the 32 byte keyed hash of that (challenge+nonce) with that client's PSK.

`[ServerNonce[32] ClientChallenge[16]] KeyedHash(bracketed,psk)`  


Clients should not accept nonces with incorrect hashes to prevent an easy DoS attack.

Clients recieving a Nonce(For any reason, requested or not), must reply with a PSK Client Info message.

The server nonce must not be reused across connection setup events. Therefore we must track all used nonces,
but we may flush the list when we change our challenge.

Reception of an otherwise valid message with a previously seen noce should not change the state of the client in
any way, but a PSK Client Info message should still be sent. This is because the PSK client info might be lost,
which might cause the server to never generate a new challenge(because the old one hasn't been used, from it's perspective).

Otherwise, if the nonce is new, this message should set the S>C PSK, and reset the client's idea of the server counter to 0(see below).

### PSK Client Info(C>S, Opcode 3)
This message has a counter of 0, then a 3 byte, then 1 byte indicating the client's selected cipher suite, followed by the client's ID, followed by the server's Nonce, a 32 byte Nonce generated by the client, and the client's current counter value, sent as 8-byte little endian.

This must be followed by the 32 byte keyed hash of all prior bytes of the payload, keyed with the preshared key. The specific hash algorithm depends on the selected cipher.

`[CipherNumber[1], ClientID[16],ClientNonce[32],ServerNonce[32],ClientSendCounter[8]] Hash(bracketed, PSK)`


Upon recieving a client info message, the server must validate that it matches the nonce it sent, and if it does, it must reset it's counter for
that client to the value in the client info packet.

The server nonce returned by the client must match what the server sent, this is another layer of challenge-response.

After this handshake, messages TO the server(s) must be keyed using the hash of the the client nonce, and that hash must be keyed
with the preshared key. 

Messages to the client must be keyed using the hash of the Client's nonce followed by the server's nonce keyed with the preshared key. Giving the client full control of it's send key allows
support for multicasting.

Just before sending this message, the client's idea of the server's counter should be set to 0,
as it is now impossible to replay old messages now that keys have been changed.


The hashing method shall be defined on a per-cipher suite basis. As challenge-response is a fairly basic and common primative, future ciphers will
probably use the same packet structure.

Upon recieving this message, the server should send some kind of encrypted application-layer message, so the client
knows the connection is good.


#### Server's counter
The server's counter isn't sent during setup. The client's idea of what the server's counter is gets set on the first recieved packet, because
the key the server uses to send is partially derived from the server's nonce, and server nonces cannot be replayed due to the client's challenge.

This proves that any recieved packet is newer than the client's challenge which is required for setup. The counter isstill used to prevent replays within a session.



### Unrecognized Client (Opcode 4, S>C)

A server sends this message with no payload after the opcode to indicate that the client should make a Nonce Request.

### New Server Join (Opcode 5)
This message is sent to a multicast address when a server starts listening to it. Clients should send a Nonce Request to the server if they want to send multicast.

Multicast transmitters should listen to their multicast group, ignoring their own messages, but otherwise processing
New Server Join or Unrecognized Client messages.


### Invalid Client ID(opcode 6)

This message should be sent with the client's ClientChallenge as the payload
to a client attempting to connect using an invalid ID. Clients recieving this message can back off, but should still listen
for PSK Nonce messages, in case the Invalid Client ID message was faked.

The client's challenge must be included to prevent DoS attacks. Sending this message requires being able to recieve at the server's address
and not just the ability to spoof it.


### Handling Errors
Upon recieving a message from an unfamiliar sender, a server should send a Unrecognized Peer message, which has a counter of 0, an opcode of 5,
and a data field of the client's 16 byte ID, and the client should respond with a nonce request.

A client recieving an unfamiliar message should send a nonce request message to that server.

After a certain number of failures, exponential backoff should be used.



## Asymmetric setup process


### 11: ECC Nonce (S>C)
An ECC Nonce message serves the role of a standard nonce message, but contains only the 32 byte server nonce followed by the 16 byte
client challenge. The entire data contents are encrypted using the client selected cipher's specified asymetric encryption. Because the counter is 0,
a random 24 byte nonce is selected and prepended to the encrypted data.

### 12: ECC Client Info (C>S)
Upon receiving a Nonce message with a correct challenge, a client wishing to use ECC  must send an ECC client info message with opcode 12 instead of a standard client info message.

An ECC client info has a counter value of 0, followed by a 12 byte, followed by the one byte cipher number.

This is followed by a signed and encrypted message containing the 16 byte client ID, the 32 byte server nonce(As a challenge response), followed by the 32 byte key that will be used to send messages TO the server, followed by the key that will be used to send messages to the client, followed by the 8 byte current client counter.

Because the counter is 0, a random 24 byte nonce is selected and prepended to the encrypted data.

Asymetric setup Errors will be resolved my resending nonce requests or nonces as appropriate to restart the handshake process.

## Future ciphers

Cipher suites that do not follow the usual preshared key model will be implemented using additional message types. To make this more efficient,
a message with a zero counter followed by 5 shall by considered the "Unknown message type" warning from server to client.


## Cipher Suites:
 
A cipher suite must define a keyed hash, and an encryption/decryption function. They may also define


### 1: libnacl
Pad little endian counters with 0s for the encryption nonce. ChaCha20 encryption, blake2b keyed hash


### 2: libnacl_pubkey
Same as libnacl, but specifies that ECC key setup should be used

## Discovery

Automatic Discovery of devices should use multicast DNS. 

Public key based servers supporting discovery should advertise themselves under <hex digest of blake2b hash of public key>.local

Non-public key servers should just use an arbitrary server name and advertise that via MDNS.



## Possible Errors

New client sends message to server
New server sends multicast subscribe
Client tries to connect to server it doesn't have the password for
Server reboots, causing number 1

