# Pavillion Reserved Messages

## Debugging

### core.print
This allows the server to print debugging output. Contents are just UTF8 text.
The message name may be empty, but if present it should be interpreted as a heading for the message.

### core.error
This allows the server to print errors. The data us utf8 and the name should be interpreted as an exception name,
like KeyError. Builtin python exception names can be used where possible.

# Misc 
### core.nfc
This allows a device to announce that it has detected a new NFC tag. The first byte must by the index of the
reader it was detected on. The remainder must by the tags UID.

## Alerts
### core.alert
This allows SCADA-like alarm states to be transmitted. The name must be the name of the alert,
and the data must be a single byte(With the reserved), a 0 for normal and a 1 for abnormal.

The reciever is entirely resposible for any trip delays or priorities.

## Tagpoints

The tag point system at present has only minimal support for bidirectional variables. On reconnection, the server will send it's data and we will have no way to tell if it's new data from the server or old data the client put there.

Use of bidirectional tags in things like three way switches will produce odd behavior with unreliable connections, so for
now tags should either be inputs or outputs.

If you do use bidirectional tags, conflicts like this can be partially resolved by having the "winner" be the device physically connetced to the controlled equipment, so long as only one device is connected.


### core.tag
This allows very simple reading and writing of "tag points", named floating point variables. It is sent by the server,
which is the "owner" of the tag point.

The message has the tag's name for the name, and then a 4-byte float in the payload, optionally
followed by three more floats, the min and the max values that are accepted, a 1 byte flags field, and the tag's "interval", and then a 64 bit /signed/ modification timestamp in the server's monotonic microseconds count.
 
The rest of the packet is reserved. The interval is a sampling rate in seconds.

When a client connects, it should declare all of it's tag points with this packet.

the lowest order bit of the flags field indicates if a client can write the tag's value. A 1 means they can.

### core.tagv
This allows setting or declaring a tagpoint's value. If sent to the server, it is a command to update. If from the server, it declares the current value. The name is the tag name and the payload is a single floating point value, followed by a 64 bit /signed/ microseconds timestamp(Always in the server's monotonic time scale no matter the sender) with all other bytes reserved.

Devices should ignore messages with old timstamps before the tag's modification time. The client is entirely responsible for converying from real time to the server's time.

Servers are not required to rebroadcast core.tagv messages to multiple clients. *They are intended for IO devices and fixed pairs of controllers*.

To make things easier on the server, it should, but is not required to reject older timestamps, and thus the client is responsible for not sending it old data. If it does so it must also reject alues more than a minute in the future.

When a device accepts a value, it must also accept the timestamp, as the timestamp is intended to represent the 
time of the datum itself and not of the arrival time. 