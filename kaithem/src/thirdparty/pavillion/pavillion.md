
# The Pavillion Protocol

Pavillion is a UDP based protocol that provides reliable multicast messaging and RPC calls. 

By default, Port 1783 should be used general application traffic, and 2221 should be used for low data rate system status messages.

For multicasting, general application traffic by default should use 239.255.28.12 and low rate system messages should use 239.255.28.18

Chat messages between humans should use an application-specific port.

Remember every node must process every message on the chosen multicast group, so you may need to divide the space into multiples.

Port numbers remain the same if security is used.


The Server may listen on a multicast port, but should send all replies as unicast from a randomly-selected port. This allows
cliets to tell multiple servers on one machine apart. Server-initiated messages should always be unicast.
Pavillion is a UDP based protocol that provides reliable multicast messaging and RPC calls. 

By default, Port 1783 should be used general application traffic, and 2221 should be used for low data rate system status messages.

For multicasting, general application traffic by default should use 239.255.28.12 and low rate system messages should use 239.255.28.18

Chat messages between humans should use an application-specific port.

Remember every node must process every message on the chosen multicast group, so you may need to divide the space into multiples.

Port numbers remain the same if security is used.


The Server may listen on a multicast port, but should send all replies as unicast from a randomly-selected port. This allows
cliets to tell multiple servers on one machine apart. Server-initiated messages should always be unicast.

This means that clients must accept responses from any port on the server. This would normally be terrible for security,
but pavillion is mostly meant to be used with it's encryption layer.


## Nodes

A node may be a client, a server, and a client and server may share a port. If they do, the roles of client and server are still considered separatly.


## Message Format

Every Pavillion packet has the following general format:

|Offset|Value|
|------|-----|
|0|Fixed ASCII "Pavillion0"|
|12| 8 byte LE message counter|
|19|1 byte Opcode|
|20| N byte data area(Remainder of packet)|


The contents of the data area are opcode-dependant. The message counter must increase by at least one for
every message sent to a given address. Recievers should use this to ignore duplicates.

When a client first comes online, it should send a "sync" message to the server to tell it to reset it's counter.

To avoid issues when counters reset, nodes may use the current time in microseconds as a base for the
counter.


### Packet Types

#### 1: Reliable Message
Represents an MQTT or XMPP message with a name sent to a target(Akin to a topic). Message topics beginning with "core." are reserved.

Data area format:

<Newline terminated UTF8 target> <Newline terminated UTF8 name> <Binary payload>

#### 2: Message Acknowledge
Represents an acknowledgement of an `01 reliable message` packet, or another message type that expects acknowledgement.
Data is the message counter for that packet.


#### 3: Unreliable Message
Same as reliable but should not trigger an acknowledgement message.

#### 4: RPC Call
The first 2 bytes represent a function number, where the first 4096 are reserved. The remaining represents an argument string to the called function. Currently RPC calls must be idempotent or
else it is not possible to automatically retry them.

#### 5: RPC Response
The first 8 bytes represent the packet number of the RPC call being responded to. The next 2 represent a response typecode, where anything other than 0 indicates an error. 

The remainder is the return data of the function call.



#### 6: Register Read
The first 2 bytes represent a register number. The next 2 bytes if present represent an offset, and the next 2 represent a data length.

#### 7: Register Declaration

The first 2 bytes represent a register. The next 2 represent an offset, and the remainder is the value of that register starting at that position.



#### 8: Observe
Represents a request to be notified about changes occurring at a register for a period of time.

The first 2 bytes are the register number. The second 2 bytes are the duration. The next 2 are a rate limit, both in milliseconds.

If the sender is already subscribed, the new time limit should simply replace the old one, renewing it.


#### 9: Register Info Request
Contains a 2 bytes register number

#### 10: Register Info
Contains a 2 byte register number followed by a string having the following format: Name, Datatype, interface, description.

Datatype is a either a UUID, a DNS bases identifier, or a function type expression joining the parameter type to the return type with ->

Interface must be a UUID or a DNS based name that identifies the datatypes and purpose of the register, much like a class inheritance.

#### 10: Sync
Sent by the client when it first connects to the network. Servers recievng this message should reset their local copy of the client's counter
to be able to accept messages from them. Not neccesary when using the secure protocol.

The data area must be the client's ID. This must not be trusted outside of private LANs

#### 11: Sync Response
Sent by the server in response to a sync message from the client to acknowledge it. Not used with the secure protocol.

Data area format:
<8 byte LE of packet counter of original message>

#### 12: Quit
This message may be sent by either party, and signals the end of a session. Another quit message may be sent in reply.
The first 2 bytes should be 0 to indicate normal exiting.

#### 13: Subscribe
This message should contain a topic. It indicates that the sender of the message wishes to recieve messages on that topic.
A sender may(and should) send low-volume messages anyway, regardless of subscription status. A separate API
should be provided for "send always" and "send to subscribers". Should be acknowledged with message type 02.

#### 14: Unsubscribe
Same as above, but for unsubscribing.




#### Opcode 15

#### Opcode 16(Client Accept)
The actual message content is reserved. This message indicates to the client that the secure connection
was correctly established and may provide more info in the future.

### Reliable Messaging 

Reliable and unreliable messages can be sent by either the server or client, but work slightly differently 
on the server vs the client.

A reliable message is a single packet of data, sent to a "target" on a single client, server, or multicast group, having a utf8 name and a binary data field. Messages sent by the server should be sent unicast directly to each client individually.

A client wishing to send a multicast message must send an `01 reliable message` to the 
appropriate multicast group or unicast address. All nodes recieving this message
should reply with an `02 acknowledge` message sent via unicast to the sender.

Senders recieving this message should add the server to the list of active subscribers for that target.

Senders should resend multicasts until all active subscribers have replied. Senders should send blank messages(empty
data, name, and value) every minute as keepalives, and remove recievers that have not replied in five minutes.

### Unreliable Messaging

Unreliable messaging works the same, except senders send `03 Unreliable message` instead and no acknowledge is sent. Messages should be passed to the application layer the same either way.


## State Machine Synchronization Protocol

### Background
In some cases it might be desired to have a set of state machines whos transitions can be controlled by timers remain in sync across a network.


### Outline

Each set of state machines has a target. Whenever a state machine transitions, it sends a message containing the conceptual timestamp of the transition,
unless the transition was caused by a network message.

Conceptual timestamps, for timer triggered transitions, are calculated by adding the entry time of the old state with the length of that state. They reflect
when a transition "should have" happened regardless or real world scheduling noise.

Upon recieving a message, you transition to that state unless you are both already in that state, and your transition timestamp exactly matches the one in the message.

You set your new transition timestamp to exactly the one recieved in the message regardless of the message's actual arrival time.

To increase efficiency, the actual transition times may be randomized slightly. They should always be computed after conceptual times and not affect them at all. This randomization means that one will act as the "master" by transitioning a few milliseconds ahead, as opposed to transitioning at the same time resulting in many transition messages.

No long term drift will result as real world timestamps aren't used to calculate the next transition.


The exception is manual or non-timer transitions. In these cases the actual and conceptual times should match the real event timestamp.


## Pavillion General Events Target

The General Events Target is a Pavillion target on port XX with the target name YYY. It is reserved for small and very infrequent events about certain defined events.


## Lighting Control
Pavillion was designed to coexist with ArtNet. Realtime lighting control data should be transmitted on 239.255.28.13 and port 6454.

Lighting control should be via standard ArtNet unless security is required, except multicast should be used instead of broadcast unless backwards
compatibility is needed.




## Reserved RPC Calls
The first 4096 calls are reserved so that a set of standard calls can be defined. The currently defined ones are as follows:

### 0: Echo

This call should always return exactly the argument string, to facillitate testing.

### 1: WhatIs
This call should return the name of the function number given as a 2 byte int in the argument string. Future versions may define additional
content after a newline, which must be ignored by devices that don't understand it. If there is no RPC call defined at that index, this function must return an empty string.

### 2: Read
Read from
### 3: Write
The argument string should be input to the server's "Standard input", whatever that means for this particular server.

### 5: PavTime
This function must accept a 64 bit number followed by a 32 byte one, the tx time and tx time nanoseconds, and return a PTime packet:

Tx u64
Tx_nano u32
Rx u64
Rx_nano u32
Max_error u32


Times should be in unix time. Max error is the maximum error that the server thinks could possibly be in the Rx_time, in microseconds,



### 6: Status

This function should return the contents of the server's "status page" which should be a newline separated list of "status codes" or phrases in valid UTF-8, in any format. It can also contain basic info about the manufaturer.

### 7: Server Identity
Must return a 16 byte vendor UUID, a 16 byte product ID, and a 16 byte serial number, followed by a UTF-8 name.

### 8: Server Descriptors
Must return a UTF-8 string, which is formatted as a set of single-line descriptors beginning with an name followed by an argument
string, which is to be interpreted according to the name. A descriptor is a simple way of signalling a small amount of data, such as
a capability, a supported file type, etc, to the server.

Names beginning with "core." or any non-alphabetical character are reserved.

Example:

`com.examplecorp.voltmeter -300 1000`

Might be interpreted by one who knows what "com.examplecorp.voltmeter" is, to indivate that the device can measure between -300
and 1000 volts.

Names should generally be DNS based or be UUIDs, to ensure uniqueness. Names may not contain specian chars except "-" and ".".



### 10: File Read
Arg str: [u32 position, u16 max_bytes, utf-8 unterminated remainder filepath]
Return up to max_bytes bytes of data starting at position in the given file. Devices should use a Linux-like
virtual file system where sd cards, internal flash, etc, share one namespace.


### 11: File Write
Arg str: [u16 len, u8[len] data, u8[remainder] name]

Write to the given file starting at 0, truncating the file if it exists and
creating if it does not.

The function must return the actual length of data written as a 2 byte int.


### 12 FileWriteInto
Arg str: [u32 position, u16 len, u8[len] data, u8[remainder] name]
Write into an existing file at position, Position may point to one byte past the end of file to append.

### 13: Delete
Arg str is simply an unterminated file path. Return an empty string if the file was deleted or did not exist.

### 14: List
Arg str is a u16 followed by an unterminated filename. Return as many dir entries as possible starting at the nth entry.

Entries are a filename, prefixed by a one byte typecode and separated by nulls. 1=file, 2=dir.

### 20: pinMode
Takes 2 bytes, the first being a pin number and the second being a "mode", where that mode has bits with the following meanings:
1: Output enable
2: Pullup
4: pulldown
8: strong pullup
16: strong pulldown
32: Open collector only if 1
64: LSB drive strength
128: MSB drive strength


0 corresponds to INPUT, 139 corresponds to OUTPUT, and 3 corresponds to INPUT_PULLUP on arduino.

### 21: digitalRead(pin)
Must return 1 byte, with a 1 or zero depending on the pin state.

### 22: pwmWrite(pin, state)
call with 255 to set a pin high, 0 to set low, and anything else to trigger PWM mode.

### 23: analogRead(pin)
Returns a 4 byte signed number that is the digital value.



## Error codes


### 1: Error

### 2: Nonexistant function

### 3: Bad input

### 4: File does not exist

