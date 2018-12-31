#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include "Arduino.h"
#include "k4d.h"

static unsigned char HexChar (char c)
{
    if ('0' <= c && c <= '9') return (unsigned char)(c - '0');
    if ('A' <= c && c <= 'F') return (unsigned char)(c - 'A' + 10);
    if ('a' <= c && c <= 'f') return (unsigned char)(c - 'a' + 10);
    return 0xFF;
}

static int HexToBin (const char* s, unsigned char * buff, int length)
{
    int result;
    if (!s || !buff || length <= 0) return -1;

    for (result = 0; *s; ++result)
    {
        unsigned char msn = HexChar(*s++);
        if (msn == 0xFF) return -1;
        unsigned char lsn = HexChar(*s++);
        if (lsn == 0xFF) return -1;
        unsigned char bin = (msn << 4) + lsn;

        if (length-- <= 0) return -1;
        *buff++ = bin;
    }
    return result;
}


//This buffer holds the main key that allows full access to the system.
static unsigned  char PSKBuf[32];


//Given a 16byte ID, return a pointer to the PSK, or None if the client doesn't exist.
// The PSK is always the same in this case for all clients,and it is pavillion.psk in the server config.
static uint8_t * PSKforClient(uint8_t * id)
{
  char hexbuf[66];

  Acorns.getConfig("pavillion.psk","",hexbuf, 65);
  if(strlen(hexbuf)==0)
  {
    return 0;
  }
  HexToBin(hexbuf, PSKBuf, 32);
  return PSKBuf;
}


//Takes a null term string that is just the name
static int rpc_newProgram(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{
  const char * name = (const char *)data;

  //TODO: race condition between check and action, probably not relevant in practice
  if(Acorns.isRunning(name)==0)
  {
    //Load the program with just only that comment line
    Acorns.loadProgram("//c", name);
  }
  else
  {
      Acorns.clearInput(name);
  }
  return 0;
}


//Takes a null term string that is just the name
static int rpc_forceClose(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{
  const char * name = (const char *)data;

  Acorns.closeProgram(name,true);
  return 0;
}


//Takes a 4 byte position 2 null term strings,one being the nameand the next being some code yout want to write into the program
//The position is required to make this call idempotent.
static int rpc_writeToInput(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{
  uint32_t position = ((uint32_t *)data)[0];
  data+= 4;
  const char * name = (const char *)data;
  const char * code = strchr((const char *)data,0)+1;


  //Load the program with just only that comment line
  Acorns.writeToInput(name, code, strlen(code),position);
  return 0;
}
//Takes 2 null term strings,one being the nameand the next being the program hash and returns 1 if a program
//By that id and hash is running
static int rpc_isRunning(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{
  const char * name = (const char *)data;
  const char * hash = strchr((const char *)data,0)+1;

  if(*hash==0)
  {
    hash=0;
  }
  //Load the program with just only that comment line
  *((uint8_t *)rbuffer)= Acorns.isRunning(name, hash);
  *rlen = 1;

  return 0;
}



static int rpc_loadInput(void * data, unsigned int datalen, KnownClient *client, void *rbuffer, unsigned int * rlen)
{
  const char * name = (const char *)data;

   //Write the null terminator
  Acorns.writeToInput(name, "\0", 1);
  //Load the program with just only that comment line
  Acorns.loadInputBuffer(name,true);
  return 0;
}



static void acornserr(loadedProgram * p, const char * c)
{
    K4D.server->broadcastMessage("k4derr",p->programID, (uint8_t*)c, strlen(c));
}
static void acornsprint(loadedProgram * p, const char * c)
{
    K4D.server->broadcastMessage("k4dprint",p->programID, (uint8_t*)c, strlen(c));
}





void _k4d::begin()
{

    server = new PavillionServer;
    //Setting up the Pavillion node.
    server->PSKforClient = PSKforClient;
    server->enableRemoteAccess();
    server->listen(12345);


    Acorns.errorfunc = acornserr;
    Acorns.printfunc = acornsprint;
    Acorns.begin();

    //These are the actual K4d calls  
    server->addRPC(4097, "newProgram", rpc_newProgram);
    server->addRPC(4098, "writeToProgramInput", rpc_writeToInput);
    server->addRPC(4099, "loadInput", rpc_loadInput);  
    server->addRPC(4100, "isRunning", rpc_isRunning);  
    server->addRPC(4105, "forceClose", rpc_forceClose);  

}

_k4d K4D;