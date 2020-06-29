# The SG1Device object

NOTE: At present, the Python gateway API does not support sending requests.

Requests will be recieved just like any other message, and SENDING replies
is fairly easy, but creating new SG1 requests is not implemented yet and will
require a gateway firmware update.





## SG1Device.keepAwake
If this is a callable returning non-falsy, the gateway should respond to SG1 beacons on the channel with wake requests, allowing you to wake up devices in deep sleep.

The intent is that you use a weak ref to a controller object, to automatically cancel
the wake requestwhen it dissapears.

Set to None to disable wake.


## SG1Device.onBeacon(m)
Called on incoming beacons.  Note that gateways do not support sending beacons except as automatic replies.

m is a data dict containing:

```
'gwid': "GatewayID',
'rssi': -90,
'loss': 96
```

## SG1Device.onMessage(m), SG1Device.onRTMessage(m)

Called on incoming messages. m is a dict with the full message info. 

```
'data': b'TheActualPacketData,
'rssi': -70,  
'gw': "TheGatewayThisIsFrom",
'loss': 60,   #dBm path loss(Not present for RT messages)
'id': 7,      #Node ID of physical device that sent the packet
"ts": timestamp  #In microseconds, normally since the epoch
"h": 35 # Byte 1 of the actual SG1 header. With this, you can detect if the 
        # message is a request or reply.
```

It could also contain:
```
replyTo: 7884735, //The timestamp of the message this one is replying to,
req: False //True if this is a request otherwise not present
```

## SG1Device.sendMessage(message, ** rt=False, power=-127, replyTo=None,request=False, special=False)

Send a message on the device's channel. The node ID will be 1, since the message is
coming from a hub.  Power is generally automatic, but you can force a specific power level.

You can pass the entire message dict to m to reply to that dict, but you cannot reply
to a reply.

You can pass request=True to send a request, or rt=True to send a SG1  RT message.

You can also send special messages this way.
