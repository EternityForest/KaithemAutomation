
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
#include <Wire.h>

#include "pavillion.h"
#include <FS.h>

#ifdef ESP32
#include <SD.h>
#include <SPIFFS.h>
#endif

//Arduino doesn't give us a way to access the root dir, without
//Using esp32 posix only stuff. So we just select a mounted dir based on hardcoded names
fs::FS *getFS(String fn)
{
  if (fn.startsWith("/spiffs"))
  {
    return &SPIFFS;
  }
#ifdef ESP32
  if (fn.startsWith("/sd"))
  {
    return &SD;
  }
#endif

  return 0;
}

int rpcpinmode(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen)
{
  if (((uint8_t *)data)[1] == 0)
  {
    pinMode(((uint8_t *)data)[0], INPUT);
  }
  else if (((uint8_t *)data)[1] == 3)
  {
    pinMode(((uint8_t *)data)[0], INPUT_PULLUP);
  }
  else if (((uint8_t *)data)[1] == 139)
  {
    pinMode(((uint8_t *)data)[0], OUTPUT);
  }
  else
  {
    RPC_ERR(2, "Supported pinModes: 0, 3, 139");
  }

  *rlen = 0;
  return 0;
}

int rpcanalogread(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen)
{
  *rlen = 4;
  writeUnsignedNumber(rbuffer, 4, analogRead(((uint8_t *)data)[0]));
  return 0;
}

int rpcdigitalread(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen)
{
  *rlen = 1;
  ((uint8_t *)rbuffer)[0] = digitalRead(((uint8_t *)data)[0]);
  return 0;
}

//I2C
int rpcwiretransaction(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen)
{
  *rlen =0;

  uint8_t addr = readUnsignedNumber(data,2); data+=2;
  int flags = readUnsignedNumber(data, 1); data+=1;
  size_t toRead = readUnsignedNumber(data, 1); data+=1;
  if(datalen>32+4)
  {
        RPC_ERR(0, "Data too long");
  }
  if(datalen>4)
  {
    Wire.beginTransmission(addr);
    Wire.write((uint8_t *)data,datalen-4);
    Wire.endTransmission(true);
  }
  *rlen = 0;
  if(toRead)
  {
    if(Wire.requestFrom(addr,toRead,true)==toRead)
    {
        Wire.readBytes((char*)rbuffer,toRead);
        *rlen = toRead;
    }
  }

  writeUnsignedNumber(rbuffer, 4, analogRead(((uint8_t *)data)[0]));
  return 0;
}

#include "FS.h"
#ifdef ESP32
#include "SPIFFS.h"
#endif

//rpc call that takes a 4 byte pointer and 2 byte len and reads up to that many bytes from a file
int rpcfsread(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen)
{
  rlen[0] = 0;
  unsigned int pos = readUnsignedNumber(data, 4);
  unsigned int m = readUnsignedNumber(data + 4, 2);

  fs::FS *mountpoint = getFS((char *)data + 6);
  //Skip the first slash if any(Assume mountpoint name is at least 2 chars)
  //Then get the slash after that.
  char *fn = strchr((char *)data + 7, '/');

  if (mountpoint == 0)
  {
    RPC_ERR(3, "That device does not exist or is disconnected.");
  }
  data += 6;

  File file = mountpoint->open(fn, "r");
  if (!file)
  {
    file.close();
    RPC_ERR(1, "Selected path is a directory or could not be opened");
  }

#ifdef ESP32
  if (!file || file.isDirectory())
  {
  // if (mountpoint != &SPIFFS)
    {
      file.close();
      RPC_ERR(1, (String("Selected object ") + String(fn+1) + String(" is a directory")).c_str());
    }
  }
#endif
  int x = 0;

  //You're exactly at the end of the file. Return 0 bytes.
  if(pos == file.size())
  {
    *rlen = 0;
    return 0;
  }

  //Seek to 0 doesn't work?
  if (pos){
    //You tried to read past the end of the file
    if (file.seek(pos) == false)
    {
      file.close();
      RPC_ERR(1, (String("Failed to seek to position ") + String(pos)).c_str());
    }
  }

  if (m > 1024)
  {
    m = 1024;
  }

  x = file.readBytes((char *)rbuffer, m);
  if (x < 0)
  {
    file.close();
    RPC_ERR(1, "Error reading file, return value below zero.");
  }

  if (x > 1200)
  {
    file.close();
    RPC_ERR(1, "Error reading file");
  }
  rlen[0] = x;
  file.close();
  return 0;
}

//rpc call that takes a 4 byte pointer and 2 byte len and a block of data then an fn, and writes that to a file at that pos
int rpcfswrite(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen)
{
  *rlen = 0;
  unsigned int pos = readUnsignedNumber(data, 4);
  unsigned int m = readUnsignedNumber(data + 4, 2);
  data += 6;

  fs::FS *mountpoint = getFS((char *)data+m);

  if (mountpoint == 0)
  {
      RPC_ERR(3, (String("Nonexistant filesystem ") + String((char *)data+m)).c_str());
  }

  File file;
  //Skip the first slash if any(Assume mountpoint name is at least 2 chars)
  //Then get the slash after that.
  char *fn = strchr((char *)data + m+1, '/');

  file = mountpoint->open(fn, "w");

  if (!file)
  {
    file.close();
    RPC_ERR(3, (char *)data + m);
  }

#ifdef ESP32
  if (file.isDirectory())
  {
    file.close();
    //eVERYTHING AND NOTHING IS DIR ON SPIFFS!!!!
    if (mountpoint != &SPIFFS)
    {
      RPC_ERR(1, (String("Selected path ") + String(fn) + String("is a directory")).c_str());
    }
  }
#endif
  int x = 0;

  file.write((uint8_t *)data, m);
  file.close();
  return 0;
}

// rpc call that takes a 4 byte pointer and 2 byte len and a block of data then an fn, and writes that to a file at that pos
int rpcfswriteinto(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen)
{
  *rlen = 0;
  unsigned int pos = readUnsignedNumber(data, 4);
  unsigned int m = readUnsignedNumber(data + 4, 2);

  fs::FS *mountpoint = getFS((char *)data +m+ 6);
  //Skip the first slash if any(Assume mountpoint name is at least 2 chars)
  //Then get the slash after that.
  char *fn = strchr((char *)data + m + 7, '/');

  if (mountpoint == 0)
  {
      RPC_ERR(3, (String("Nonexistant filesystem ") + String((char *)data+m)).c_str());
  }
  data += 6;

  File file;
  if (mountpoint->exists(fn))
  {
    file = mountpoint->open(fn, "r+");
    if (file.size() <= pos)
    {
      file.close();
      file = mountpoint->open(fn, "a");
    }
    else
    {
      file.seek(pos);
    }
  }
  else
  {
    file = mountpoint->open(fn, "w+");
  }

  if (!file)
  {
    file.close();
    RPC_ERR(1, "Selected path is a directory or could not be opened");
  }

#ifdef ESP32
  if (!file || file.isDirectory())
  {
    file.close();
    //eVERYTHING AND NOTHING IS DIR ON SPIFFS!!!!
    if (mountpoint != &SPIFFS)
    {
      RPC_ERR(1, (String("Selected path ") + String(fn) + String("is a directory")).c_str());
    }
  }
#endif

  int x = 0;

  file.write((uint8_t *)data + 6, m);
  file.close();
  return 0;
}

//rpc call that takes a 4 byte pointer and 2 byte len and a block of data then an fn, and writes that to a file at that pos
int rpcfsdelete(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen)
{
  *rlen = 0;

  fs::FS *mountpoint = getFS((char *)data + 6);
  //Skip the first slash if any(Assume mountpoint name is at least 2 chars)
  //Then get the slash after that.
  char *fn = strchr((char *)data + 6, '/');

  if (mountpoint == 0)
  {
    RPC_ERR(3, "That device does not exist or is disconnected.");
  }

  mountpoint->remove(fn);
  return 0;
}

int rpcfslist(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen)
{
  *rlen = 0;

  //Min entry index to start listing at
  unsigned int m = readUnsignedNumber(data, 2);
  data += 2;

  if (strlen((char *)data) == 1)
  {
    //hardcoded response. Note that SD card might not exist.
    //TODO: Properly detect missing SD card
    if (((char *)data)[0] == '/')
    {
      strcpy((char *)rbuffer, "\x02spiffs\x02sd");
      rlen[0] = 10;
      return 0;
    }
  }

  //Skip the first slash if any(Assume mountpoint name is at least 2 chars)
  //Then get the slash after that.
  char *fn = strchr((char *)data + 1, '/');
  if (fn == 0)
  {
    RPC_ERR(3, "Impossible filename does not contain a root directory");
  }

  fs::FS *mountpoint = getFS((char *)data);
  if (mountpoint == 0)
  {
    RPC_ERR(3, "That device does not exist or is disconnected.");
  }

  int count = 0;
#ifdef ESP32
  File d = mountpoint->open(fn);
#else
  if (mountpoint->exists(fn) == false)
  {
    RPC_ERR(3, "Selected dir does not exist");
  }
  Dir d = mountpoint->openDir(fn);
#endif

  //Start from end if string
  int dirnamelen = strlen(fn);

  //Get rid of the trailing slash that seems to mess things up
  //While we're at it
  if (fn[dirnamelen - 1] == '/')
  {
    fn[dirnamelen - 1] = 0;
  }

#ifdef ESP32
  if (!d)
  {
    RPC_ERR(3, ("Selected dir " + String((char *)data + 2) + " does not exist").c_str());
  }

  if (!d.isDirectory())
  {
    RPC_ERR(1, "Selected obj is not a directory");
  }

  File f = d.openNextFile();
#else
  d.next();
  File f = d.openFile("r");
#endif

  String l = "";
  while (f && (rlen[0] < 1024))
  {
    if (l == f.name())
    {
      return 0;
    }
    l = f.name();
    if (count >= m)
    {
      strcpy((char *)rbuffer + 1, ((char *)f.name()) + 1);
//I don't think ESP8266 SPIFFS has true directories
#ifdef ESP32
      if (f.isDirectory())
#else
      if (0)
#endif
      {
        *(char *)rbuffer = 2;
      }
      else
      {
        *(char *)rbuffer = 1;
      }

      //Plus 1 for typecode, plus 1 for null
      rlen[0] += strlen(f.name() + 1) + 2;
      rbuffer += (strlen(f.name() + 1) + 2);
    }

#ifdef ESP32
    f = d.openNextFile();
#else
    d.next();
    f = d.openFile("r");
#endif

    count += 1;
  }
  return 0;
}

/*Enable "full access" to the ESP32*/

void PavillionServer::enableRemoteAccess()
{
  addRPC(10, "readFile", rpcfsread, false);
  addRPC(11, "writeFile", rpcfswrite,false);
  addRPC(12, "writeInto", rpcfswriteinto,false);
  addRPC(13, "deleteFile", rpcfsdelete,false);
  addRPC(14, "listDir", rpcfslist,false);

  addRPC(20, "pinMode", rpcpinmode,false);
  addRPC(23, "analogRead", rpcanalogread,false);
  addRPC(21, "digitalRead", rpcdigitalread,false);
  addRPC(25, "wireTransaction", rpcwiretransaction,false);

}

/*
   Given a function index, a name, and a function, add a new RPC function to the server.
   Servers can't be cleaned up, and functions can't be deleted. However they can be overridden.

   Calling theis function twice for the same number replaces the old one.
*/
void PavillionServer::addRPC(uint16_t number, char *fname, int (*function)(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen), bool usespavillion)
{
  struct RpcFunction *n = 0;
  struct RpcFunction *s = &fzero;

  while (s->next)
  {
    s = s->next;
  }

  //We found the last one, append
  if(s->next == 0)
  {
    n = new struct RpcFunction;
    s->next = n;
    n->next = 0;
  }
  //We found one with the same number. Overwrite
  else
  {
    n=s;
  }

  //Fill in the actual data
  n->function = function;
  n->index = number;
  n->fname = fname;
  n->usespavillion = usespavillion;
}

void PavillionServer::addRPC(uint16_t number, char *fname, int (*function)(void *data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int *rlen))
{
  addRPC(number,fname, function, true);
}

void PavillionServer::doRPC(uint16_t number, KnownClient *client, void *data, uint16_t datalen, uint64_t callid, bool allowPavillion)
{
  //For convenience of accepting strings, the byte after the last char is a null.
  ((uint8_t *)data)[datalen] = 0;
  unsigned int rlen = 0;
  char rbuffer[1501];

  //Builtin test mode returns exactly the data you send it.
  if (number == 0)
  {
    writeUnsignedNumber(rbuffer + 8, 2, 0);
    writeUnsignedNumber(rbuffer, 8, callid);
    memcpy(rbuffer + 10, data, datalen);
    dbg("echo RPC");
    client->sendRawEncrypted(5, (uint8_t *)rbuffer, datalen + 10);
    return;
  }

  if (number == 1)
  {
    dbg("function name requested");
    struct RpcFunction *s = &fzero;
    while (s->next)
    {
      s = s->next;
      if (s->index == readUnsignedNumber(data, 2))
      {
        rlen = strlen(s->fname);
        strcpy(rbuffer + 10, s->fname);

        writeUnsignedNumber(rbuffer + 8, 2, 0);
        writeUnsignedNumber(rbuffer, 8, callid);
        client->sendRawEncrypted(5, (uint8_t *)rbuffer, rlen + 10);
        return;
      }
    }
  }

  struct RpcFunction *s = &fzero;
  dbg("doing rpc");
  dbg(number);
  while (s->next)
  {
    s = s->next;
    if (s->index == number)
    {
      //Completely ignore RPC calls that can cause a broadcast,
      //if we're already inside a broadcast loop.
      if((!allowPavillion) && (s->usespavillion==true))
      {
        return;
      }
      writeUnsignedNumber(rbuffer + 8, 2, s->function(data, datalen, client, rbuffer + 10, &rlen));
      writeUnsignedNumber(rbuffer, 8, callid);

      dbg(F("Sending RPC response"));
      client->sendRawEncrypted(5, (uint8_t *)rbuffer, rlen + 10);
      return;
    }
  }
  dbg(F("No RPC hanfler for that call"));
  char *rbuffer2 = (char *)malloc(32);
  memcpy(rbuffer2, "0000000000NonexistentFunction", 29);
  rlen = 19;
  *((uint16_t *)(rbuffer2 + 8)) = 2;
  *(uint64_t *)rbuffer2 = callid;
  client->sendRawEncrypted(5, (uint8_t *)rbuffer2, rlen + 10);
  free(rbuffer2);
}
