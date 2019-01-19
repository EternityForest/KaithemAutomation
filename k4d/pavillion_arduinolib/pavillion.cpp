
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

#include <iostream>
#include <string.h>

#include "pavillion.h"

using namespace std;

#include "fake_libsodium.h"

#ifdef __cplusplus
extern "C"
{
#endif
#include "tweetnacl.h"
#ifdef __cplusplus
}
#endif

#define ip_cmp(a, b) ((a[0] == b[0]) & (a[1] == b[1]) & (a[2] == b[2]) & (a[3] == b[3]))

static bool connected = false;

//Root entry of linked list of all PavillionServers
static PavillionServer *ServersList = 0;

//These two functions read len bytes from i and interpret
//Them as numbers, because pointer casting doesn't work
//With unaligned.

//Sigh. Esp8266 aligned addressing crap workaround
int64_t readSignedNumber(void *i, int len)
{
  union {
    int64_t r = 0;
    uint8_t b[8];
  };
  for (int j = 0; j < len; j++)
  {
    b[j] = ((uint8_t *)i)[j];
  }
  return r;
}

//Sigh. Esp8266 aligned addressing crap workaround
uint64_t readUnsignedNumber(void *i, int len)
{
  union {
    uint64_t r = 0;
    uint8_t b[8];
  };
  for (int j = 0; j < len; j++)
  {
    b[j] = ((uint8_t *)i)[j];
  }
  return r;
}

void writeSignedNumber(void *i, int len, int64_t val)
{
  for (int j = 0; j < len; j++)
  {
    ((uint8_t *)i)[j] = ((uint8_t *)&val)[j];
  }
}

void writeUnsignedNumber(void *i, int len, uint64_t val)
{
  for (int j = 0; j < len; j++)
  {
    ((uint8_t *)i)[j] = ((uint8_t *)&val)[j];
  }
}

#ifdef ESP32
//TODO: thread safe if we ever implement closing a server
//wifi event handler lets us automatically all listening servers when disconnected
static void pav_WiFiEvent(WiFiEvent_t event)
{
  PavillionServer *p = ServersList;

  switch (event)
  {
  case SYSTEM_EVENT_STA_GOT_IP:
    dbg(F("WiFi connected"));

    //TODO: We should try to send a message to the last known server we were in contact with?
    connected = true;
    while (p)
    {
      p->listen();
      p = p->next;
    }
    break;
  case SYSTEM_EVENT_STA_DISCONNECTED:
    dbg(F("WiFi disconnected"));
    connected = false;
    break;

  default:
    break;
  }
}

//ESP8266
#else
WiFiEventHandler stationConnectedHandler;
WiFiEventHandler stationDisconnectedHandler;

static void pav_onconnect(const WiFiEventStationModeConnected &evt)
{
  dbg(F("WiFi Connected"));
  connected = true;
  PavillionServer *p = ServersList;
  while (p)
  {
    p->listen();
    p = p->next;
  }
}

static void pav_ondisconnect(const WiFiEventStationModeDisconnected &evt)
{
  dbg(F("WiFi disconnected"));
  connected = false;
}
#endif

#ifdef INC_FREERTOS_H
//Basically what this does is let us do this function before main.
static SemaphoreHandle_t setThingsUp()
{
  SemaphoreHandle_t t;
#ifdef ESP32
  WiFi.onEvent(pav_WiFiEvent);
#else
  stationConnectedHandler = WiFi.onSoftAPModeStationConnected(&pav_onconnect);
  stationDisconnectedHandler = WiFi.onSoftAPModeStationDisconnected(&pav_ondisconnect);
#endif
  t = xSemaphoreCreateBinary();
  xSemaphoreGive(t);
  return (t);
}

static SemaphoreHandle_t PavilllionLock = setThingsUp();

#define PAV_LOCK() assert(xSemaphoreTake(PavilllionLock, 1500))
#define PAV_UNLOCK() xSemaphoreGive(PavilllionLock)
#endif

#ifndef INC_FREERTOS_H
static char setThingsUp()
{
#ifdef ESP32
  WiFi.onEvent(pav_WiFiEvent);
#else
  stationConnectedHandler = WiFi.onStationModeConnected(&pav_onconnect);
  stationDisconnectedHandler = WiFi.onStationModeDisconnected(&pav_ondisconnect);
#endif
}
static char t = setThingsUp();
//These are no-ops in a single thread.
#include <assert.h>
#define PAV_LOCK() assert(1)
#define PAV_UNLOCK() assert(1)
#endif

KnownClient::KnownClient()
{
  randombytes_buf(serverNonce, 32);
  //Put random garbage in the key, so it doesn't accidentally get used with a predictable value
  //Before setup.
  randombytes_buf(skey, 32);
}

//Send a Pavillion message to the Known Client. Must be called after setting up a valid connection,
//Or else garbage will be sent.
void KnownClient::sendRawEncrypted(uint8_t opcode, uint8_t *data, uint16_t datalen)
{

  //Our garbage fake version of libsodium needs 32 extra bytes after the output buffer so it doesn't crash.
  uint8_t *op = (uint8_t *)malloc(datalen + 33 + 11 + 8 + 1 + 32);
  if (op == 0)
  {
    dbg("Malloc Fail sending raw encrypted data");
    dbg(ESP.getFreeHeap());
    dbg(datalen + 33 + 11 + 8 + 1 + 32);
    return;
  }
  uint8_t *encrypted = op + 11 + 8;

  this->counter[2]++;

  memcpy(op, "PavillionS0", 11);

  //copy
  memcpy((op + 11), (unsigned char *)(&(this->counter[2])), 8);

  op[11 + 8] = opcode;

  memcpy((op + 11 + 9), data, datalen);

  crypto_secretbox_easy(encrypted, encrypted,
                        datalen + 1, (uint8_t *)&(this->counter[0]),
                        this->skey);

  this->server->sendUDP(op, datalen + 16 + 8 + 1 + 11, this->addr, this->port);
  free(op);
}

void PavillionServer::broadcastMessage(const char *target, const char *name, uint8_t *data, int len)
{
  broadcastMessage(target, name, data, len, PAV_OP_RELIABLE);
}

void PavillionServer::broadcastMessage(const char *target, const char *name, uint8_t *data, int len, char opcode)
{
  dbg("Starting to broadcastMessage");
//It is important that sendinglock be the outer lock.
//Because we release the main lock during the resend loop.
//And deadlocks suck.
#ifdef INC_FREERTOS_H
  xSemaphoreTake(sendinglock, 1000000000);
#else
  ignore_except_ack = true;
#endif

  PAV_LOCK();

  //How long to delay before polling if it's time to try again.
  //We don't do exponential backoff individually.
  //We do a global exponential, and we try
  //with individual servers at a rate that is the slower
  //of that client's specific calculated delay
  //and the current global delay
  float d = 10;

  int tlen = strlen(target);
  int nlen = strlen(name);
  if (len == -1)
  {
    len = strlen((char *)data);
  }

  for (int i = 0; i < MAX_CLIENTS; i++)
  {
    if (knownClients[i])
    {
      //Increment the counters
      knownClients[i]->counter[2] += 1;
      //Tell client objects to watch for acks if it's reliable
      if (opcode == PAV_OP_RELIABLE)
      {
        knownClients[i]->ack_watch = knownClients[i]->counter[2];
        //This constantly falls but each extra retry bumps it back up.
        knownClients[i]->defaultretrydelay*= 0.97;


        //If it's been a long time, assume network conditions could have changed
        //So we try a little faster if we had been going ultra slowly
        if((millis()-knownClients[i]->_lastAttempt)>30*1000)
        {
          if( knownClients[i]->defaultretrydelay> 250)
          {
           knownClients[i]->defaultretrydelay = 250;
          }
        }
        knownClients[i]->_lastAttempt = 0;
      }

      //Even if only doing one round, set it false,
      //We use it to decide who to sent to
      knownClients[i]->ack_responded = false;
    }
  }

  while (d < 513)
  {
    dbg("bcast loop iteration");
    for (int i = 0; i < MAX_CLIENTS; i++)
    {
      dbg("searching");
      dbg(i);
      //The array might include null pointers
      if (knownClients[i])
      {
        dbg("Is a client");
        //If they've been gone for 300s, consider them disconnected
        if ((millis() - knownClients[i]->lastSeen) < 300000)
        {
          //Don't send to clients that already acknowledged
          //This message
          if(knownClients[i]->ack_responded==false)
          {

            if((millis()- knownClients[i]->_lastAttempt)< knownClients[i]->defaultretrydelay)
            {
              //Hasn't been long enough to try again with that client
              continue;
            }


            //Automatic retransmit delay optimization
            if (opcode == PAV_OP_RELIABLE)
            {
              //Every attempt after the first increases the 
              //delay, because the goal is to only have one attempt
              //But still have the min time.
              //So it slowly creeps down and gets increased by attempts.

              //Note that it increases by 3 percent and decreases by 12 They're different
              //So it doesn't get locked to a set of discrete steps as much.
              //The numbers after the decimal are arbitrary.

              //This also has the effect that any time a packet is lost,
              //We slow down a tiny bit, which may help with congesyion control.
              //Is ithis the first attempt to send this particular message?
              if(knownClients[i]->_lastAttempt)
              {
                knownClients[i]->defaultretrydelay*= 1.12567565;
              }
              if(knownClients[i]->defaultretrydelay>500)
              {
                knownClients[i]->defaultretrydelay= 500;
              }
              knownClients[i]->_lastAttempt =millis();
            }
            dbg("Found client to send bcast to:");
            dbg(knownClients[i]->addr);
            dbg(knownClients[i]->port);
            //Our garbage fake version of libsodium needs 32 extra bytes after the output buffer so it doesn't crash.
            uint8_t *op = (uint8_t *)malloc(len + tlen + nlen + 2 + 33 + 11 + 8 + 1 + 32);
            
            //Can't do much if the malloc fails
            if (op == 0)
            {
              continue;
            }
            uint8_t *encrypted = op + 11 + 8;

            memcpy(op, "PavillionS0", 11);

            //copy
            memcpy((op + 11), (unsigned char *)(&(knownClients[i]->counter[2])), 8);

            //This is the opcode
            op[11 + 8] = opcode;

            memcpy((op + 11 + 9), target, tlen);
            op[9 + 11 + tlen] = '\n';
            memcpy((op + 11 + 9) + tlen + 1, name, nlen);
            op[9 + 11 + tlen + 1 + nlen] = '\n';

            memcpy((op + 11 + 9 + tlen + 1 + nlen + 1), data, len);

            crypto_secretbox_easy(encrypted, encrypted,
                                  len + tlen + nlen + 2 + 1, (uint8_t *)&(knownClients[i]->counter[0]),
                                  knownClients[i]->skey);

            sendUDP(op, len + tlen + nlen + 2 + 16 + 8 + 1 + 11, knownClients[i]->addr, knownClients[i]->port);
            free(op);
          }
        }
      }
    }

    //If this is an unreliable message only do one loop
    if (opcode == PAV_OP_RELIABLE)
    {
      PAV_UNLOCK();
      if (yieldFunc)
      {
        long long start = millis();
        while (millis() - start < d)
        {
          yieldFunc();
        }
      }
      else
      {
        delay(d);
      }
      PAV_LOCK();

//Without freeRTOS, we have to do a limited form of polling
//right here, inline.
#ifndef INC_FREERTOS_H
      poll();
#endif

      char canQuit = 1;

      for (int i = 0; i < MAX_CLIENTS; i++)
      {
        if (knownClients[i])
        {
          if ((millis() - knownClients[i]->lastSeen) < 300000)
          {
            if (knownClients[i]->ack_responded == false)
            {
              dbg("Still waiting on client");
              canQuit = 0;
            }
            else
            {
              dbg("got ack");
            }
          }
        }
      }
      if (canQuit)
      {
        break;
      }
    }
    else
    {
      break;
    }
    d = d * 2;
  }
  PAV_UNLOCK();

#ifdef INC_FREERTOS_H
  xSemaphoreGive(sendinglock);
#else
  ignore_except_ack = false;
#endif
}

void PavillionServer::onApplicationMessage(IPAddress addr, uint16_t port, uint64_t counter, uint8_t *data, int datalen, KnownClient *client)
{
  //If no client given, find the client
  if (client == 0)
  {
    client = clientForAddr(addr, port);
  }
  if (client == 0)
  {
    return;
  }

  uint8_t opcode = data[0];
  data += 1;
  //subtract Header, counter, opcode, auth tag
  datalen -= (11 + 8 + 1 + 16);

  if(opcode== PAV_OP_QUIT)
  {
    //Don't actually delete it, we might need it again,
    //But set the timestamp to 0 so it's marked first in line,
    //And marked no longer included when sending broadcasts.
    client->lastSeen=0;
  }

  if (opcode == PAV_OP_MESSAGEACK)
  {
    if (client->ack_watch == readUnsignedNumber(data, 8))
    {
      dbg("Recieved message ack");
      client->ack_responded = true;
    }
  }

//This feature is only for non-rtos platforms.
//This allows a limited degree of polling, to support reliable messages WITHIN
//The retry loop for message sending.
//Unfortunately, this means we depend entirely on client retries
//And the retry period for these reliable messages has to be less than
//The client timeout for whatever they're trying to do.
#ifndef INC_FREERTOS_H
  if (ignore_except_ack)
  {

    //Ok, maybe it's not JUST acks we accept. TODO: Bettter name for that var
    //We don't allow functions that can send reliable broadcasts
    //Because we're already sending one
    if (opcode == PAV_OP_RPC)
    {
      doRPC(readUnsignedNumber(data, 2), client, data + 2, datalen - 2, counter, false);
    }
    return;
  }
#endif

  //Yield the lock, because an RPC call may well try to send a message, which would require the lock.
  if (opcode == PAV_OP_RPC)
  {
    PAV_UNLOCK();
    //Allow functions that can broadcast
    doRPC(readUnsignedNumber(data, 2), client, data + 2, datalen - 2, counter, true);
    PAV_LOCK();
  }
}

//Handle raw UDP Messages
void KnownClient::onMessage(uint8_t *data, uint16_t datalen, IPAddress addr, uint16_t port)
{
  //Make sure it has the header
  if (memcmp(data, "PavillionS0", 11))
  {
    return;
  }
  data += 11;
  uint64_t counter = readUnsignedNumber(data, 8);

  data += 8;

  //If the counter is 0, it's a setup message
  if (counter)
  {
    uint8_t *nonce = (uint8_t *)malloc(24);
    writeUnsignedNumber(nonce + 16, 8, counter);
    writeUnsignedNumber(nonce, 8, 0);
    writeUnsignedNumber(nonce + 8, 8, 0);

    //Attempt to decrypt before checking the counnter.
    //If we can't decrypt we know we aren't actually connected. Otherwise it might just be that
    //There was an actual duplicated packet

    int x = crypto_secretbox_open_easy(data, data, datalen - (8 + 11), nonce, ckey);

    free(nonce);

    if (x == -1)
    {
      //Eliminate some chattery problems where it's got multiple reconnection
      //Attempts happening all at once because they're piling up and overlapping
      if (millis() - this->lastSeen > 500)
      {
        dbg("Decrypt fail");
        //send an unrecognized client message
        this->server->sendUDP((uint8_t *)"PavillionS0\0\0\0\0\0\0\0\0\x04", 9 + 11, this->addr, this->port);
        return;
      }
    }


    //We don't have code to actually understand messages, but we can acknowledge
    //Them, because that's how keepalives work
    //Note that this happens *before* the duplicate check.
    //We do actually want to ack duplicates
    if (data[0] == PAV_OP_RELIABLE)
    {
      dbg("Sending acknowledgement");
      sendRawEncrypted(2, (uint8_t *)&counter, 8);
    }


    //Make sure there's not a duplicate
    if (counter <= clientcounter)
    {
      return;
    }

    clientcounter = counter;
    this->lastSeen = millis();
    this->server->onApplicationMessage(addr, port, counter, data, datalen, this);
  }

  //Counter is 0, it's a protocol setup message
  else
  {
    uint8_t opcode = interpret(data, uint8_t);
    data += 1;
    if (opcode == 1)
    {
      uint8_t cipher = interpret(data, uint8_t);
      data += 1;

      uint8_t *clientID = data;
      data += 16;

      uint8_t *clientChallenge = data;
      data += 16;

      uint8_t *clientSessionID = data;
      data += 16;

      /*If the session ID matches, we are already connected.
        This could happen if we recieve a multicast nonce request actually meant for another server
        or if someone is spoffing our IP to send fake unrecognized client messages.
      
      */
      if (memcmp(sessionID, clientSessionID, 16) == 0)
      {
        dbg("Got opcode 1, but already connected");
        return;
      }
      uint8_t *clientPubkey = data;

      uint8_t *clientPSK = server->PSKforClient(clientID);

      //PSKforClient returns null if you give it a nonexistent client
      if (clientPSK == 0)
      {

        ignore = millis();
        dbg("No PSK for this client");
        return;
      }

      uint8_t *resp = (uint8_t *)malloc(1501);

      memcpy(resp, "PavillionS0", 11);
      uint8_t *head = resp + 11;

      writeUnsignedNumber(head, 8, 0);
      head += 8;

      //opcode 2
      interpret(head, uint8_t) = 2;
      head += 1;

      memcpy(head, serverNonce, 32);
      head += 32;

      memcpy(head, clientChallenge, 16);
      head += 16;
      //Append a hash of the servernonce and clientChallenge to the end
      crypto_generichash(head, 32,
                         head - 48, 48,
                         clientPSK, 32);

      head += 32;

      this->server->sendUDP(resp, head - resp, this->addr, this->port);
      free(resp);
    }

    if (opcode == 3)
    {
      uint8_t cipher = interpret(data, uint8_t);
      data += 1;
      uint8_t *clientID = data;
      data += 16;
      uint8_t *clientNonce = data;
      data += 32;
      uint8_t *serverNonceReply = data;
      data += 32;
      uint64_t clientcounter_b = readUnsignedNumber(data, 8);
      data += 8;

      uint8_t *clientPSK = this->server->PSKforClient(clientID);

      uint8_t hash[32];

      if (memcmp(serverNonceReply, serverNonce, 32))
      {
        dbg("Client's reply has the wrong nonce");
        return;
      }
      //Append a hash of the servernonce and clientChallenge to the end
      crypto_generichash(hash, 32,
                         data - (1 + 16 + 32 + 32 + 8), (1 + 16 + 32 + 32 + 8),
                         clientPSK, 32);

      //Last 32 bytes of the message are a hash, if it doesn't match, ignore.
      if (memcmp(data, hash, 32))
      {
        dbg("Client's reply has the wrong hash");

        return;
      }

      //This message can't really be spoofed, because it's got the challenge response stuff.
      this->lastSeen = millis();

      this->clientcounter = clientcounter_b;
      //Hash the client nonce to get the key they are using at the moment for sending to us
      crypto_generichash(this->ckey, 32,
                         clientNonce, 32,
                         clientPSK, 32);

      uint8_t toHash[64];
      memcpy(toHash, clientNonce, 32);
      memcpy(toHash + 32, serverNonceReply, 32);

      //Calculate the session key for sending TO them
      crypto_generichash(this->skey, 32,
                         toHash, 64,
                         clientPSK, 32);

      //Calculate the session ID
      crypto_generichash(sessionID, 16,
                         ckey, 32,
                         clientPSK, 32);

      //Send the client accept message
      dbg("sending cl accept");
      this->sendRawEncrypted(16, (uint8_t *)"", 30);
      //No reusing the server nonce is allowed here.
      randombytes_buf(serverNonce, 32);
    }
  }
}

//Get a pointer to the client object, and if there isn't one at that address, make one.
KnownClient *PavillionServer::clientForAddr(IPAddress addr, uint16_t port)
{
  for (int i = 0; i < MAX_CLIENTS; i++)
  {
    if (this->knownClients[i])
    {
      if (ip_cmp(this->knownClients[i]->addr, addr))

        if (this->knownClients[i]->port == port)
        {
          return (this->knownClients[i]);
        }
    }
  }

  dbg("Packet from unknown client, trying to make handler object");
  //No known client, make a new one
  for (int i = 0; i < MAX_CLIENTS; i++)
  {

    if (this->knownClients[i] == 0)
    {

      this->knownClients[i] = new KnownClient();
      this->knownClients[i]->addr = addr;
      this->knownClients[i]->port = port;
      this->knownClients[i]->lastSeen = 0;

      knownClients[i]->server = this;
      dbg("Made client using empty slot");
      return (this->knownClients[i]);
    }

    if ((millis() - this->knownClients[i]->lastSeen) > 8 * 60 * 1000)
    {

      if (this->knownClients[i])
      {
        free(this->knownClients[i]);
      }
      this->knownClients[i] = new KnownClient();
      this->knownClients[i]->addr = addr;
      this->knownClients[i]->port = port;
      this->knownClients[i]->lastSeen = 0;

      knownClients[i]->server = this;
      dbg("Cleared old client to make room for new");
      return (this->knownClients[i]);
    }
  }
  dbg("Out of client slots");
  return 0;
}

//Send UDP
void inline PavillionServer::sendUDP(uint8_t *data, uint16_t datalen, IPAddress udpAddress, uint16_t udpPort)
{
  /*
  struct sockaddr_in addr;
  addr.sin_family = AF_INET;
  addr.sin_port = htons(port);

  memcpy(addr.sin_address, udpAddress, 4);

  sendto(socket, data, datalen, 0,
               const struct sockaddr *dest_addr, socklen_t addrlen)
*/

  udp.beginPacket(udpAddress, udpPort);
  udp.write(data, datalen);
  udp.endPacket();
}

static void serverTask(void *t)
{
  while (1)
  {
    ((PavillionServer *)t)->poll();
  }
}

//Do our linked list
PavillionServer::PavillionServer()
{
  PAV_LOCK();

  //Initialize our array of client pointers to 0
  for (int i = 0; i < MAX_CLIENTS; i++)
  {
    knownClients[i] = 0;
  }

  if (ServersList == 0)
  {
    ServersList = this;
  }
  else
  {
    PavillionServer *p = ServersList;

    while (p->next)
    {
      p = p->next;
    }
    p->next = this;
  }
  PAV_UNLOCK();

  /* xTaskCreatePinnedToCore(serverTask,
                            "PavServ",
                            4096,
                            0,
                            1,
                            &serverTaskHandle,
                            1
                           );
  */
#ifdef INC_FREERTOS_H
  sendinglock = xSemaphoreCreateBinary();
  xSemaphoreGive(sendinglock);
#endif
}

void PavillionServer::onMessage(uint8_t *data, uint16_t len, IPAddress addr, uint16_t port)
{

  if (PSKforClient == 0)
  {
    Serial.println(F("Plase define a PSKforClient function"));
    return;
  }
  KnownClient *x = clientForAddr(addr, port);
  if (x == 0)
  {
    dbg("fail");
  }
  x->onMessage(data, len, addr, port);
}

void PavillionServer::listen(uint16_t port)
{
  this->port = port;
  udp.begin(port);
}

void PavillionServer::listen()
{
  if (port)
  {
    udp.begin(port);
  }
}

void PavillionServer::poll()
{
  PAV_LOCK();
  if (connected == false)
  {
    PAV_UNLOCK();
    return;
  }
  int x = udp.parsePacket();

  if (x)
  {
    //Once again the extra 32 are for garbage fake libsodium's memory saving tricks
    uint8_t *incoming = (uint8_t *)malloc(x + 32 + 1);
    udp.read(incoming, 1500);
    this->onMessage(incoming, x, udp.remoteIP(), udp.remotePort());
    free(incoming);
  }
  PAV_UNLOCK();
}