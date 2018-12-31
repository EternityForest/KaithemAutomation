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
#pragma once
#include <stdint.h>

class PavillionServer;
class KnownClient;

#define MAX_CLIENTS 8

#define interpret(x,type) (*((type *)(x)))



int64_t readSignedNumber(void * i,int len);
//Sigh. Esp8266 aligned addressing crap workaround
uint64_t readUnsignedNumber(void * i,int len);
void writeSignedNumber(void * i,int len, int64_t val);
void writeUnsignedNumber(void * i,int len, uint64_t val);

#ifdef ESP32

#include <WiFi.h>
#else
#include <ESP8266WiFi.h>
#endif

#include <WiFiUdp.h>

#ifdef PAVILLIONDEBUG
#define dbg(x) Serial.println(x)
#define dbgn(x) Serial.println((long)x)
#else
#define dbg(x)
#define dbgn(x)
#endif

#define RPC_ERR(code, string) *rlen=strlen(string);strcpy((char*)rbuffer, string); return (code)
struct RpcFunction
{
  unsigned short index;
  int(*function)(void * data, unsigned int datalen, KnownClient *client,void *rbuffer, unsigned int * rlen);
  char * fname;
  struct RpcFunction  * next;
};




class KnownClient
{
    //Only the first one gets used.
    uint64_t clientcounter;
    uint8_t sessionID[16];

    //This variable can be set to a millis() time to igore all messages until N seconds past that, unless it's a protocol setup message.
    long long ignore =0;

  public:
    uint64_t counter[3]={0,0,0};
    bool ack_responded;
    uint64_t ack_watch;

    uint16_t port;
    IPAddress addr;
    uint64_t lastSeen = 0;
    uint8_t serverNonce[32];
    uint8_t skey[32];
    uint8_t ckey[32];

    PavillionServer * server = 0;
    void onMessage(uint8_t * data, uint16_t datalen, IPAddress addr, uint16_t port);
    void sendRawEncrypted(uint8_t opcode, uint8_t * data, uint16_t datalen);
   KnownClient();

};

class PavillionServer
{
    WiFiUDP udp;
    KnownClient * knownClients[MAX_CLIENTS];
    KnownClient * clientForAddr(IPAddress  addr, uint16_t port);
    struct RpcFunction fzero = {0,0,"null",0};

    char * outData =0;
    char * inData =0 ;
    int inLen = 0;
    int outLen = 0;
#ifdef INC_FREERTOS_H
    //The lock that must be held to do anything that involves waiting for a reply.
    xSemaphoreHandle sendinglock;
    xTaskHandle  serverTaskHandle;
#endif

  public:
    //Servers are in a linked list so we can track all servers
    PavillionServer * next = 0;
    PavillionServer();
    void * sn = 0;
    void * vendor = 0;
    void * deviceid = 0;
    void * devicename = 0;
    void poll();
    uint16_t port=0;
    void listen(uint16_t port);
    void listen();
    void write(void * data, int len);
    void enableRemoteAccess();
    uint8_t *(*PSKforClient)(uint8_t * id)=0;

    void sendUDP(uint8_t * data, uint16_t datalen, IPAddress addr, uint16_t port);
    void onMessage(uint8_t *data, uint16_t len, IPAddress addr, uint16_t port);

    void addRPC(uint16_t number, char *fname, int(*function)(void * data, unsigned int datalen, KnownClient *client,void *rbuffer, unsigned int * rlen));
    void doRPC(uint16_t number, KnownClient *client, void * data, uint16_t datalen, uint64_t callid);
    void broadcastMessage(const char * target, const char * name, uint8_t * data, int len, char opcode);
    void broadcastMessage(const char * target, const char * name, uint8_t * data, int len);
};
