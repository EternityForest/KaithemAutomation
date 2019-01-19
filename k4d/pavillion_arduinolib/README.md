## Pavillion: Arduino ESP32 Edition!

##Intro

This library lets the ESP32 act as a pavillion server. It also provides some if the standard pavillion reserved RPC calls.


## Using it

You'll need to find your own copy of tweetnacl,and make it into an arduino library by putting the 2 files into a directory in your libraries folder.
Find them here: https://tweetnacl.cr.yp.to/software.html

You'll also need this library from RWeather: https://github.com/rweather/arduinolibs/tree/master/libraries/Crypto

Beware, this has never been audited, I am not a crypto professional, and the protocol is not stable.


```c++

#include "pavillion.h"

PavillionServer p;

#include "FS.h"
#include "SPIFFS.h"



//Given a 16byte ID, return a pointer to the PSK, or None if the client doesn't exist.
//You must define this yourself, or the server ignores all messages.

//This example returns a fixed PSK, which acts as a "universal password" for any client ID.
uint8_t * PSKforClient(uint8_t * id)
{
  return (uint8_t *)"OneGreenHillOneGreenHillOneFarGr";
}


void setup()
{
  if (!SPIFFS.begin()) {
    Serial.println("SPIFFS Mount Failed");
    return;
  }
  p.PSKforClient = PSKforClient;

  //Calling this gives any client "full access" to
  //Any supported remote builtin RPC.
  //If you only want to define your own RPCs, don't call this

  p.enableRemoteAccess();
  Serial.begin(115200);
  WiFi.persistent (false);
  WiFi.mode(WIFI_STA);
  WiFi.onEvent(WiFiEvent);
  WiFi.begin("SSID", "PASS");
  dbg("began");
}




void loop()
{
  p.poll();

}


//wifi event handler
void WiFiEvent(WiFiEvent_t event) {
  switch (event) {
    case SYSTEM_EVENT_STA_GOT_IP:
      //When connected set
      Serial.print("WiFi connected! IP address: ");
      Serial.println(WiFi.localIP());

      //You don't really need this line, Pavillion already handles auto reconnect to whatever 
      //The most recent port was. It won't drop sessions either.
      p.listen(12345);
      break;
    case SYSTEM_EVENT_STA_DISCONNECTED:
      Serial.println("WiFi lost connection");
      WiFi.begin("SSID", "PASS");
      break;
    default:
      break;
  }
}

```


### Adding your own functions
#### void PavillionServer::addRPC(uint16_t number, char *fname, int(*function)(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen), [usesPavillion])

Example: `addRPC(20, "pinMode", rpcpinmode, false);`

The last param, usesPavillion, is optional. It must be true if the function is capable of sending out any
reliable broadcasts.

If false, clients will be able to call it even while the ESP is waiting for ACKs from a broadcast, even on the 8266.


### Broadcasting a message
#### void PavillionServer::broadcastMessage(const char *target, const char *name, uint8_t *data, int len, uint8_t [opcode]);
Pass it the target, len, data, and datalen. This function is 100% blocking. It blocks until all clients
acknowledges, or it gives up in a few seconds.

RPC requests that have usesPavillion==false will still be accepted.

Opcode is optional, defaulting to PAV_OP_RELIABLE. Pass PAV_OP_UNRELIABLE instead to send an unreliable message.

Unreliable messages are non blocking and can be sent almost anywhere but are subject to packet loss and do not retransmit.

##### Doing other things while transmitting
To avoid utterly locking up the system, if the function pointer server.yieldFunc is not 0, it will be called in
the inner loop. You may not send reliable broadcasts from that function. It will be called as often as possible,
like loop().

This must be a function of 0 arguments that returns void.



### Interpreting Packed Data

Because the ESP8266 doesn't like unaligned reads, if you want to support it, and you need to work with packed structs,
use these when working with values bigger than a signle byte. They work one byte at a time and so should work no matter
how the platform handles alignment.

//Interpret i as a pointer to an integer of length len and return the value
int64_t readSignedNumber(void * i,int len);
uint64_t readUnsignedNumber(void * i,int len);

//Interpret i as a pointer to an integer of length len and write the value
void writeSignedNumber(void * i,int len, int64_t val);
void writeUnsignedNumber(void * i,int len, uint64_t val);
