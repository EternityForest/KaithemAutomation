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

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "Arduino.h"
#include "acorns.h"
#include <WiFi.h>
#include <dirent.h>
#include "minIni.h"
#include <ESPmDNS.h>








/************************************************************************************************************/
//Data Structures, forward declarations

  
  

//Represents a request to the thread pool to execute the given function
//with the loadedProgram and the arg as its params.
struct Request
{
  void (*f)(loadedProgram *, void *);
  //Pointer tp the target of the request
  struct loadedProgram * program;
  //Object that represents what the interpreter should do.
  //If it === interpreter, it means run loaded code
  void * arg;
};




///declarations

static void deref_prog(loadedProgram *);
static struct loadedProgram* _programForId(const char * id);

/***************************************************/
//The GIL

//The global interpreter lock. Almost any messing
//with of interpreters uses this.
SemaphoreHandle_t _acorns_gil_lock;


//This gets called every 250 instructions in long running squirrel programs to other threads can do things.
void sq_threadyield()
{
  GIL_UNLOCK;
  GIL_LOCK;
}

/*********************************************************************/
//Random number generation

static uint64_t entropy=88172645463325252LL;
static uint64_t rng_key = 787987897897LL;


/*
static unsigned long long doRandom(){
  //Every time we call this function, mix in some randomness. We could use the ESP prng,
  //But that's less portable, and we want 64 bits, and I'm not sure what performance is like there.
  //Instead we seed from that occasionally, and continually reseed from micros().
  entropy += micros();
  entropy^=(entropy<<13); entropy^=(entropy>>7); return (entropy^=(entropy<<17));
}
*/

//This function was modified for Acorns.
// *Really* minimal PCG32 code / (c) 2014 M.E. O'Neill / pcg-random.org
// Licensed under Apache License 2.0 (NO WARRANTY, etc. see website)
static uint32_t doRandom()
{
    //This is the modified line, for continual reseeding.
    entropy+=micros();

    uint64_t oldstate = entropy;
    // Advance internal state
    entropy = oldstate * 6364136223846793005ULL + (rng_key|1);
    // Calculate output function (XSH RR), uses old state for max ILP
    uint32_t xorshifted = ((oldstate >> 18u) ^ oldstate) >> 27u;
    uint32_t rot = oldstate >> 59u;
    return (xorshifted >> rot) | (xorshifted << ((-rot) & 31));
}



static SQInteger sqrandom(HSQUIRRELVM v)
{
  SQInteger i = sq_gettop(v);
  SQInteger mn =0;
  SQInteger mx=0;
  if(i==2)
  {
    //Wrong and bad way to generate random numbers. There's a tiny bias if the range
    //isn't a divisor of 2**64. But in practice, 2**64 is big and
    //this isn't for security purposes anyway.
    sq_getinteger(v, 2, &mx);
    sq_pushinteger(v, doRandom()%mx);
    return 1;
  }
 if(i==3)
  {
    sq_getinteger(v, 2, &mn);
    sq_getinteger(v, 3, &mx);
    sq_pushinteger(v,(doRandom()%mx) +mn);
    return 1;
  }

  //Wrong number of params
  return SQ_ERROR;
}


/***********************************************************************/
//Directory listing

static HSQOBJECT DirEntryObj;



static SQInteger sqdirectoryiterator(HSQUIRRELVM v)
{

  //Points to the userdata, but that userdata is actually a dir pointer
  DIR ** d;
  const char * dirname =0;

  if(sq_getstring(v, 2, &dirname) == SQ_ERROR)
  {
    sq_throwerror(v,"dir requires one string parameter.");
    return SQ_ERROR;
  }

  //The packed data has the dir name in it after the dir pointer
  sq_newuserdata(v, sizeof(DIR *));
  sq_getuserdata(v, -1,(void**)&d, 0);
  sq_pushobject(v,DirEntryObj);
  sq_setdelegate(v,-2);

  *d = opendir(dirname);

  if(*d==0)
  {
        return sq_throwerror(v,"Could not open directory");
  }
  return 1;
}


//Get is a passthrough
static SQInteger sqdirectoryiterator_get(HSQUIRRELVM v)
{
   return 1;
}

static SQInteger sqdirectoryiterator_next(HSQUIRRELVM v)
{
  DIR ** d;
  struct dirent * de;

  char buffer[258];
  buffer[0]= '/';

  if(sq_getuserdata(v, 1,(void**)&d, 0)==SQ_ERROR)
  {
    return SQ_ERROR;
  }

  if(*d==0)
  {
    return sq_throwerror(v, "This directory object is invalid or has been closed");
  }
  de=readdir(*d);



  if(de)
  {
    sq_pushstring(v,de->d_name, -1);
  }
  else
  {
    sq_pushnull(v);
    closedir(*d);
  }
  return 1;
}

static SQInteger dir_release_hook(SQUserPointer p,SQInteger size)
{
  if(*((DIR**)p)==0)
  {
    return 0;
  }
  closedir(*((DIR**)(p)));
  *((DIR**)(p)) = 0;
}


/************************************************************************/
//Quotes system

 const char  * acorn_Quoteslist[] = {
    "\"The men waited some time at the outpost.\"",
    "\"This road is longer for some than others.\"",
    "\"He carefully packed his travelsack before setting out.\"",
    "\"His staff had been with him on many adventures.\"",
    "\"From the top of the hill, he could see for miles.\"",
    "\"She knew better than the others why the river was dry.\"",
    "\"Only the fireflies lit the path as they made their way through the dark forest.\"",
    "\"The treasure they sought had been buried years ago.\"",
    "\"The stone glowed faintly when they passed by the door.\"",
    "\"The mountain rose before them at the end of the path.\"",
    "\"Her mother had warned her about this road.\"",
    "\"The Caravansarai was still miles ahead.\"",
    "\"His cloak was well-worn and had many small pockets\"",
    "\"Roads go ever ever on,\nOver rock and under tree,\nBy caves where never sun has shone,\nBy streams that never find the sea;\nOver snow by winter sown,\nAnd through the merry flowers of June,\nOver grass and over stone,\nAnd under mountains in the moon.\"\n-- J. R. R. Tolkien ",
    "\"The runes read 'I serve but the good,\n        of life and liberty'\"\n    -Leslie Fish, \"The Arizona Sword\"",
    0
};

static int numQuotes()
{
    int i =0;
  
    while(acorn_Quoteslist[i])
    {
        i++;
    }
  return(i);

}

static const char * acorn_getQuote()
{
    return acorn_Quoteslist[(doRandom()%numQuotes())];
}

static SQInteger sqlorem(HSQUIRRELVM v)
{

  sq_pushstring(v, acorn_getQuote(),-1);
  return 1;
}

/*************************************************************************/
//Misc Arduino

/*
//Warning: this uses undocumented internals of the arduino handle

static SQInteger squartread(HSQUIRRELVM v)
{

   SQInteger ticks = 


    uart_t * uart = &_uart_bus_array[n]
    if(uart == NULL || uart->queue == NULL) {
        return 0;
    }
    uint8_t c;
    if(xQueueReceive(uart->queue, &c, portMAX_DELAY)) {
        return c;
    }
    return 0;
}*/



//This is meant to be part of a squirrel class


/*************************************************************************************/
//Module system

//This is our modules table. It contains weak references to every module that is loaded.
//This means a module can dissapear if all references to it go away!!!
//Beware of bugs!
static HSQOBJECT modulesTable;



//One of the ways that imports are handled, by just letting the user deal with it.
//This function must place the new imported module onto the stack.

//Return 0 if you can't handle the request, 1 if you can, SQ_ERROR for an error
//error.

//This is weak, so the user can override it rather easily.
SQRESULT  __attribute__((weak)) sq_userImportFunction(HSQUIRRELVM v, const char * c, char len) 
{
  return 0;
}


//Our builtin modules available for import.
//TODO: move into it's own library
SQRESULT sq_builtinImportFunction(HSQUIRRELVM v, const char * c, char len);


SQRESULT sq_builtinImportFunction(HSQUIRRELVM v, const char * c, char len)
{
  return (0);
}


static SQInteger sqimport(HSQUIRRELVM v)
{

 SQInteger s = 0;
 SQInteger i =sq_gettop(v);

  
  const SQChar * mname;
  if(i==2)
  {
    if (sq_getstring(v, 2, &mname)==SQ_ERROR)
    {
      sq_throwerror(v, "Name must be a string");
      return SQ_ERROR;
    }

    s=sq_getsize(v,2);
    

    sq_pushobject(v, modulesTable);
    sq_pushstring(v, mname, s);
    i = sq_gettop(v);
    //We have found it in the table of things that are already loaded.
    if (SQ_SUCCEEDED(sq_get(v,-2)))
    {
        return 1;
    }


    //This user import function is expected to put the module we are trying to
    //import onto the stack.
    if(sq_builtinImportFunction(v, mname, s)==1)
    {

      HSQOBJECT o;
      sq_resetobject(&o);

      //Set the object as a member of the module table.
      //return the object itself
      sq_getstackobj(v,-1, &o);
      sq_pushobject(v,modulesTable);
      sq_pushstring(v, mname, s);
      sq_pushobject(v, o);
      sq_newslot(v, -3,SQFalse);

      sq_pushobject(v, o);
      return 1;
    }

    //This user import function is expected to put the module we are trying to
    //import onto the stack.
    if(sq_userImportFunction(v, mname, s)==1)
    {

      HSQOBJECT o;
      sq_resetobject(&o);

      //Set the object as a member of the module table.
      //return the object itself
      sq_getstackobj(v,-1, &o);
      sq_pushobject(v,modulesTable);
      sq_pushstring(v, mname, s);
      sq_pushobject(v, o);
      sq_newslot(v, -3,SQFalse);

      sq_pushobject(v, o);
      return 1;
    }

  sq_throwerror(v, "No import handler found");
  return SQ_ERROR;

  }
  else
  {
    sq_throwerror(v, "import takes exactly one parameter");
    return SQ_ERROR;
  }

}




/**************************************************************************************/
//Free/busy functions

//Mark a program as busy by incrementing the busy reference count of it and all parents
static void _setbusy(struct loadedProgram * p)
{
  while (p)
  {
    p->busy += 1;
    p = p->parent;
  }

}

//Mark a program as busy by decrementing the reference count
static void _setfree(struct loadedProgram * p)
{
  while (p)
  {
    p->busy -= 1;
    p = p->parent;
  }
}





/*******************************************************************/
//Thread pool stuff


//This is the thread pool
static TaskHandle_t sqTasks[ACORNS_THREADS];


//The queue going into the thread pool
static QueueHandle_t request_queue;



//Create and send a request to the thread pool
static void _makeRequest(loadedProgram * program, void (*f)(loadedProgram *, void *), void * arg)
{
  struct Request r;

  //Only call under gil because of this.
  //The fact that it is in the queue counts as a reference, and it's up to the thread pool
  //thread to deref it.
  program->refcount++;


  r.program = program;
  r.f = f;
  r.arg = arg;
  xQueueSend(request_queue, &r, portMAX_DELAY);
}

void _Acorns::makeRequest(const char * id, void (*f)(loadedProgram *, void *), void * arg)
{
  GIL_LOCK;
  loadedProgram * program = _programForId(id);
  if(program==0)
  {
    GIL_UNLOCK;
    return;
  }
  _makeRequest(program, f, arg);
  GIL_UNLOCK;

}


//The loop thar threads in the thread pool actually run
static void InterpreterTask(void *)
{
  struct Request rq;
  struct loadedProgram * ud;

  while (1)
  {
    xQueueReceive(request_queue, &rq, portMAX_DELAY);

    GIL_LOCK;


    while (rq.program->busy)
    {
      GIL_UNLOCK;
      vTaskDelay(10);
      GIL_LOCK;

      //If someone stopped the program while we were waiting
      if (rq.program->vm == 0)
      {
        goto fexit;
      }
    }

    _setbusy(rq.program);
    rq.f(rq.program, rq.arg);
    _setfree(rq.program);

fexit:
    deref_prog(rq.program);
    GIL_UNLOCK;
  }
}


/**********************************************************************************************/
//Callback stuff


void deref_cb(CallbackData * p)
{
  p->refcount--;

  //If either reference is done with it,
  //The callback isn't happening, cleanup right away
  if(p->cleanup)
    {
      p->cleanup(p->prog, p->userpointer);
    }
  p->cleanup = 0;


  if(p->callable)
  {
    if(p->prog)
    {
      sq_release(p->prog->vm, p->callable);
    }
    //Setting the callable to 0 is the flag not
    //To try to call this callback anymore
    p->callable=0;
  }

  //Deal with the linked list entry in the program
  CallbackData * x = p->prog->callbackRecievers;
  //Just delete if there's no list
  if (p->prog->callbackRecievers)
  {
    p->prog->callbackRecievers =0;
  }


  //There's callbacks, but the first one isn't this
  else if (x)
  {
    CallbackData * last =x;
    while(x)
    {
      //If we find it, link the one before to the one after
      if(x==p)
      {
        if(x->next)
        {
        last->next = x->next;
        }
        else
        {
          last->next=0;
        }
      }
      last = x;
    }
  }
  
  if(p->refcount==0)
  {
   free(p);
  }
}

static SQInteger cb_release_hook(SQUserPointer p,SQInteger size)
{
  deref_cb(*((CallbackData **)p));
}

//Gets the callable at stack index idx, and return a CallbackData you can use to call it.
//Pushes an opaque subscription object to the stack. The callback is canceled if that ever gets 
//garbage collected
struct CallbackData* _Acorns::acceptCallback(HSQUIRRELVM vm, SQInteger idx,void (*cleanup)(struct loadedProgram *, void *))
{
  HSQOBJECT * callable = (HSQOBJECT * )malloc(sizeof(HSQOBJECT));
  sq_resetobject(callable);

  SQObjectType t = sq_gettype(vm, idx);
  if((t!=OT_CLOSURE)&&(t!=OT_NATIVECLOSURE)&&(t!=OT_INSTANCE)&&(t!=OT_USERDATA))
  {
    sq_throwerror(vm, "Supplied object does not appear to be callable.");
  }
  sq_getstackobj(vm,idx,callable);


  //This callback data is a ref to the callable
  sq_addref(vm, callable);

  CallbackData * d = (CallbackData*) malloc(sizeof(CallbackData));

  d->callable = callable;
  d->cleanup =cleanup;

  struct loadedProgram * prg = ((loadedProgram *)sq_getforeignptr(vm));
  Serial.println((int)prg);
  //One for the user side, one for the internal side that actually recieves the data.
  d->refcount = 2;

  d->prog = prg;

  if(prg->callbackRecievers ==0)
  {
    prg->callbackRecievers = d;
  }

  else
  {
    CallbackData * p = prg->callbackRecievers;

    while(p)
    {
      p=p->next;
    }
    p->next = d;
  }
  
  CallbackData ** x=0;
  sq_newuserdata(vm,sizeof(void *));
  sq_getuserdata(vm,-1, (SQUserPointer *)&x, 0);
  sq_setreleasehook(vm, -1, cb_release_hook);
  *x = d;


  return d;
}



//**********************************************************************************8
//program management

static struct loadedProgram* rootInterpreter = 0;

//This is our "program table"
static struct loadedProgram * loadedPrograms[ACORNS_MAXPROGRAMS];



//Given a string program ID, return the loadedProgram object
//If it's not loaded.
static struct loadedProgram* _programForId(const char * id)
{
  if (id == 0)
  {
    if (rootInterpreter)
    {
      return rootInterpreter;
    }
    else
    {
      return 0;
    }
  }
  for (char i = 0; i < ACORNS_MAXPROGRAMS; i++)
  {
    if (loadedPrograms[i])
    {
      if (strcmp(loadedPrograms[i]->programID, id) == 0)
      {
        return loadedPrograms[i];
      }
    }
  }
  return 0;
}



//Only call under gil
static void deref_prog(loadedProgram * p)
{
  p->refcount --;
  if (p->refcount == 0)
  {
    free(p);
  }
}


void _Acorns::clearInput(const char * id)
{
 GIL_LOCK;
  loadedProgram * p = _programForId(id);
  if (p==0)
  {
    GIL_UNLOCK;
    return;
  }
  if(p->inputBuffer)
  {
    free(p->inputBuffer);
    p->inputBuffer = 0;
    p->inputBufferLen = 0;
  }

  GIL_UNLOCK;
}

void _Acorns::writeToInput(const char * id, const char * data, int len, long position)
{
  GIL_LOCK;
  loadedProgram * p = _programForId(id);
  if (p==0)
  {
    GIL_UNLOCK;
    return;
  }

  if (len == -1)
  {
    len = strlen(data);
  }

  if(p->inputBuffer ==0)
  {
    p->inputBuffer = (char *)malloc(len+2);
    p->inputBufferLen = 0;
  }
  else
  {
    //TODO: this is a memory leak if realloc ever fails
    if((p->inputBuffer = (char *)realloc(p->inputBuffer, p->inputBufferLen+len))==0)
    {
      GIL_UNLOCK;
      return;
    }
  }

  memcpy(p->inputBuffer+(p->inputBufferLen), data, len);
  p->inputBufferLen += len;

  GIL_UNLOCK;
}


///Position is mostly there to allow for idempotent writes. Set to -1 to append to the end.
///But it will fill with garbage if you leave gaps
void _Acorns::writeToInput(const char * id, const char * data, int len, long position)
{
  GIL_LOCK;
  loadedProgram * p = _programForId(id);
  if (p==0)
  {
    GIL_UNLOCK;
    return;
  }

  if (len == -1)
  {
    len = strlen(data);
  }

  if(position==-1)
  {
    position=p->inputBufferLen;
  }

  //How ,uch extra past the end to malloc
  long needed = len+position-1;
  needed-= p->inputBufferLen

  if(p->inputBuffer ==0)
  {
    p->inputBuffer = (char *)malloc(len+2);
    p->inputBufferLen = 0;
  }
  else
  {
    //TODO: this is a memory leak if realloc ever fails
    if((p->inputBuffer = (char *)realloc(p->inputBuffer, needed)==0)
    {
      GIL_UNLOCK;
      return;
    }
  }

  memcpy(p->inputBuffer+position, data, len);
  p->inputBufferLen += len;

  GIL_UNLOCK;
}




static int _closeProgram(const char * id, bool freeInput);

//Function that the thread pool runs to run whatever program is on the top of an interpreter's stack
static void runLoaded(loadedProgram * p, void * d)
{
  sq_pushroottable(p->vm);
  if(sq_call(p->vm, 1, SQFalse, SQTrue) == SQ_ERROR)
  {
    //If the flag saying we should do so is set, close the program on failure.
    if(d==(void *)1)
    {
      _closeProgram(p->programID, true);
      return;
    }
  }
  //Pop the closure itself.
  sq_pop(p->vm, 1);
}



static void _runInputBuffer(loadedProgram * p, void *d)
{

    //Adding the null terminator
    p->inputBuffer[p->inputBufferLen]=0;
    if (SQ_SUCCEEDED(sq_compilebuffer(p->vm, p->inputBuffer, p->inputBufferLen+1, _SC("InputBuffer"), SQTrue)))
      {
        runLoaded(p, 0);
        free(p->inputBuffer);
        p->inputBuffer = 0;
        p->inputBufferLen = 0;
      }
      else
      {       
        Serial.println("Failed to compile code");
        return;
      }

    runLoaded(p, 0);
    free(p->inputBuffer);
    p->inputBuffer = 0;
    p->inputBufferLen = 0;
}

void _Acorns::runInputBuffer(const char * id)
{
  makeRequest(id, _runInputBuffer,0);
}



//Close a running program, waiting till all children are no longer busy.
static int _closeProgram(const char * id, bool freeInput)
{
  entropy += esp_random();
  rng_key += esp_random();
  doRandom();
  
  loadedProgram * old = _programForId(id);
  //Check if programs are the same

  if (old)
  {
 
    ///Something can be "busy" without holding the lock if it yields.
    while (old->busy)
    {
      GIL_UNLOCK;
      delay(2500);
      GIL_LOCK;
    }

    if(old->inputBuffer)
    {
      if(freeInput)
      {
        free(old->inputBuffer);
      }
    }
    //Close the VM and deref the task handle now that the VM is no longer busy.
    //The way we close the VM is to get rid of references to its thread object.
    if(old->vm)
    {
      sq_release(old->vm, &old->threadObj);
      old->vm = 0;
    }
    deref_prog(old);

  }
}


//Get a running program to stop whatever it's doing, but don't actually
//Remove it's process table entry.
static void _forceclose(const char * id)
{
    loadedProgram * old = _programForId(id);
    if(old==0)
    {
      return;
    }
    sq_request_forceclose(old->vm);
}

int _Acorns::closeProgram(const char * id)
{
  GIL_LOCK;
  _closeProgram(id,true);
  GIL_UNLOCK;
}

int _Acorns::closeProgram(const char * id, char force)
{
  GIL_LOCK;
  if(force)
  {
    _forceclose(id);
  }
  _closeProgram(id,true);
  GIL_UNLOCK;
}


//Sq function to do an unclean stop of a running program.
static SQInteger sqcloseProgram(HSQUIRRELVM v)
{
  const char * id;
  char id2[32];
  int len;
  sq_getstring(v,2, &id);

  if (sq_getsize(v,2)>31)
  {
    return SQ_ERROR;
  }

  memcpy(id2, id,sq_getsize(v, 2));
  id2[sq_getsize(v,2)] = 0;

  _forceclose(id2);
  _closeProgram(id2,true);

  return 0;
}


//Load a new program from source code with the given ID, replacing any with the same ID if the
//first 30 bytes are different. The new program will have its own global scope that an inner scope of the root interpreter's.
//You will be able to use getdelegate to get at the root table directly.
static int _loadProgram(const char * code, const char * id)
{

  //Program load times as another entropy
  //Source
  entropy += esp_random();
  rng_key += esp_random();

 
  void * inputBufToFree = 0;
  //Pointer to pointer. So we can free the mem, then set pointer to 0
  void ** inputBufToFreep = 0;

  
  struct loadedProgram * old = _programForId(id);
  //Check if programs are the same
  //passing a null pointer tells it to use the input buffer
  if (code == 0)
  {
    if(old)
    {
      if(old->inputBuffer)
      {
        code = old->inputBuffer;
      }
      else{
         code = "//comment";
      }
    }
    else
    {
    code = "//comment";
    }
  }

  if (old)
  {
    inputBufToFree = (void *)(old->inputBuffer);
    inputBufToFreep = (void **)(&old->inputBuffer);

    //Check if the versions are the same
    if (memcmp(old->hash, code, PROG_HASH_LEN) == 0)
    {
      return 0;
    }


    ///Something can be "busy" without holding the lock if it yields.
    while (old->busy)
    {
      GIL_UNLOCK;
      delay(2500);
      GIL_LOCK;
    }


    //We told it not to close the input buffer. We have to do that ourself.
    _closeProgram(id, false);

  }

 

  //Find a free interpreter slot
  for (char i = 0; i < ACORNS_MAXPROGRAMS; i++)
  {
    if (loadedPrograms[i] == 0)
    {

      //Note that the old struct is still out there in heap until all the refs are gone
      loadedPrograms[i] = (struct loadedProgram *)malloc(sizeof(struct loadedProgram));
      loadedPrograms[i]->parent = rootInterpreter;
      loadedPrograms[i]->refcount = 1;
      loadedPrograms[i]-> callbackRecievers =0;
      loadedPrograms[i]->busy = 0;
      loadedPrograms[i]->inputBuffer =0;
      loadedPrograms[i]->inputBufferLen =0;

      //This is so the dereference function can free the slot in the table
      //By itself
      loadedPrograms[i]->slot = &loadedPrograms[i];

      HSQUIRRELVM vm;
      loadedPrograms[i]->vm = sq_newthread(rootInterpreter->vm, 1024);
      vm = loadedPrograms[i]->vm;
      sq_setforeignptr(vm, loadedPrograms[i]);
      sq_resetobject(&loadedPrograms[i]->threadObj);

      //Get the thread handle, ref it so it doesn't go away, then store it in the loadedProgram
      //and pop it. Now the thread is independant
      sq_getstackobj(rootInterpreter->vm,-1, &loadedPrograms[i]->threadObj);
      sq_addref(vm, &loadedPrograms[i]->threadObj);
      sq_pop(rootInterpreter->vm, 1);


      //Make a new table as the root table of the VM, then set root aa it's delegate(The root table that is shared with the parent)
      //then set that new table as our root. This way we can access parent functions but have our own scope.
      sq_newtable(vm);
      sq_pushroottable(vm);
      sq_setdelegate(vm,-2);
      sq_setroottable(vm);
      
      //Get rid of any garbage, and ensure there's at leas one thomg on the stack
      sq_settop(vm, 1);

      memcpy(loadedPrograms[i]->hash, code, PROG_HASH_LEN);

      //Don't overflow our 16 byte max prog ID
      if(strlen(id)< 16)
      {
          strcpy(loadedPrograms[i]->programID, id);
      }
      else
      {
          memcpy(loadedPrograms[i]->programID, id,15);
          loadedPrograms[i]->programID[15] == 0;
      }
      loadedPrograms[i]->busy = 0;
      loadedPrograms[i]->vm = vm;

      if (SQ_SUCCEEDED(sq_compilebuffer(vm, code, strlen(code) + 1, _SC(id), SQTrue))) {
              if(inputBufToFree)
              {
                free(inputBufToFree);
                *inputBufToFreep = 0;
              }
         //That 1 is there as a special flag indicating we should close the program if we can't run it.
        _makeRequest(loadedPrograms[i], runLoaded, (void *)1);
      }
      else
      {
        //If we can't compile the code, don't load it at all.
        _closeProgram(id,true);
        Serial.println("Failed to compile code");
      }




      return 0;
    }
  }
  if(inputBufToFree)
  {
    free(inputBufToFree);
    *inputBufToFreep = 0;
  }
  //err, could not find free slot for program
  return 1;
}


int _Acorns::isRunning(const char * id, const char * hash)
{
  GIL_LOCK;
  struct loadedProgram * x = _programForId(id);
  if(hash)
  {
    if(memcmp(x->hash, hash, PROG_HASH_LEN))
    {
      x=0;
    }
  }
  GIL_UNLOCK;

  if(x)
  {
    return 1;
  }
  else
  {
    return 0;
  }
}

int _Acorns::isRunning(const char * id)
{
  isRunning(id,0);
}

int _Acorns::loadProgram(const char * code, const char * id)
{
  GIL_LOCK;
  _loadProgram(code, id);
  GIL_UNLOCK;
}
int  _Acorns::loadInputBuffer(const char * id)
{
  GIL_LOCK;
  _loadProgram(0,id);
  GIL_UNLOCK;
}

int _Acorns::loadFromFile(const char * fn)
{
  GIL_LOCK;
  FILE * f = fopen(fn, "r");
  if(f){
      fseek(f, 0L, SEEK_END);
      int sz = ftell(f);
      rewind(f);

      char * buf = (char *)malloc(sz);
      int p = 0;
      
      int chr = fgetc(f);
      while(chr != EOF)
      {
        buf[p]=chr;
        chr=fgetc(f);
        p+=1;
      }
      buf[p]=0;


      //Find last slash in the path
      const char * slash = fn;
      while(*fn)
      {
        if(*fn=='/')
        {
          slash = fn;
        }
        fn++;
      }
      fclose(f);

      GIL_UNLOCK;
      loadProgram(buf,slash+1);
      GIL_LOCK;
  }
  
  GIL_UNLOCK;
}

int _Acorns::loadFromDir(const char * dir)
{
  GIL_LOCK;
  DIR * d = opendir(dir);
  char buffer[256];
  struct dirent * de=readdir(d);
  char * fnpart;

  strcpy(buffer, dir);
  if (buffer[strlen(dir)-1]=='/')
  {
    fnpart = buffer+strlen(dir);
  }
  else
  {
    buffer[strlen(dir)]= '/';
    fnpart = buffer+strlen(dir)+1;
  }

  
  while(de)
  {
    //Rather absurd hackery just to put a / before the path that seems to lack one.
    strcpy(fnpart, de->d_name);
    GIL_UNLOCK;
    Serial.print("Loading program:");
    Serial.println(buffer);
    loadFromFile(buffer);
    GIL_LOCK;
    de=readdir(d);
  }
  GIL_UNLOCK;
}

//****************************************************************************/
//Callbacks management



//*********************************************************************************
//REPL


static HSQUIRRELVM replvm;
static loadedProgram * replprogram;
static SQChar  replbuffer[1024];
static int replpointer = 0;
static int startofline = 0;
static int string = 0;
static int blocks = 0;
static char dotprompt = 0;
static char retval = 0;
static char esc = 0;

/*Most of this function is from the original sq.c  see copyright notice in squirrel.h */

void _Acorns::replChar(char c)
{
  if (c == _SC('\n')) {

    if (blocks)
    {
      Serial.print("\n...");
    }
  }
  else
  {
    Serial.write(c);
  }

  if (c == _SC('\n')) {
    if (replpointer > 0 && replbuffer[replpointer - 1] == _SC('\\'))
    {
      replbuffer[replpointer - 1] = _SC('\n');

    }
    else if (blocks == 0)goto doing;
    replbuffer[replpointer++] = _SC('\n');
  }

  else if(c == _SC('\\'))
  {
    esc = 1;
  }
  else if(string && esc)
  {
       replbuffer[replpointer++] = (SQChar)c; 
  }
  else if (c == _SC('}') && !string) {
    blocks--;
    replbuffer[replpointer++] = (SQChar)c;
  }
  else if (c == _SC('{') && !string) {
    blocks++;
    replbuffer[replpointer++] = (SQChar)c;
  }
  else if (c == _SC('"') || c == _SC('\'')) {
    string = !string;
    replbuffer[replpointer++] = (SQChar)c;
  }
  else if (replpointer >= 1024 - 1) {
    Serial.print("sq : input line too long\n");
    goto resetting;
  }
  else {
    replbuffer[replpointer++] = (SQChar)c;
  }

  esc=0;
  return;
doing:
  replbuffer[replpointer] = _SC('\0');
  GIL_LOCK;
  if (replbuffer[0] == _SC('=')) {
    sprintf(sq_getscratchpad(replvm, 1024), _SC("return (%s)"), &replbuffer[1]);
    memcpy(replbuffer, sq_getscratchpad(replvm, -1), (scstrlen(sq_getscratchpad(replvm, -1)) + 1)*sizeof(SQChar));
    retval = 1;
  }
  replpointer = scstrlen(replbuffer);
  if (replpointer > 0) {
    SQInteger oldtop = sq_gettop(replvm);
    if (SQ_SUCCEEDED(sq_compilebuffer(replvm, replbuffer, replpointer, _SC("interactive console"), SQTrue))) {
      sq_pushroottable(replvm);
      if (SQ_SUCCEEDED(sq_call(replvm, 1, retval, SQTrue)) &&  retval) {
        scprintf(_SC("\n"));
        sq_pushroottable(replvm);
        sq_pushstring(replvm, _SC("print"), -1);
        sq_get(replvm, -2);
        sq_pushroottable(replvm);
        sq_push(replvm, -4);
        sq_call(replvm, 2, SQFalse, SQTrue);
        retval = 0;
      }
    }
    sq_settop(replvm, oldtop);
  }
  GIL_UNLOCK;
resetting:
  replpointer = 0;
  blocks = 0;
  string = 0;
  retval = 0;
  Serial.print("\n>>>");

}


//***********************************************************************************************************/
//INI file config handling
const char cfg_inifile[] = "/spiffs/config.ini";

HSQOBJECT ConfigTable;

static int iniCallback(const char *section, const char *key, const char *value, void *userdata)
{
  (void)userdata; /* this parameter is not used in this example */
  

  char buf[256];

  char slen = strlen(section);
  
  //Join section and key with a dot, if section exists.
  if(slen)
  {
    strcpy(buf,section);
    buf[slen]='.';
    strcpy(buf+slen+1, key);
  }
  else
  {
    strcpy(buf, key);
  }
  sq_pushobject(rootInterpreter->vm, ConfigTable);
  sq_pushstring(rootInterpreter->vm, buf, -1);
  sq_pushstring(rootInterpreter->vm, value, -1);
  sq_newslot(rootInterpreter->vm, -3, SQFalse);
  sq_pop(rootInterpreter->vm,1);
  return 1;
}

//This is the fallback getter for the config options
static SQInteger sqgetconfigfromini(HSQUIRRELVM v)
{
  const char * key;

  char buf[256];
  char section[49];

  if(sq_getstring(v,2,&key)==SQ_ERROR)
  {
    return sq_throwerror(v,"Key must be str");
  }
  char * x=strchr(key,'.');
  if(x)
  {
    if(x-key> 47)
    {
      return sq_throwerror(v,"Section is too long(max 48 bytes)");
    }
    memcpy(section, key, (x-key)+1);
    section[x-key] =0;
    key = x+1;
    ini_gets(section, key, "", buf, 256, cfg_inifile);
  }
  else
  {
  ini_gets("",key, "", buf, 256, cfg_inifile);
  }
  sq_pushstring(v,buf, -1);
  return 1;
}

void loadConfig()
{


  sq_resetobject(&ConfigTable);
  sq_pushroottable(rootInterpreter->vm);
  sq_pushstring(rootInterpreter->vm,"config",-1);
  sq_newtableex(rootInterpreter->vm, 2);
  //Create the delegate for the config function;
  sq_newtableex(rootInterpreter->vm, 2);
  sq_pushstring(rootInterpreter->vm,"_get",-1);
  sq_newclosure(rootInterpreter->vm,sqgetconfigfromini,0); //create a new function
  sq_newslot(rootInterpreter->vm,-3,SQFalse);
  sq_setdelegate(rootInterpreter->vm, -2);




  sq_getstackobj(rootInterpreter->vm, -1, &ConfigTable);
  sq_addref(rootInterpreter->vm,&ConfigTable);
  sq_newslot(rootInterpreter->vm,-3, SQFalse);



  sq_pop(rootInterpreter->vm,1);

  /*
  //Ensure the existance of the file.
  FILE * f = fopen(cfg_inifile,"r");
  if(f)
  {
    fclose(f);
  }
  else
  {
    return;
  }

  ini_browse(iniCallback, 0, cfg_inifile);
  */
}

static SQInteger sqwriteconfig(HSQUIRRELVM v)
{
  const char * key;
  const char * val;

  char section[49];

  if(sq_getstring(v,2,&key)==SQ_ERROR)
  {
    return sq_throwerror(v,"Key must be str");
  }
  if(sq_getstring(v,3,&val)==SQ_ERROR)
  {
    if(sq_tostring(v,3)==SQ_ERROR)
    {
      return sq_throwerror(v,"Requires 2 args");
    }
    sq_getstring(v,3,&val);
  }

  char * x=strchr(key,'.');
  if(x)
  {
    if(x-key> 47)
    {
      return sq_throwerror(v,"Section is too long(max 48 bytes)");
    }
    memcpy(section, key, (x-key)+1);
    section[x-key] =0;
    key = x+1;
    ini_puts(section, key,val,cfg_inifile);
    return 0;
  }

  ini_puts("", key,val,cfg_inifile);
}



/*First try to get a value from the table itself. Failing that, try to get a value from the .ini file.*/

void _Acorns::getConfig(const char * key, const char * d, char * buf, int maxlen )
{

  char section [256];

  char * x=strchr(key,'.');

  const char * buf2;
  bool found = false;
  

  sq_pushobject(rootInterpreter->vm, ConfigTable);
  sq_pushstring(rootInterpreter->vm, key, -1);
  if(sq_get(rootInterpreter->vm,-1) != SQ_ERROR)
  {
    if(sq_getsize(rootInterpreter->vm,-1)<maxlen)
    {
       sq_getstring(rootInterpreter->vm,-1, &buf2);
       strcpy(buf, buf2);
       found = true;
    }
    sq_pop(rootInterpreter->vm, 1);
  }
    sq_pop(rootInterpreter->vm, 1);
  if (found)
  {
    return;
  }

 if(x)
  {
    if(x-key> 47)
    {

    }
    else
    {
      memcpy(section, key, (x-key)+1);
      section[x-key] =0;
      char * akey = x+1;

      ini_gets(section, akey, "", buf, maxlen, cfg_inifile);

      if(strlen(buf))
      {
        return;
      }
    }
  }
  if(strlen(d)< maxlen)
  {
    strcpy(buf, d);
  }
}
/***************************************************************************************/
//WiFi
//Connect to wifi based on config file

//wifi event handler

//AsyncWebServer server(80);

/*
static void findLocalNtp()
{

    mdns_result_t * results = NULL;
    esp_err_t err = mdns_query_ptr(service_name, proto, 3000, 20,  &results);
    if(err){
        return;
    }
    if(!results){
        return;
    }

    mdns_result_t * best=results; 
    
    while(results)
    {
      //Find the lowest ASCIIBetical instance name
      if(strcmp(results->instance_name, best->instance_name))
      {
        best= results;
      }
    }

    WiFiUDP ntpUDP;
    NTPClient timeClient(ntpUDP);
    ntpUDP.begin();

    NTPClient.forceUpdate();

    
}
*/


//Configure wifi according to the config file
static void wifiConnect()
{ 
  char ssid[65];
  char psk[65];
  char wifimode[8];


  //Ensure the existance of the file.
  FILE * f = fopen(cfg_inifile,"r");
  if(f)
  {
    fclose(f);
  }
  else
  {
    return;
  }

  Acorns.getConfig("wifi.ssid","",ssid, 64);
  Acorns.getConfig("wifi.psk","",psk, 64);
  Acorns.getConfig("wifi.mode","sta",wifimode, 8);
  
  if(strcmp(wifimode,"sta")==0)
  {
    if(strlen(ssid))
    {
      WiFi.begin(ssid, psk);
      Serial.print("Trying to connect to: ");
      Serial.println(ssid);
    }
  }
  if(strcmp(wifimode,"ap")==0)
  {
    WiFi.softAP(ssid, psk);
    Serial.print("Serving as access point with SSID: ");
    Serial.println(ssid);
   
  }
   


}





static void WiFiEvent(WiFiEvent_t event){

    switch(event) {
      case SYSTEM_EVENT_STA_GOT_IP:
          break;
      case SYSTEM_EVENT_STA_DISCONNECTED:
          wifiConnect();

          break;
    }
}

//**************************************************************************************/
//General system control

//It's actually down below in this file
extern struct loadedProgram * replprogram;

static void printfunc(HSQUIRRELVM v, const SQChar *s, ...)
{

  struct loadedProgram * prg = ((loadedProgram *)sq_getforeignptr(v));  

  char buf[256];
  va_list vl;
  va_start(vl, s);
  vsnprintf(buf, 256, s, vl);
  va_end(vl);
    if(prg==replprogram)
    {
      Serial.println(buf);
    }
    else
    {
      if (Acorns.printfunc)
      {
        Acorns.printfunc(prg, buf);
      }
      else
      {
        Serial.println(buf);
      }
    }
}

static void errorfunc(HSQUIRRELVM v, const SQChar *s, ...)
{

  struct loadedProgram * prg = ((loadedProgram *)sq_getforeignptr(v));  

  char buf[256];
  va_list vl;
  va_start(vl, s);
  vsnprintf(buf, 256, s, vl);
  va_end(vl);


  if(prg==replprogram)
  {
    Serial.println("");
    Serial.print(buf);
  }
  else
  {
    if (Acorns.errorfunc)
    {
      Acorns.errorfunc(prg, buf);
    }
    else
    {
      Serial.println("");
      Serial.print(buf);
    }
  }
}



//Adds the basic standard libraries to the squirrel VM
static void addlibs(HSQUIRRELVM v)
{
  sq_setprintfunc(v, printfunc, errorfunc);
  sq_pushroottable(v);
  sqstd_register_bloblib(v);
  sqstd_register_iolib(v);
  sqstd_register_systemlib(v);
  sqstd_register_mathlib(v);
  sqstd_register_stringlib(v);

  //aux library
  //sets error handlers
  sqstd_seterrorhandlers(v);
  sq_pop(v, 1);
}

SQObject sqSerialBaseClass;



void resetLoadedProgram(loadedProgram * p)
{

}


static HSQOBJECT ReplThreadObj;


static bool began = false;

//Initialize squirrel task management
void _Acorns::begin()
{
 
  //Run this once and only once
  if (began)
  {
    return;
  }
  began = true;

  Serial.println("Acorns: Squirrel for Arduino");
  Serial.println("Based on: http://www.squirrel-lang.org/\n");

  for (char i = 0; i < ACORNS_MAXPROGRAMS; i++)
  {
    loadedPrograms[i] == 0;
  }
  

  _acorns_gil_lock = xSemaphoreCreateBinary( );
  xSemaphoreGive(_acorns_gil_lock);





  //This will probably seed the RNG far better than anyone should even think of needing
  //For non-crypto stuff.
  rng_key += esp_random();
  rng_key += esp_random()<<32;
  
  entropy += esp_random()<<32;
  entropy += esp_random();


  //Start the root interpreter
  rootInterpreter = (struct loadedProgram *)malloc(sizeof(struct loadedProgram));

  rootInterpreter->vm = sq_open(1024); //creates a VM with initial stack size 1024
  
  //Setup the config system
  loadConfig();

  WiFi.onEvent(WiFiEvent);
  wifiConnect();  

  //Lets us advertise a hostname. This already has it's own auto reconnect logic.
  char hostname[32];
  Acorns.getConfig("wifi.hostname","",hostname, 32);
  if(strlen(hostname))
  {
    Serial.println("Doing MDNS begin");
    MDNS.begin(hostname);
  }


  registerFunction(0, sqwriteconfig, "setConfig");

  registerFunction(0, sqlorem, "lorem");
  registerFunction(0, sqrandom, "random");
  registerFunction(0, sqimport,"import");
  registerFunction(0, sqcloseProgram,"forceClose");

  addlibs(rootInterpreter->vm);
  Serial.println("Added core libraries");

  //This is part of the class, it's in acorns_aduinobindings
  addArduino(rootInterpreter->vm);

  //Use the root interpeter to create the modules table
  sq_newtableex(rootInterpreter->vm,8);
  sq_resetobject(&modulesTable);
  sq_getstackobj(rootInterpreter->vm,-1, &modulesTable);
  sq_addref(rootInterpreter->vm, &modulesTable);
  sq_pop(rootInterpreter->vm, 1);

  sq_setforeignptr(rootInterpreter->vm, rootInterpreter);






  //Create the directory iteration code
  sq_newtableex(rootInterpreter->vm, 2);
  sq_pushstring(rootInterpreter->vm,"_nexti",-1);
  sq_newclosure(rootInterpreter->vm,sqdirectoryiterator_next,0); //create a new function
  sq_newslot(rootInterpreter->vm,-3,SQFalse);

  //The get function that's actually just a passthrough
  sq_pushstring(rootInterpreter->vm,"_get",-1);
  sq_newclosure(rootInterpreter->vm,sqdirectoryiterator_get,0); //create a new function
  sq_newslot(rootInterpreter->vm,-3,SQFalse);

  sq_resetobject(&DirEntryObj);
  sq_getstackobj(rootInterpreter->vm, -1, &DirEntryObj);
  sq_addref(rootInterpreter->vm,&DirEntryObj);
  sq_pop(rootInterpreter->vm,1);

  //create the dir function.
  registerFunction(0,sqdirectoryiterator,"dir");

  memcpy(rootInterpreter->hash, "//This is the first line of the code which will server as the ID", PROG_HASH_LEN);
  rootInterpreter->busy = 0;
  rootInterpreter->inputBuffer =0;
  rootInterpreter->inputBufferLen =0;
  rootInterpreter->parent = 0;

  request_queue = xQueueCreate( 25, sizeof(struct Request));




  for (char i = 0; i < ACORNS_THREADS; i++)
  {
    xTaskCreatePinnedToCore(InterpreterTask,
                            "SquirrelVM",
                            4096,
                            0,
                            1,
                            &sqTasks[i],
                            1
                           );
  }




  Serial.println("Initialized root interpreter.");

  replvm = sq_newthread(rootInterpreter->vm, 1024);
  replprogram = (struct loadedProgram *)malloc(sizeof(struct loadedProgram));
  sq_setforeignptr(replvm, replprogram);
  replprogram -> busy = 0;
  replprogram-> callbackRecievers =0;
  replprogram-> parent = rootInterpreter;
  replprogram->vm = replvm;
  replprogram->inputBuffer =0;
  replprogram->inputBufferLen =0;

  sq_resetobject(&ReplThreadObj);
  sq_getstackobj(rootInterpreter->vm, -1, &ReplThreadObj);
  sq_addref(rootInterpreter->vm, &ReplThreadObj);

  //Clear the stack, just in case. It's important the ome thing we leave
  //Be the repl VM.
  sq_settop(rootInterpreter->vm, 1);
  loadFromDir("/spiffs/sqprogs");
  Serial.print("Free Heap: ");
  Serial.print(ESP.getFreeHeap());
  Serial.println("\nStarted REPL interpreter\n");
  //All booted 
  Serial.println(acorn_getQuote());
  Serial.print("\n>>>");

}

SQInteger _Acorns::registerFunction(const char *id,SQFUNCTION f,const char *fname)
{
    GIL_LOCK;
    loadedProgram * p = _programForId(id);
    sq_pushroottable(p->vm);
    sq_pushstring(p->vm,fname,-1);
    sq_newclosure(p->vm,f,0); //create a new function
    sq_newslot(p->vm,-3,SQFalse);
    sq_pop(p->vm,1); //pops the root table
    GIL_UNLOCK;
}


SQInteger _Acorns::setIntVariable(const char *id,long long value,const char *fname)
{
    GIL_LOCK;
    loadedProgram * p = _programForId(id);
    sq_pushroottable(p->vm);
    sq_pushstring(p->vm,fname,-1);
    sq_pushinteger(p->vm, value);
    sq_newslot(p->vm,-3,SQFalse);
    sq_pop(p->vm,1); //pops the root table
    GIL_UNLOCK;
}


//*******************************************************/
//Compatibility


//Squirrel needs this for something
int __attribute__((weak)) system(const char *string)
{
  
}

///********************************************************/
//API Class instance
_Acorns Acorns;
