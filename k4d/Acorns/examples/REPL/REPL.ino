/*
  Squirrel REPL! Load this on an ESP32, and type some squirrel code in the serial monitor!
*/
#include "acorns.h"



SQInteger make_callback(HSQUIRRELVM v)
{

  //This is how you accept a callback. 2 is the callable stack index,
  //And it pushes the callback subscription object to the stack
  CallbackData * cd = Acorns.acceptCallback(v, 2, 0);

  
  //This is how you call it. Normally you would do this in a makeRequest function.
  //But it's pretty much like any other call. This happens in the GIL,
  //but an unregister could have happened while the callback was "inflight"
  //In the queue, so we always have to check if it still has a callable.
  if(cd->callable)
  {
    sq_pushobject(v, *cd->callable);
    sq_pushroottable(v);
    sq_call(v, 1, false, true);
  }

  
  //How you signal that you're done with it.
  deref_cb(cd);
  return 1;
}



void setup() {
  Serial.begin(115200);
  Serial.println("**starting up**");
  Acorns.begin();

  Acorns.registerFunction(0, make_callback, "callit");
}

// the loop function runs over and over again forever
void loop() {

  if (Serial.available())
  {
    Acorns.replChar(Serial.read());
  }
}
