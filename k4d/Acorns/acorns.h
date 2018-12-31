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

#pragma once

#include "Arduino.h"

#include "utility/squirrel.h"
extern "C"
{
#include "utility/sqstdblob.h"
#include "utility/sqstdsystem.h"
#include "utility/sqstdio.h"
#include "utility/sqstdmath.h"
#include "utility/sqstdstring.h"
#include "utility/sqstdaux.h"
}
#include "utility/minIni.h"

struct CallbackData;
struct loadedProgram;
class _Acorns
{

  public:

    void (*printfunc)(loadedProgram *, const char *);
    void (*errorfunc)(loadedProgram *, const char *);

    void replChar(char);
    void begin();
    void begin(const char *);


    int loadProgram(const char * code, const char * id);
    int runProgram(const char * code, const char * id);
    int runProgram(const char * code, const char * id,  void (*errorfunc)(loadedProgram *, const char *)=NULL, void (*printfunc)(loadedProgram *, const char *)=NULL, const char * workingDir=0);

    int loadInputBuffer(const char * id);
    int loadInputBuffer(const char * id,bool force);

    int closeProgram(const char * id);
    int closeProgram(const char * id, char force);
    String joinWorkingDir(HSQUIRRELVM v,char * dir);

    struct CallbackData *acceptCallback(HSQUIRRELVM vm, SQInteger idx,void (*cleanup)(struct loadedProgram *, void *));
    void makeRequest(const char *, void (*f)(loadedProgram *, void *), void * arg);
    
    SQInteger registerFunction(const char* id,SQFUNCTION f,const char *fname);
    SQInteger setIntVariable(const char *id,long long value,const char *fname);

    void addArduino(HSQUIRRELVM);
    void runInputBuffer(const char * id);
    void writeToInput(const char * id, const char * data, int len);
    void writeToInput(const char * id, const char * data, int len, long position);

    void clearInput(const char * id);

    int isRunning(const char * id);
    int isRunning(const char * id, const char * hash);
    void getConfig(const char * key, const char * d, char * buf, int maxlen );
    int loadFromFile(const char * fn);
    int loadFromDir(const char * dir);

    const char * getQuote();

};

#define PROG_HASH_LEN 24
//The userdata struct for each loadedProgram interpreter
struct loadedProgram
{

  //Points to the slot in the function table where the pointer to this is stored,
  //So we can zero it when we free it.
  struct loadedProgram ** slot;
  //This is how we can know which program to replace when updating with a new version
  char programID[24];
  //The first 30 bytes of a file identify its "version" so we don't
  //replace things that don't need replacing.
  char hash[PROG_HASH_LEN];
  char * workingDir;
  //This is the input buffer that gives us an easy way to send things to a program
  //in excess of the 1500 byte limit for UDP. We might also use it for other stuff later.
  char * inputBuffer;

  //How many bytes are in the input buffer.
  int inputBufferLen;

  //1  or above if the program is busy, don't mess with it in any way except setting/getting vars and making sub-programs.
  //0 means you can delete, replace, etc

  //When a child interpreter runs, it increments all parents and itself.
  //In this way it is kind of like a reference count.
  //Note that it's not the same as GIL, you can yield the GIL but still flag a
  //program as busy so the other tasts don't mess with it.
  char busy;

  HSQUIRRELVM vm;

  //We often use sq_newthread, this is where we store the thread handle so
  //We don't have to clutter up a VM namespace.
  HSQOBJECT threadObj;


//A parent proram, used because we don't want to stop a running program's parent
  struct loadedProgram * parent;

  //A reference count for this struct itself.
  //We only change it under the GIL lock.
  //It's purpose is that the interpreter thread must know if
  //someone has deleted and replaced a VM while we yield.

  //This lets us set the VM to 0 to indicate that a program has ended.
  //And still have this struct around to read that info from.

  //Essentially, this implements zombie processes, handles to things that don't exist.
  char refcount;

  //linked list of the recievers, or 0 if there are none.
  struct CallbackData * callbackRecievers;
  
  //This errorfunc handles errors for that program in addition to reporting to the root.
  //Same with print.

    void (*printfunc)(loadedProgram *, const char *);
    void (*errorfunc)(loadedProgram *, const char *);

};
struct CallbackData
{

  //User code amd the manager both reference this.
  //When it hits 0, free it.
  char refcount;
  //These are stored in linked lists
  struct CallbackData * next;

  //This program may be set to zero to indicate that the program is no longer listening fo that callback.
  struct loadedProgram * prog;
 
  //The actual callable that gets called when the callback happens
  //
  HSQOBJECT * callable;

  void * userpointer;
  void (*cleanup)(struct loadedProgram *, void *);
};

void deref_cb(CallbackData * p);

extern _Acorns Acorns;


#ifdef INC_FREERTOS_H
//Wait 10 million ticks which is probably days, but still assert it if it fails
extern SemaphoreHandle_t _acorns_gil_lock;
#define GIL_LOCK assert(xSemaphoreTake(_acorns_gil_lock,200))
#define GIL_UNLOCK xSemaphoreGive(_acorns_gil_lock)
#else
#define GIL_LOCK
#define GIL_UNLOCK
#endif

//How many threads in the thread pool
#define  ACORNS_THREADS 4

//How many slots in the process table
#define ACORNS_MAXPROGRAMS 16
#define dbg(x) Serial.println(x)