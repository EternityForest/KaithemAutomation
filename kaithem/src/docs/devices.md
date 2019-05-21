# Kaithem Devices

Kaithem provides an abstraction called a Device that covers several kinds of device, but currently only
Kasa smartplugs and Pavillion devices are supported.

## Configuring

You configure devices through the devices page.

## API

All devices appear in the kaithem.devices[] space. All Pavillion devices post all recieved pavillion messages to the bus at /devices/<DEVNAME>/msg/<TARGET>, with the data being (pavillion message name, payload, (ip,port))

All Tagpoints the device exposes appear in the tags list under  /devices/<DEVNAME>/<TAGNAME>. These sync with the tag on the remote device as you might expect.

The value is synced using a claim called "shared" at default priority 51. If a tag is bidirectional, set this claim directly, otherwise just read or override with a higher claim.