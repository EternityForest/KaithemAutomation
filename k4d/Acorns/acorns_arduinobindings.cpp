/*Copyright (c) 2018 Daniel Dunn(except noted parts)

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
SOFTWARE.*/

#include "acorns.h"
#include "Arduino.h"
#include "HardwareSerial.h"
#include <Wire.h>

HardwareSerial SecondSerPort(1);
/*

NMEAGPS * gps;
gps_fix * fix;

void loop()
{
  while (gps.available( gps_port )) {
    fix = gps.read();
    doSomeWork( fix );
  }
}

static SQInteger sqgps_construct(HSQUIRRELVM v)
{
  NMEAGPS * gps = new NMEAGPS;
  sq_newclass(v, 0);

  sq_pushstring(vm,"begin",-1);
  sq_newclosure(vm,sqserial_begin,0); //create a new function
  sq_newslot(vm,-3,SQFalse);
}
*/

static SQInteger sqwire_read(HSQUIRRELVM v)
{

  TwoWire *s = 0;


  SQInteger addr;
  SQInteger num;

  if (sq_getinteger(v, 2, &addr) == SQ_ERROR)
  {
    sq_throwerror(v, "Expected an integer between 0 and 255");
    return SQ_ERROR;
  }
  if (sq_getinteger(v, 3, &num) == SQ_ERROR)
  {
    sq_throwerror(v, "Expected an integer between 0 and 32");
    return SQ_ERROR;
  }

  sq_getinstanceup(v, 1, (void **)&s, 0);

  char b = Wire.requestFrom(addr, num);
  char x = 0;
  uint8_t *buf = (uint8_t *)sqstd_createblob(v, b);
  if (buf == 0)
  {
    return sq_throwerror(v, "Error allocating blob memory");
  }
  while (x < b)
  {
    buf[x] = Wire.read();
    x++;
  }
  return 1;
}


static SQInteger sqwire_begin(HSQUIRRELVM v)
{
  Wire.begin();
}


static SQInteger sqwire_write(HSQUIRRELVM v)
{

  TwoWire *s = 0;

  SQInteger addr;
  SQInteger num;

  if (sq_getinteger(v, 2, &addr) == SQ_ERROR)
  {
    sq_throwerror(v, "Expected an integer between 0 and 255");
    return SQ_ERROR;
  }

  sq_getinstanceup(v, 1, (void **)&s, 0);

  Wire.beginTransmission(addr);
  char x = 0;

  uint8_t *buf =0;
  sqstd_getblob(v, 3, (void **)&buf);
  if (buf == 0)
  {
    return sq_throwerror(v,"Second parameter must be a blob");
  }
  char b = sqstd_getblobsize(v, 3);
  if (b > 32)
  {
    return sq_throwerror(v, "Max of 32 bytes is allowed");
  }
  while (x < b)
  {
    Wire.write(buf[x]);
    x++;
  }
  char ret = Wire.endTransmission(true);
  if (ret == 2)
  {
    return sq_throwerror(v,"Address NACK. Does slave exist?");
  }
  if (ret == 3)
  {
    return sq_throwerror(v, "Data NACK. Is data valid?");
  }
  return 0;
}


static SQInteger sqserial_begin(HSQUIRRELVM v)
{

  HardwareSerial *s = 0;

  SQInteger baud = 9600;

  SQInteger rxpin = 0;
  SQInteger txpin = 0;
  SQInteger i = sq_gettop(v);

  if (i > 1)
  {
    sq_getinteger(v, 2, &baud);
  }

  if (i > 3)
  {
    sq_getinteger(v, 4, &rxpin);
  }
  if (i > 4)
  {
    sq_getinteger(v, 5, &txpin);
  }
  sq_getinstanceup(v, 1, (void **)&s, 0);

  //Just to be safe, use the config.
  #ifdef ESP32
  s->begin(baud, SERIAL_8N2, rxpin, txpin);
  #elif ESP8266
  s->begin(baud, SERIAL_8N2, SERIAL_FULL, txpin);
  #else
  #error No suppport for chip
  #endif
  return 0;
}

static SQInteger sqserial_write(HSQUIRRELVM v)
{

  HardwareSerial *s = 0;

  SQInteger b;
  SQInteger i = sq_gettop(v);

  if (i > 1)
  {
    if (sq_getinteger(v, 2, &b) == SQ_ERROR)
    {
      sq_throwerror(v, "Expected an integer between 0 and 255");
      return SQ_ERROR;
    }
  }
  else
  {
    sq_throwerror(v, "HardwareSerial.write takes exactly one parameter");
    return SQ_ERROR;
  }

  sq_getinstanceup(v, 1, (void **)&s, 0);

  //Just to be safe, use the config.
  s->write(b);
  return 0;
}

static SQInteger sqserial_read(HSQUIRRELVM v)
{

  HardwareSerial *s = 0;

  SQInteger b;

  sq_getinstanceup(v, 1, (void **)&s, 0);

  //Just to be safe, use the config.
  sq_pushinteger(v,s->read());
  return 0;
}

static SQInteger sqserial_available(HSQUIRRELVM v)
{

  HardwareSerial *s = 0;

  SQInteger b;

  sq_getinstanceup(v, 1, (void **)&s, 0);

  //Just to be safe, use the config.
  sq_pushinteger(v, s->available());
  return 0;
}

static SQInteger sqfreeheap(HSQUIRRELVM v)
{
  sq_pushinteger(v, ESP.getFreeHeap());
  return (1);
}

static SQInteger sqrestart(HSQUIRRELVM v)
{
  ESP.restart();
  return (0);
}



static SQInteger sqmillis(HSQUIRRELVM v)
{
  sq_pushinteger(v, millis());
  return (1);
}

//
static SQInteger sqmicros(HSQUIRRELVM v)
{
  sq_pushinteger(v, micros());
  return (1);
}

static SQInteger sqdelay(HSQUIRRELVM v)
{
  SQInteger i = sq_gettop(v);
  SQInteger d = 0;
  if (i == 2)
  {
    if (sq_getinteger(v, 2, &d) == SQ_ERROR)
    {
      sq_throwerror(v, "Integer is required");
      return SQ_ERROR;
    }
    else
    {
      //Delay for the given number of milliseconds
      GIL_UNLOCK;
      delay(d);
      GIL_LOCK;
      return 0;
    }
  }
  return SQ_ERROR;
}

static SQInteger sqanalogread(HSQUIRRELVM v)
{
  SQInteger i = sq_gettop(v);
  SQInteger d = 0;
  if (i == 2)
  {
    sq_getinteger(v, 2, &d);

    //Delay for the given number of milliseconds
    sq_pushinteger(v, analogRead(d));
    return 1;
  }
  return SQ_ERROR;
}

static SQInteger sqdigitalread(HSQUIRRELVM v)
{
  SQInteger i = sq_gettop(v);
  SQInteger d = 0;
  if (i == 2)
  {
    sq_getinteger(v, 2, &d);

    //Delay for the given number of milliseconds
    sq_pushinteger(v, digitalRead(d));
    return 1;
  }
  return SQ_ERROR;
}

static SQInteger sqdigitalwrite(HSQUIRRELVM v)
{
  SQInteger i = sq_gettop(v);
  SQInteger d = 0;
  SQInteger val = 0;
  if (i == 3)
  {
    sq_getinteger(v, 2, &d);
    sq_getinteger(v, 3, &val);
    digitalWrite(d, val);
    return 0;
  }
  return SQ_ERROR;
}

static SQInteger sqpinmode(HSQUIRRELVM v)
{
  SQInteger i = sq_gettop(v);
  SQInteger d = 0;
  SQInteger val = 0;
  if (i == 3)
  {
    sq_getinteger(v, 2, &d);
    sq_getinteger(v, 3, &val);
    pinMode(d, val);
    return 0;
  }
  return SQ_ERROR;
}

void _Acorns::addArduino(HSQUIRRELVM vm)
{

  SQInteger i = sq_gettop(vm);
  sq_newclass(vm, 0);

  //Make the Wire base class, add two functions
  sq_newclass(vm, 0);
  sq_pushstring(vm, "begin", -1);
  sq_newclosure(vm, sqwire_begin, 0); //create a new function
  sq_newslot(vm, -3, SQFalse);

  sq_pushstring(vm, "read", -1);
  sq_newclosure(vm, sqwire_read, 0); //create a new function
  sq_newslot(vm, -3, SQFalse);

  sq_pushstring(vm, "write", -1);
  sq_newclosure(vm, sqwire_write, 0); //create a new function
  sq_newslot(vm, -3, SQFalse);




  //Make the serial base class, add two functions
  sq_newclass(vm, 0);
  sq_pushstring(vm, "begin", -1);
  sq_newclosure(vm, sqserial_begin, 0); //create a new function
  sq_newslot(vm, -3, SQFalse);

  sq_pushstring(vm, "write", -1);
  sq_newclosure(vm, sqserial_write, 0); //create a new function
  sq_newslot(vm, -3, SQFalse);

  sq_pushstring(vm, "available", -1);
  sq_newclosure(vm, sqserial_available, 0); //create a new function
  sq_newslot(vm, -3, SQFalse);

  sq_pushstring(vm, "read", -1);
  sq_newclosure(vm, sqserial_read, 0); //create a new function
  sq_newslot(vm, -3, SQFalse);

  sq_pushroottable(vm);
  sq_pushstring(vm, "Serial", -1);
  sq_createinstance(vm, -3);
  sq_setinstanceup(vm, -1, &Serial);
  //add to root table under name serial, poopping name and value
  sq_newslot(vm, -3, 0);


  sq_pushstring(vm, "Serial1", -1);
  sq_createinstance(vm, -3);
  sq_setinstanceup(vm, -1, &SecondSerPort);
  //add to root table under name serial, poopping name and value
  sq_newslot(vm, -3, 0);

  //Pop the root table and the base class
  sq_pop(vm, 2);

  //Now we make the "system" namespace which is just a table of static members
  sq_pushroottable(vm);

  sq_pushstring(vm, "memfree", -1);
  sq_newclosure(vm, sqfreeheap, 0); //create a new function
  sq_newslot(vm, -3, SQFalse);

  sq_pushstring(vm, "restart", -1);
  sq_newclosure(vm, sqrestart, 0); //create a new function
  sq_newslot(vm, -3, SQFalse);

  sq_settop(vm, i);

  registerFunction(0, sqdelay, "delay");
  registerFunction(0, sqmicros, "micros");
  registerFunction(0, sqmillis, "millis");
  registerFunction(0, sqdigitalread, "digitalRead");
  registerFunction(0, sqanalogread, "analogRead");
  registerFunction(0, sqdigitalwrite, "digitalWrite");
  registerFunction(0, sqpinmode, "pinMode");
  setIntVariable(0, HIGH, "HIGH");
  setIntVariable(0, LOW, "LOW");
  setIntVariable(0, INPUT, "INPUT");
  setIntVariable(0, INPUT_PULLUP, "INPUT_PULLUP");
  setIntVariable(0, OUTPUT, "OUTPUT");
}