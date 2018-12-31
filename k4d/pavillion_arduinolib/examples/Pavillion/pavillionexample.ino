/*
Copyright (c) 2018 Daniel Dunn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/

#include "pavillion.h"

PavillionServer p;
#include "FS.h"

#ifdef ESP32
#include "SPIFFS.h"
#endif


#define SSID 
#define WIFIPSK

//Given a 16byte ID, return a pointer to the PSK, or None if the client doesn't exist.
//You must define this yourself, or the server ignores all messages.

//This example returns a fixed PSK, which acts as a "universal password" for any client ID.
uint8_t * PSKforClient(uint8_t * id)
{
  return (uint8_t *)"ZbCG43nkb6kuUwynqSsIgLZmn0SGd1Sp";    
}



//This is a user-defined RPC function. It just echoes the data you give it.

int rpc_example(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{

    //rbuffer is the output data buffer, which is 1500 bytes long.
    //data is the input data, and datalen is the length of it.

    //There's always a null pointer past the end of input data
    memcpy(rbuffer, data,datalen);

    //Rlen is a pointer to where the function stores the len of the return data
    *rlen = datalen;


    //0 Is the successful return code
    return 0;
}

#ifdef ESP32
//wifi event handler. Pavillion already handles disconnect and reconnect,
//So we only need to handle wifi itself
void WiFiEvent(WiFiEvent_t event) {
  switch (event) {
    case SYSTEM_EVENT_STA_GOT_IP:
      //When connected set
      Serial.print("WiFi connected! IP address: ");
      Serial.println(WiFi.localIP());
      break;
    case SYSTEM_EVENT_STA_DISCONNECTED:
      Serial.println("WiFi lost connection");
      WiFi.begin(SSID, WIFIPSK);
      break;
    default:
      break;
  }
}

#endif


void setup()
{
  if (!SPIFFS.begin()) {
    Serial.println("SPIFFS Mount Failed");
    return;
  }
  p.PSKforClient = PSKforClient;



  ///register the RPC call with the server at rpc index 5000 with the name
  //"example". The client can use introspection to discover this name.
  p.addRPC(5000, "echo", rpc_example);


  //Calling this gives any client "full access" to
  //Any supported remote builtin RPC.
  //If you only want to define your own RPCs, don't call this
  
  p.enableRemoteAccess();
  Serial.begin(115200);

  //THIS LINE IS IMPORTANT! WITHOUT IT, THE ESP WRITES TO FLASH
  //EVERY TIME YOU CALL BEGIN!
  WiFi.persistent (false);
  
  WiFi.mode(WIFI_STA);
  #ifdef ESP32
  WiFi.onEvent(WiFiEvent);
  #else
  WiFi.setAutoReconnect(true);
  #endif
  
  WiFi.begin(SSID, WIFIPSK);

  //Pavillion server on port 12345  
  p.listen(12345);
}




void loop()
{
  p.poll();

}

