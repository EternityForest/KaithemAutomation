
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


int rpcpinmode(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{
  if (((uint8_t* )data)[1] == 0)
  {
    pinMode(((uint8_t* )data)[0], INPUT);
  }
  else if (((uint8_t* )data)[1] == 3)
  {
    pinMode(((uint8_t* )data)[0], INPUT_PULLUP);
  }
  else if (((uint8_t* )data)[1] == 139)
  {
    pinMode(((uint8_t* )data)[0], OUTPUT);
  }
  else
  {
    RPC_ERR(2, "Supported pinModes: 0, 3, 139");

  }

  *rlen = 0;
  return 0;
}

int rpcanalogread(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{
  *rlen = 4;
  dbg(((uint8_t* )data)[0]);
  dbg(analogRead(((uint8_t* )data)[0]));

  ((int32_t *)rbuffer)[0] = analogRead(((uint8_t* )data)[0]);
  return 0;
}



int rpcdigitalread(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{
  *rlen = 1;
  ((uint8_t *)rbuffer)[0] = digitalRead(((uint8_t* )data)[0]);
  return 0;
}


#include "FS.h"
#include "SPIFFS.h"


//rpc call that takes a 4 byte pointer and 2 byte len and reads up to that many bytes from a file
int rpcfsread(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{
  rlen[0] = 0;
  unsigned int pos = ((uint32_t *)data)[0];
  unsigned int m = ((uint16_t *)(data + 4))[0];

  File file = SPIFFS.open((char*)data + 6);
  if (!file || file.isDirectory()) {
    return 1;
  }
  int x = 0;

  file.seek(pos);
  if (m > 1400)
  {
    m = 1400;
  }



  *rlen = file.readBytes((char*)rbuffer, m);
  file.close();
  return 0;
}

//rpc call that takes a 4 byte pointer and 2 byte len and a block of data then an fn, and writes that to a file at that pos
int rpcfswrite(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{
  *rlen = 0;
  unsigned int pos = ((uint32_t *)data)[0];
  unsigned int m = ((uint16_t *)(data + 4))[0];

  dbg((char *)data + 6 + m);
  dbg(pos);
  dbg(m);
  File file;

  file = SPIFFS.open((char*)data + 6 + m, "w");


  if (!file) {
    file.close();
    RPC_ERR(3, (char*)data + 6 + m);
  }


  
  if (file.isDirectory()) {
    file.close();
    RPC_ERR(1, "Selected file is a directory");
  }
  int x = 0;

  file.write((uint8_t*)data + 6, m);
  file.close();
  return 0;

}



// rpc call that takes a 4 byte pointer and 2 byte len and a block of data then an fn, and writes that to a file at that pos
int rpcfswriteinto(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{
  *rlen = 0;
  unsigned int pos = ((uint32_t *)data)[0];
  unsigned int m = ((uint16_t *)(data + 4))[0];

  dbg((char *)data + 6 + m);
  dbg(pos);
  dbg(m);

  File file;
  if (SPIFFS.exists((char*)data + 6 + m))
  {

    dbg("writeto existing");
    file = SPIFFS.open((char*)data + 6 + m, "r+");
    if (file.size() <= pos)
    {
      dbg("Going to append");
      file.close();
      file = SPIFFS.open((char*)data + 6 + m, "a");
    }
    else
    {
      file.seek(pos);
    }
  }
  else
  {
    file = SPIFFS.open((char*)data + 6 + m, "w+");
  }
  if (!file || file.isDirectory()) {
    file.close();
    RPC_ERR(1, "Selected path is a directory");
  }
  int x = 0;

  file.write((uint8_t*)data + 6, m);
  file.close();
  return 0;

}


//rpc call that takes a 4 byte pointer and 2 byte len and a block of data then an fn, and writes that to a file at that pos
int rpcfsdelete(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{
  *rlen = 0;
  SPIFFS.remove((char *) data);
  return 0;

}


int rpcfslist(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{
  *rlen = 0;

  //Min entry index to start listing at
  unsigned int m = ((uint16_t *)(data ))[0];

  int count = -1;

  File d = SPIFFS.open((char *) data + 2);

  int dirnamelen=strlen((char *)data+2);

  //Get rid of the trailing slash that seems to mess things up
  if((((char *)data+1+dirnamelen)[0])== '/')
  {
    ((char *)data+1+dirnamelen)[0]= 0;
  }
  dbg(d.name());
  if (!d)
  {
    RPC_ERR(3, "Selected dir does not exist");

  }
  if (!d.isDirectory()) {
    RPC_ERR(1, "Selected obj is not a directory");
  }
  File f = d.openNextFile();

  while (f && (rlen[0] < 1024))
  {
    dbg(f.name());
    count += 1;

    if (count < m)
    {
      continue;
    }

    //Get rid of the prefix part
    strcpy((char*)rbuffer + 1, f.name()+dirnamelen+1);
    if (f.isDirectory())
    {
      *(char*) rbuffer = 2;
    }
    else
    {
      *(char*) rbuffer = 1;
    }

    //Plus 1 for typecode, plus 1 for null
    rlen[0] += strlen(f.name()-(dirnamelen+1)) + 2;
    rbuffer += strlen(f.name()-(dirnamelen+1)) + 2;
    f = d.openNextFile();

  }




  return 0;

}


/*Enable "full access" to the ESP32*/

void PavillionServer::enableRemoteAccess()
{
  addRPC(10, "readFile", rpcfsread);
  addRPC(11, "writeFile", rpcfswrite);
  addRPC(12, "writeInto", rpcfswriteinto);
  addRPC(13, "deleteFile", rpcfsdelete);
  addRPC(14, "listDir", rpcfslist);

  addRPC(20, "pinMode", rpcpinmode);
  addRPC(23, "analogRead", rpcanalogread);
  addRPC(21, "digitalRead", rpcdigitalread);


}


/*
   Given a function index, a name, and a function, add a new RPC function to the server.
   Servers can't be cleaned up, and functions can't be deleted.

*/
void PavillionServer::addRPC(uint16_t number, char *fname, int(*function)(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen))
{
  struct RpcFunction * n = new struct RpcFunction;
  n->function = function;
  n->index = number;
  n->fname = fname;
  n->next = 0;

  struct RpcFunction * s = &fzero;

  while (s->next)
  {
    s = s->next;
  }

  s -> next = n;
}


void PavillionServer::doRPC(uint16_t number, KnownClient *client, void * data, uint16_t datalen, uint64_t callid)
{


  //For convenience of accepting strings, the byte after the last char is a null.
  ((uint8_t*)data)[datalen] = 0;


  //Builtin test mode returns exactly the data you send it.
  if (number == 0)
  {
    uint8_t rbuffer[1501];
    unsigned int rlen;
    *((uint16_t *)(rbuffer + 8)) = 0;
    *(uint64_t *)rbuffer = callid;
    client->sendRawEncrypted(5, (uint8_t*)rbuffer, datalen + 10);
    return;
  }

  if (number == 1)
  {
    struct RpcFunction * s = &fzero;
    unsigned int rlen = 0;
    char rbuffer[256];
    while (s->next)
    {
      s = s->next;
      if (s->index == interpret(data, uint8_t))
      {
        char rbuffer[1501];
        unsigned int rlen;
        *((uint16_t *)(rbuffer + 8)) = s->function(data, datalen, client, rbuffer + 10, &rlen);
        *(uint64_t *)rbuffer = callid;
      }
    }

    rlen = strlen(s->fname);
    strcpy(rbuffer + 10, s->fname);

    *(uint64_t *)rbuffer = callid;
    *((uint16_t *)(rbuffer + 8))  = 0;
    client->sendRawEncrypted(5, (uint8_t*)rbuffer, rlen + 10);

  }

  struct RpcFunction * s = &fzero;

  while (s->next)
  { ;
    s = s->next;
    if (s->index == number)
    {
      char rbuffer[1501];
      unsigned int rlen;
      *((uint16_t *)(rbuffer + 8)) = s->function(data, datalen, client, rbuffer + 10, &rlen);
      *(uint64_t *)rbuffer = callid;
      client->sendRawEncrypted(5, (uint8_t*)rbuffer, rlen + 10);
      return;
    }
  }

 char rbuffer[30]= "0000000000NonexistentFunction";
  unsigned int rlen=19;
  *((uint16_t *)(rbuffer + 8)) = 2;
  *(uint64_t *)rbuffer = callid;
  client->sendRawEncrypted(5, (uint8_t*)rbuffer, rlen + 10);
}

