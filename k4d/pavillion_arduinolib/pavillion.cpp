
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
extern "C" {
#endif
#include "tweetnacl.h"
#ifdef __cplusplus
}
#endif

#define ip_cmp(a,b) ((a[0]==b[0])&(a[1]==b[1])&(a[2]==b[2])&(a[3]==b[3]))


static bool connected = false;

//Root entry of linked list of all PavillionServers
static PavillionServer * ServersList =0;


//TODO: thread safe if we ever implement closing a server
//wifi event handler lets us automatically all listening servers when disconnected
static void pav_WiFiEvent(WiFiEvent_t event) {
  PavillionServer*  p = ServersList;

  switch (event) {
    case SYSTEM_EVENT_STA_GOT_IP:
      connected = true;
      while(p)
      {
        Serial.println("Pavillion listening");
        p->listen();
        p = p->next;
      }
    break;
    case SYSTEM_EVENT_STA_DISCONNECTED:
    connected = false;
    break;

    default:
      break;
  }
}

//Basically what this does is let us do this function before main. 
static SemaphoreHandle_t setThingsUp()
{
  SemaphoreHandle_t t;
  WiFi.onEvent(pav_WiFiEvent);
  t= xSemaphoreCreateBinary();
  xSemaphoreGive(t);
  return(t);
}

static SemaphoreHandle_t PavilllionLock = setThingsUp();

#define PAV_LOCK()  assert(xSemaphoreTake(PavilllionLock,10000000))
#define PAV_UNLOCK()  xSemaphoreGive(PavilllionLock)


#define dbg(x) Serial.println(x)
#define dgb(x)








KnownClient::KnownClient()
{
  randombytes_buf(serverNonce, 32);
  //Put random garbage in the key, so it doesn't accidentally get used with a predictable value
  //Before setup.
  randombytes_buf(skey, 32);

}

//Send a Pavillion message to the Known Client. Must be called after setting up a valid connection,
//Or else garbage will be sent.
void KnownClient::sendRawEncrypted(uint8_t opcode, uint8_t* data, uint16_t datalen)
{

  //Our garbage fake version of libsodium needs 32 extra bytes after the output buffer so it doesn't crash.
  uint8_t * op = (uint8_t *)malloc(datalen + 33 + 11 + 8 + 1 + 32);
  uint8_t * encrypted = op + 11 + 8;

  this->counter[2]++;

  memcpy(op, "PavillionS0", 11);

  //copy
  memcpy((op + 11), (unsigned char *) (& (this->counter[2])), 8);

  op[11 + 8] = opcode;

  memcpy((op + 11 + 9), data, datalen);


  crypto_secretbox_easy(encrypted, encrypted,
                        datalen + 1, (uint8_t *) & (this->counter[0]),
                        this->skey);

  this->server->sendUDP(op, datalen + 16 + 8 + 1 + 11, this->addr, this->port);
  free(op);
}

void PavillionServer::broadcastMessage(const char * target, const char * name, uint8_t * data, int len)
{
  broadcastMessage(target, name,data, len, 1);
}

void PavillionServer::broadcastMessage(const char * target, const char * name, uint8_t * data, int len, char opcode)
{

  //It is important that sendinglock be the outer lock.
  //Because we release the main lock during the resend loop.
  //And deadlocks suck.
  Serial.print("gl1");
  xSemaphoreTake(sendinglock,1000000000);
  Serial.print("Gl2");
  PAV_LOCK();

  int d =2;

  int tlen = strlen(target);
  int nlen = strlen(name);

  if(opcode==1)
  {

    for (int i = 0; i < MAX_CLIENTS; i++)
    {
      if(knownClients[i])
      {
        knownClients[i]->ack_watch = knownClients[i]->counter[2];
        knownClients[i]->ack_responded = false;
      }
    }
  }

  
  while(d< 513)
  {
    for (int i = 0; i < MAX_CLIENTS;i++)
    {
      if(knownClients[i])
      {
        if((millis()-knownClients[i]->lastSeen)<300000)
        {
          //Our garbage fake version of libsodium needs 32 extra bytes after the output buffer so it doesn't crash.
          uint8_t * op = (uint8_t *)malloc(len+tlen+nlen+2 + 33 + 11 + 8 + 1 + 32);
          uint8_t * encrypted = op + 11 + 8;

          memcpy(op, "PavillionS0", 11);

          //copy
          memcpy((op + 11), (unsigned char *) (& (knownClients[i]->counter[2])), 8);

          //This is the opcode
          op[11 + 8] = opcode;


          memcpy((op + 11 + 9), target, tlen);
          op[9+11+tlen]= '\n';
          Serial.println("naaaame");
          Serial.println(name);
          memcpy((op + 11 + 9)+tlen+1, name, nlen);
          op[9+11+tlen+1+nlen]= '\n';

          memcpy((op + 11 + 9 +tlen+1+nlen+1), data, len);


          crypto_secretbox_easy(encrypted, encrypted,
                                len+tlen+nlen+2 + 1, (uint8_t *) & (knownClients[i]->counter[0]),
                                knownClients[i]->skey);

          sendUDP(op, len+tlen+nlen+2 + 16 + 8 + 1 + 11, knownClients[i]->addr, knownClients[i]->port);
          free(op);
        }
      }
    }

    //If this is an unreliable message only do one loop
    if(opcode==1)
    {
      PAV_UNLOCK();
      delay(d);
      Serial.print("gl3");
      PAV_LOCK();
      
      char canQuit = 1;

      for (int i = 0; i < MAX_CLIENTS; i++)
      {
        if(knownClients[i])
        {
          if (millis()-knownClients[i]->lastSeen>300000)
          {
            if(knownClients[i]->ack_responded ==false)
            {
              canQuit = 0;
            }
          }
        }
      }
      if(canQuit)
      {
        break;
      }
    }
    else
    {
      break;
    }
    d=d*2;
    Serial.println(d);
  }
  PAV_UNLOCK();
  xSemaphoreGive(sendinglock);
}

//Handle raw UDP Messages
void KnownClient::onMessage(uint8_t * data, uint16_t datalen, IPAddress addr, uint16_t port)
{

  //Make sure it has the header
  if (memcmp(data, "PavillionS0", 11))
  {
    return;
  }
  data += 11;
  uint64_t counter = interpret(data, uint64_t);

  data += 8;

  //If the counter is 0, it's a setup message
  if (counter)
  {
    uint8_t * nonce = (uint8_t *)malloc(24);
    ((uint64_t *)nonce)[2] = counter;
    ((uint64_t *)nonce)[0] = 0;
    ((uint64_t *)nonce)[1] = 0;
    //Attempt to decrypt before checking the counnter.
    //If we can't decrypt we know we aren't actually connected. Otherwise it might just be that
    //There was an actual duplicated packet
    
    int x = crypto_secretbox_open_easy(data, data, datalen - (8 + 11), nonce, ckey);

    free(nonce);


    if (x == -1)
    {
      Serial.println("Decrypt fail");

      //send an unrecognized client message
      this->server->sendUDP((uint8_t *)"PavillionS0\0\0\0\0\0\0\0\0\x04", 9 + 11, this->addr, this->port);
      return;
    }



    //Make sure there's not a duplicate
    if (counter <= clientcounter)
    {
      return;
    }

    clientcounter = counter;




    uint8_t opcode = data[0];
    data += 1;

    //subtract Header, counter, opcode, auth tag
    datalen -= (11 + 8 + 1 + 16);




    if(opcode==2)
    {
      if(this->ack_watch == *((uint64_t *) data))
      {
        this->ack_responded=true;
      }
    }
    //Yield the lock, because an RPC call may well try to send a message, which would require the lock.
    if (opcode == 4)
    {
      PAV_UNLOCK();
      this->server->doRPC(((uint16_t *)data)[0], this, data + 2, datalen - 2, counter);
      PAV_LOCK();
    }
  }

  //Counter is 0, it's a protocol setup message
  else
  {
    uint8_t opcode = interpret(data, uint8_t);
    data += 1;
    dbg("setup opcod");
    dbg(opcode);

    if (opcode == 1)
    {
      uint8_t cipher = interpret(data, uint8_t);
      data += 1;

      uint8_t * clientID = data;
      data += 16;


      uint8_t * clientChallenge = data;
      for (char i = 0; i < 16; i++)
      {
        Serial.print(clientChallenge[i]);
      }
      data += 16;


      uint8_t * clientSessionID = data;
      data+=16;


      /*If the session ID matches, we are already connected.
        This could happen if we recieve a multicast nonce request actually meant for another server
        or if someone is spoffing our IP to send fake unrecognized client messages.
      
      */
      if(memcmp(sessionID, clientSessionID, 16)==0)
      {
        dbg("Got opcode 1, but already connected");
        return;
      }
      uint8_t * clientPubkey = data;

      uint8_t * clientPSK = server->PSKforClient(clientID);

      //PSKforClient returns null if you give it a nonexistent client
      if (clientPSK == 0)
      {

        ignore = millis();
        dbg("No PSK for this client");
        return;
      }

      uint8_t * resp = (uint8_t *)malloc(1501);

      memcpy(resp, "PavillionS0", 11);
      uint8_t * head = resp + 11;

      interpret(head, uint64_t) = 0;
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
      uint8_t * clientID = data;
      data += 16;
      uint8_t * clientNonce = data;
      data += 32;
      uint8_t * serverNonceReply = data;
      data += 32;
      uint64_t clientcounter_b = interpret(data, uint64_t);
      dbg("client ctr is");
      dbg((unsigned long)clientcounter_b);
      data += 8;

      uint8_t * clientPSK = this->server->PSKforClient(clientID);

      uint8_t hash[32];

      if (memcmp(serverNonceReply, serverNonce,32))
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
        dbg((char *)data);
        dbg((char *)hash);
        return;
      }

      this->clientcounter = clientcounter_b;
      //Hash the client nonce to get the key they are using at the moment for sending to us
      crypto_generichash(this->ckey, 32,
                         clientNonce, 32,
                         clientPSK, 32);


      uint8_t toHash [64];
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
      this->sendRawEncrypted(0, (uint8_t*)"This here is a testing message", 25);

      //No reusing the server nonce is allowed here.
      randombytes_buf(serverNonce, 32);

    }



  }

}



//Get a pointer to the client object, and if there isn't one at that address, make one.
KnownClient * PavillionServer::clientForAddr(IPAddress addr, uint16_t port)
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

  //No known client, make a new one
  for (int i = 0; i < MAX_CLIENTS; i++)
  {

    if (this->knownClients[i] == 0)
    {
      this->knownClients[i] = new KnownClient();
      this->knownClients[i]->addr = addr;
      this->knownClients[i]->port = port;
      knownClients[i]->server = this;
      return (this->knownClients[i]);
    }

    if (millis() - this->knownClients[i]->lastSeen < 120000)
    {

      if (this->knownClients[i])
      {
        free(  this->knownClients[i]);
      }
      this->knownClients[i] = new KnownClient();
      this->knownClients[i]->addr = addr;
      this->knownClients[i]->port = port;
      knownClients[i]->server = this;

      return (this->knownClients[i]);
    }
  }
  dbg("Out of client slots");
  return 0;
}


//Send UDP
void inline PavillionServer::sendUDP(uint8_t * data, uint16_t datalen, IPAddress udpAddress, uint16_t udpPort)
{

  udp.beginPacket(udp.remoteIP(), udp.remotePort());
  udp.write(data, datalen);
  udp.endPacket();
}


static void serverTask(void * t)
{
  while(1)
  {
    ((PavillionServer*)t)->poll();
  }
}

//Do our linked list
PavillionServer::PavillionServer()
{
  PAV_LOCK();
  
  //Initialize our array of client pointers to 0
  for (int i = 0; i < MAX_CLIENTS; i++)
  {
    knownClients[i]=0;
  }
  
  if(ServersList==0)
  {
    ServersList = this;
  }
  else
  {
    PavillionServer * p = ServersList;

    while(p->next)
    {
      p=p->next;
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
  sendinglock = xSemaphoreCreateBinary();
  xSemaphoreGive(sendinglock);
}


void PavillionServer::onMessage(uint8_t *data, uint16_t len, IPAddress addr, uint16_t port)
{

 if(PSKforClient ==0)
 {
     Serial.println("Plase define a PSKforClient function");
     return;
 }
  KnownClient* x = clientForAddr(addr, port);
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
if(port)
  {
  udp.begin(port);
  }
}

void PavillionServer::poll()
{
  PAV_LOCK();
  if(connected==false)
  {
    PAV_UNLOCK();
    return;
  }
  int x = udp.parsePacket();

  if (x)
  {
    //Once again the extra 32 are for garbage fake libsodium's memory saving tricks
    uint8_t * incoming = (uint8_t *) malloc(x + 32+1);
    udp.read(incoming, 1500);
    this->onMessage(incoming, x, udp.remoteIP(), udp.remotePort());
    free(incoming);
  }
  PAV_UNLOCK();
}