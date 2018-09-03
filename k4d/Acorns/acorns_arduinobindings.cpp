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


static SQInteger sqserial_begin(HSQUIRRELVM v)
{

  HardwareSerial * s = 0;
 
  SQInteger baud =9600;

  SQInteger rxpin = 0;
  SQInteger txpin = 0;
  SQInteger i = sq_gettop(v);

  if(i>1)
  {
    sq_getinteger(v,2, &baud);
  }


  if(i>3)
  {
    sq_getinteger(v,4, &rxpin);
  } 
  if(i>4)
  {
    sq_getinteger(v,5, &txpin);
  }
  sq_getinstanceup(v, 1,(void **)&s,0);

  //Just to be safe, use the config.
  s->begin(baud,SERIAL_8N2, rxpin, txpin);
  return 0;
}

static SQInteger sqserial_write(HSQUIRRELVM v)
{

  HardwareSerial * s = 0;
 
  SQInteger b;
  SQInteger i = sq_gettop(v);

  if(i>1)
  {
    if(sq_getinteger(v,2, &b)==SQ_ERROR)
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

  sq_getinstanceup(v, 1,(void **)&s,0);

  //Just to be safe, use the config.
  s->write(b);
  return 0;
}




static SQInteger sqfreeheap(HSQUIRRELVM v)
{
  sq_pushinteger(v, ESP.getFreeHeap());
  return(1);
}

static SQInteger sqrestart(HSQUIRRELVM v)
{
  ESP.restart();
  return(0);
}


static SQInteger sqmillis(HSQUIRRELVM v)
{
  sq_pushinteger(v, millis());
  return(1);
}

//
static SQInteger sqmicros(HSQUIRRELVM v)
{
  sq_pushinteger(v, micros());
  return(1);
}

static SQInteger sqdelay(HSQUIRRELVM v)
{
 SQInteger i = sq_gettop(v);
  SQInteger d =0;
  if(i==2)
  {
    if(sq_getinteger(v, 2, &d)==SQ_ERROR)
   {
      sq_throwerror(v,"Integer is required");
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
  SQInteger d =0;
  if(i==2)
  {
    sq_getinteger(v, 2, &d);
   
    //Delay for the given number of milliseconds
    sq_pushinteger(v,  analogRead(d));
    return 1;
  }
  return SQ_ERROR;
}

static SQInteger sqdigitalread(HSQUIRRELVM v)
{
 SQInteger i = sq_gettop(v);
  SQInteger d =0;
  if(i==2)
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
  SQInteger d =0;
  SQInteger val=0;
  if(i==3)
  {
    sq_getinteger(v, 2, &d);
    sq_getinteger(v, 3, &val);
    digitalWrite(d,val);
    return 0;
  }
  return SQ_ERROR;
}

static SQInteger sqpinmode(HSQUIRRELVM v)
{
 SQInteger i = sq_gettop(v);
  SQInteger d =0;
  SQInteger val=0;
  if(i==3)
  {
    sq_getinteger(v, 2, &d);
    sq_getinteger(v, 3, &val);
    pinMode(d,val);
    return 0;
  }
  return SQ_ERROR;
}


void _Acorns::addArduino(HSQUIRRELVM vm)
{

  
  SQInteger i = sq_gettop(vm);
  sq_newclass(vm,0);



  //Make the serial base class, add two functions
  sq_newclass(vm, 0);
  sq_pushstring(vm,"begin",-1);
  sq_newclosure(vm,sqserial_begin,0); //create a new function
  sq_newslot(vm,-3,SQFalse);

  sq_pushstring(vm,"write",-1);
  sq_newclosure(vm,sqserial_write,0); //create a new function
  sq_newslot(vm,-3,SQFalse);


  sq_pushroottable(vm);
  sq_pushstring(vm,"Serial", -1);
  sq_createinstance(vm , -3);
  sq_setinstanceup(vm, -1, &Serial);
  //add to root table under name serial, poopping name and value
  sq_newslot(vm, -3, 0);

  //Pop the root table and the base class
  sq_pop(vm, 2);


  //Now we make the "system" namespace which is just a table of static members
  sq_pushroottable(vm);

  sq_pushstring(vm,"memfree",-1);
  sq_newclosure(vm,sqfreeheap,0); //create a new function
  sq_newslot(vm,-3,SQFalse);

  sq_pushstring(vm,"restart",-1);
  sq_newclosure(vm,sqrestart,0); //create a new function
  sq_newslot(vm,-3,SQFalse);

  sq_settop(vm, i);

  registerFunction(0, sqdelay,"delay");
  registerFunction(0, sqmicros,"micros");
  registerFunction(0, sqmillis, "millis");
  registerFunction(0, sqdigitalread, "digitalRead");
  registerFunction(0, sqanalogread, "analogRead");
  registerFunction(0, sqdigitalwrite, "digitalWrite");
  registerFunction(0, sqpinmode,"pinMode");
  setIntVariable(0,HIGH,"HIGH");
  setIntVariable(0,LOW,"LOW");
  setIntVariable(0,INPUT,"INPUT");
  setIntVariable(0,INPUT_PULLUP,"INPUT_PULLUP");
  setIntVariable(0,OUTPUT,"OUTPUT");
}