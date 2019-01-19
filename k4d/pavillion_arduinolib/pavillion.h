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

#define interpret(x, type) (*((type *)(x)))

int64_t readSignedNumber(void *i, int len);
//Sigh. Esp8266 aligned addressing crap workaround
uint64_t readUnsignedNumber(void *i, int len);
void writeSignedNumber(void *i, int len, int64_t val);
void writeUnsignedNumber(void *i, int len, uint64_t val);


#define PAV_OP_RELIABLE 1
#define PAV_OP_MESSAGEACK 2
#define PAV_OP_UNRELIABLE 3
#define PAV_OP_RPC 4
#define PAV_OP_QUIT 12


#ifdef ESP32

#include <WiFi.h>
#else
#include <ESP8266WiFi.h>
#endif

#include <WiFiUdp.h>

//#define PAVILLIONDEBUG


#ifdef PAVILLIONDEBUG
#define dbg(x) Serial.println(x)
#define dbgn(x) Serial.println((long)x)
#else
#define dbg(x)
#define dbgn(x)
#endif

#define RPC_ERR(code, string)        \
    *rlen = strlen(string);          \
    strcpy((char *)rbuffer, string); \
    return (code)

struct RpcFunction
{
    unsigned short index;
    int (*function)(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen);
    char *fname;
    struct RpcFunction *next;
    //If this is false, it means the function guarantees it will not send
    //broadcasts or initiate RPC calls or the like. That makes it safe to call
    //From within the polling that happens in the loop while we're trying to send broadcasts.
    bool usespavillion;
};

class KnownClient
{
    //Only the first one gets used.
    uint64_t clientcounter;
    uint8_t sessionID[16];

    //This variable can be set to a millis() time to igore all messages until N seconds past that, unless it's a protocol setup message.
    long long ignore = 0;

  public:
    uint64_t counter[3] = {0, 0, 0};
    bool ack_responded=false;
    uint64_t ack_watch = 0;

    //Retry delay for anything we need
    //A response from the client for, in ms
    float defaultretrydelay = 250;
    //Used by things that expect responses,
    //To track when the last time was.
    long long _lastAttempt = 0;

    uint16_t port;
    IPAddress addr;
    uint64_t lastSeen = 0;
    uint8_t serverNonce[32];
    uint8_t skey[32];
    uint8_t ckey[32];

    PavillionServer *server = 0;
    void onMessage(uint8_t *data, uint16_t datalen, IPAddress addr, uint16_t port);
    void sendRawEncrypted(uint8_t opcode, uint8_t *data, uint16_t datalen);
    KnownClient();
};
/*
struct BufferedIncomingMessage
{
    uint16_t port;
    IPAddress addr;
    uint64_t counter;
    uint8_t * decodedData;
}


free(x->decodedData);
free(x);
*/

class PavillionServer
{
    WiFiUDP udp;
    KnownClient *knownClients[MAX_CLIENTS];
    KnownClient *clientForAddr(IPAddress addr, uint16_t port);
    struct RpcFunction fzero = {0, 0, "null", 0};

    //Buffered messages we had to ignore because we were doing a broadcast.
    //  vector<struct BufferedIncomingMessage> awaiting;

    char *outData = 0;
    char *inData = 0;
    int inLen = 0;
    int outLen = 0;
#ifdef INC_FREERTOS_H
    //The lock that must be held to do anything that involves waiting for a reply.
    xSemaphoreHandle sendinglock;
    xTaskHandle serverTaskHandle;
#endif

  public:
    
    //If this is not 0, it gets called from within the inner loop while broadcasting;
    //It must not use any Pavillion functions, but can do other things to prevent the system from entirely locking up.
    void (*yieldFunc)() =0 ;
    //Bypasses all protections, including duplicates.
    void onApplicationMessage(IPAddress addr, uint16_t port, uint64_t counter, uint8_t *data,int datalen, KnownClient *client);

//This is not actually public, but the KnownClients need to access it
#ifndef INC_FREERTOS_H
    //No freeRTOS means we can't really handle other kinds of messages
    //While trying to send a briadcast
    bool ignore_except_ack = false;
#endif
    //Servers are in a linked list so we can track all servers
    PavillionServer *next = 0;
    PavillionServer();
    void *sn = 0;
    void *vendor = 0;
    void *deviceid = 0;
    void *devicename = 0;
    void poll();
    uint16_t port = 0;
    void listen(uint16_t port);
    void listen();
    void write(void *data, int len);
    void enableRemoteAccess();
    uint8_t *(*PSKforClient)(uint8_t *id) = 0;

    void sendUDP(uint8_t *data, uint16_t datalen, IPAddress addr, uint16_t port);
    void onMessage(uint8_t *data, uint16_t len, IPAddress addr, uint16_t port);

    void addRPC(uint16_t number, char *fname, int (*function)(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen), bool usespavillion);
    void addRPC(uint16_t number, char *fname, int (*function)(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen));
    void doRPC(uint16_t number, KnownClient *client, void *data, uint16_t datalen, uint64_t callid, bool allowPavillion);
    void broadcastMessage(const char *target, const char *name, uint8_t *data, int len, char opcode);
    void broadcastMessage(const char *target, const char *name, uint8_t *data, int len);
};
