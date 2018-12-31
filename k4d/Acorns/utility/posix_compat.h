#pragma once
#include "Arduino.h"

#ifdef ESP32
#include <stdio.h>
#include <time.h>
#define SEEK_ENUM int
#else
#include "FS.h"
#include <stdint.h>
//Kind of insane abstraction here.
//We are trying to make the arduino version look like the POSIX-y version.
#define closedir(x) free(x)
#define DIR Dir
#define FILE File
#define dirent FakePosixDirEntryObj
#define fopen fake_fopen
#define SEEK_END SeekEnd
#define SEEK_CUR SeekCur
#define SEEK_SET SeekSet
#define SEEK_ENUM SeekMode
#define fflush(x) (0)
#define feof(x) ((x)->position()==((x)->size()-1))

int rename ( const char * oldname, const char * newname );
int remove ( const char * filename );

//We don't care about thread safety, the 8266 has a real stdio.
struct FakePosixDirEntryObj
{
  const char * d_name;
};

extern struct FakePosixDirEntryObj MostRecentlyOpenedDirectory;
int fclose(File * x);
int fputs ( const char * str, FILE * stream );
DIR * opendir(const char *name);
FILE * fopen(const char *name,const char * mode);
size_t fread ( void * ptr, size_t size, size_t count, FILE * stream );
int fgetc ( FILE * stream );
int fseek ( FILE * stream, long int offset, SeekMode origin );

void rewind(FILE * stream);
size_t ftell(FILE * stream);
char *fgets(char *str, int num, FILE *stream);
size_t fwrite ( const void * ptr, size_t size, size_t count, FILE * stream );


struct FakePosixDirEntryObj * readdir(DIR * dirp);
#endif