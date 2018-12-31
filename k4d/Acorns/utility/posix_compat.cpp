
#include "FS.h"
#ifdef ESP32
#include "SPIFFS.h"
#else
#include "posix_compat.h"

#include <stdint.h>

struct FakePosixDirEntryObj MostRecentlyOpenedDirectory;
static bool hasSpiffs = false;

bool spiffsPosixBegin()
{
  hasSpiffs = SPIFFS.begin();
}

int rename(const char *oldname, const char *newname)
{
  if (hasSpiffs == false)
  {
    return 1;
  }
  return SPIFFS.rename(oldname, newname);
}
int remove(const char *filename)
{
  if (hasSpiffs == false)
  {
    return 1;
  }
  return SPIFFS.remove(filename);
}

DIR *opendir(const char *name)
{

    if (hasSpiffs==false)
  {
    return 0;
  }
  Dir *x = (Dir *)malloc(sizeof(Dir));
  *x = SPIFFS.openDir(name);
  return x;
}
int fclose(File *x)
{
  free(x);
  return 0;
}

int fputs(const char *str, FILE *stream)
{
  stream->print(str);
}

FILE *fake_fopen(const char *name, const char *mode)
{
    if (hasSpiffs==false)
  {
    return 0;
  }
  if (name == 0)
  {
    return 0;
  }
  if (SPIFFS.exists(name) == false)
  {
    if (strcmp(mode, "r") == 0)
    {
      return 0;
    }
    if (strcmp(mode, "r+") == 0)
    {
      return 0;
    }
  }
  File *x = (File *)malloc(sizeof(File));
  *x = SPIFFS.open(name, mode);
  return x;
}

size_t fread(void *ptr, size_t size, size_t count, FILE *stream)
{
  stream->readBytes((char *)ptr, size * count);
}

size_t fwrite(const void *ptr, size_t size, size_t count, FILE *stream)
{
  stream->write((const uint8_t *)ptr, size * count);
}
char *fgets(char *str, int num, FILE *stream)
{
  int b;
  int p = 0;
  while (num)
  {
    if ((b = stream->read()) < 0)
    {
      if (p)
      {
        return (str);
      }
      else
      {
        return 0;
      }
    }

    *str = b;
    str++;
    p++;
    num--;
  }
}

int fgetc(FILE *stream)
{
  return stream->read();
}
int fseek(FILE *stream, long int offset, SeekMode origin)
{
  stream->seek(offset, origin);
}

void rewind(FILE *stream)
{
  fseek(stream, 0, SEEK_SET);
}

size_t ftell(FILE *stream)
{
  return stream->position();
}

struct FakePosixDirEntryObj *readdir(DIR *dirp)
{
  dirp->next();
  //If this breaks, look at this line
  MostRecentlyOpenedDirectory.d_name = dirp->fileName().c_str();
  return &MostRecentlyOpenedDirectory;
}
#endif