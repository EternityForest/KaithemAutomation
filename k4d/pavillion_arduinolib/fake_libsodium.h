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

#include <BLAKE2b.h>
#ifdef __cplusplus
extern "C"{
#endif 
#include "tweetnacl.h"
#ifdef __cplusplus
}
#endif

#include <string.h>

extern BLAKE2b blake;




void  crypto_generichash(unsigned char *out, size_t outlen,
                       const unsigned char *in, unsigned long long inlen,
                       const unsigned char *key, size_t keylen){
                        
  blake.reset(key, keylen, outlen);
  blake.update(in, inlen);
  blake.finalize(out, outlen);
}


void randombytes_buf(void * const buf, const size_t size)
{

  for(uint32_t i = 0;i<size;i++)
  {
    ((uint8_t*)buf)[i]=esp_random();
  }
}
void crypto_secretbox_easy(unsigned char *c, const unsigned char *m,
                          unsigned long long mlen, const unsigned char *n,
                          const unsigned char *k)
                          {
                            uint8_t * temp = (uint8_t *)malloc(mlen+33);
                            for (uint8_t i=0;i<33;i++)
                            {
                              temp[i]=0;
                            }
                            
                            memcpy(temp+32, m,  mlen);
                           crypto_secretbox(c,temp,mlen+32,n,k);

                           memmove(c,c+16, mlen+16);


                           free(temp);

                          
                          }

int crypto_secretbox_open_easy(unsigned char *c, const unsigned char *m,
                          unsigned long long mlen, const unsigned char *n,
                          const unsigned char *k)
                          {
                            Serial.println((float)mlen);
                            Serial.println("~~");
                            uint8_t * temp =  (uint8_t *)malloc(mlen+35);
                            for (uint8_t i=0;i<17;i++)
                            {
                              temp[i]=0;
                            }
                            
                            memcpy(temp+16, m,mlen);                    
    

                           int x =crypto_secretbox_open(c,temp,mlen+16,n,k);
                           memmove(c,c+32, mlen-16);
                           
                           free(temp);
                           return x;
                          }


