/*
 * Copyright (C) 2015 Southern Storm Software, Pty Ltd.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included
 * in all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
 * OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
 * DEALINGS IN THE SOFTWARE.
 */

/*
This example runs tests on the GCM implementation to verify correct behaviour.
*/

#include <Crypto.h>
#include <CryptoLW.h>
#include <AES.h>
#include <Speck.h>
#include <SpeckTiny.h>
#include <GCM.h>
#include <string.h>
#if defined(ESP8266) || defined(ESP32)
#include <pgmspace.h>
#else
#include <avr/pgmspace.h>
#endif

// There isn't enough memory to test both AES and Speck on the Uno,
// so disable Speck testing on AVR platforms unless explicitly enabled.
// When enabled, some of the AES tests are disabled to reclaim memory.
#if defined(__AVR__)
//#define TEST_SPECK 1
#endif

#define MAX_PLAINTEXT_LEN 64

struct TestVector
{
    const char *name;
    uint8_t key[32];
    uint8_t plaintext[MAX_PLAINTEXT_LEN];
    uint8_t ciphertext[MAX_PLAINTEXT_LEN];
    uint8_t authdata[20];
    uint8_t iv[12];
    uint8_t tag[16];
    size_t authsize;
    size_t datasize;
    size_t tagsize;
    size_t ivsize;
};

// Test vectors for AES in GCM mode from Appendix B of:
// http://csrc.nist.gov/groups/ST/toolkit/BCM/documents/proposedmodes/gcm/gcm-revised-spec.pdf
static TestVector const testVectorGCM1 PROGMEM = {
    .name        = "AES-128 GCM #1",
    .key         = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    .plaintext   = {0x00},
    .ciphertext  = {0x00},
    .authdata    = {0x00},
    .iv          = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00},
    .tag         = {0x58, 0xe2, 0xfc, 0xce, 0xfa, 0x7e, 0x30, 0x61,
                    0x36, 0x7f, 0x1d, 0x57, 0xa4, 0xe7, 0x45, 0x5a},
    .authsize    = 0,
    .datasize    = 0,
    .tagsize     = 16,
    .ivsize      = 12
};
#ifndef TEST_SPECK
static TestVector const testVectorGCM2 PROGMEM = {
    .name        = "AES-128 GCM #2",
    .key         = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    .plaintext   = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    .ciphertext  = {0x03, 0x88, 0xda, 0xce, 0x60, 0xb6, 0xa3, 0x92,
                    0xf3, 0x28, 0xc2, 0xb9, 0x71, 0xb2, 0xfe, 0x78},
    .authdata    = {0x00},
    .iv          = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00},
    .tag         = {0xab, 0x6e, 0x47, 0xd4, 0x2c, 0xec, 0x13, 0xbd,
                    0xf5, 0x3a, 0x67, 0xb2, 0x12, 0x57, 0xbd, 0xdf},
    .authsize    = 0,
    .datasize    = 16,
    .tagsize     = 16,
    .ivsize      = 12
};
static TestVector const testVectorGCM3 PROGMEM = {
    .name        = "AES-128 GCM #3",
    .key         = {0xfe, 0xff, 0xe9, 0x92, 0x86, 0x65, 0x73, 0x1c,
                    0x6d, 0x6a, 0x8f, 0x94, 0x67, 0x30, 0x83, 0x08},
    .plaintext   = {0xd9, 0x31, 0x32, 0x25, 0xf8, 0x84, 0x06, 0xe5,
                    0xa5, 0x59, 0x09, 0xc5, 0xaf, 0xf5, 0x26, 0x9a,
                    0x86, 0xa7, 0xa9, 0x53, 0x15, 0x34, 0xf7, 0xda,
                    0x2e, 0x4c, 0x30, 0x3d, 0x8a, 0x31, 0x8a, 0x72,
                    0x1c, 0x3c, 0x0c, 0x95, 0x95, 0x68, 0x09, 0x53,
                    0x2f, 0xcf, 0x0e, 0x24, 0x49, 0xa6, 0xb5, 0x25,
                    0xb1, 0x6a, 0xed, 0xf5, 0xaa, 0x0d, 0xe6, 0x57,
                    0xba, 0x63, 0x7b, 0x39, 0x1a, 0xaf, 0xd2, 0x55},
    .ciphertext  = {0x42, 0x83, 0x1e, 0xc2, 0x21, 0x77, 0x74, 0x24,
                    0x4b, 0x72, 0x21, 0xb7, 0x84, 0xd0, 0xd4, 0x9c,
                    0xe3, 0xaa, 0x21, 0x2f, 0x2c, 0x02, 0xa4, 0xe0,
                    0x35, 0xc1, 0x7e, 0x23, 0x29, 0xac, 0xa1, 0x2e,
                    0x21, 0xd5, 0x14, 0xb2, 0x54, 0x66, 0x93, 0x1c,
                    0x7d, 0x8f, 0x6a, 0x5a, 0xac, 0x84, 0xaa, 0x05,
                    0x1b, 0xa3, 0x0b, 0x39, 0x6a, 0x0a, 0xac, 0x97,
                    0x3d, 0x58, 0xe0, 0x91, 0x47, 0x3f, 0x59, 0x85},
    .authdata    = {0x00},
    .iv          = {0xca, 0xfe, 0xba, 0xbe, 0xfa, 0xce, 0xdb, 0xad,
                    0xde, 0xca, 0xf8, 0x88},
    .tag         = {0x4d, 0x5c, 0x2a, 0xf3, 0x27, 0xcd, 0x64, 0xa6,
                    0x2c, 0xf3, 0x5a, 0xbd, 0x2b, 0xa6, 0xfa, 0xb4},
    .authsize    = 0,
    .datasize    = 64,
    .tagsize     = 16,
    .ivsize      = 12
};
static TestVector const testVectorGCM4 PROGMEM = {
    .name        = "AES-128 GCM #4",
    .key         = {0xfe, 0xff, 0xe9, 0x92, 0x86, 0x65, 0x73, 0x1c,
                    0x6d, 0x6a, 0x8f, 0x94, 0x67, 0x30, 0x83, 0x08},
    .plaintext   = {0xd9, 0x31, 0x32, 0x25, 0xf8, 0x84, 0x06, 0xe5,
                    0xa5, 0x59, 0x09, 0xc5, 0xaf, 0xf5, 0x26, 0x9a,
                    0x86, 0xa7, 0xa9, 0x53, 0x15, 0x34, 0xf7, 0xda,
                    0x2e, 0x4c, 0x30, 0x3d, 0x8a, 0x31, 0x8a, 0x72,
                    0x1c, 0x3c, 0x0c, 0x95, 0x95, 0x68, 0x09, 0x53,
                    0x2f, 0xcf, 0x0e, 0x24, 0x49, 0xa6, 0xb5, 0x25,
                    0xb1, 0x6a, 0xed, 0xf5, 0xaa, 0x0d, 0xe6, 0x57,
                    0xba, 0x63, 0x7b, 0x39},
    .ciphertext  = {0x42, 0x83, 0x1e, 0xc2, 0x21, 0x77, 0x74, 0x24,
                    0x4b, 0x72, 0x21, 0xb7, 0x84, 0xd0, 0xd4, 0x9c,
                    0xe3, 0xaa, 0x21, 0x2f, 0x2c, 0x02, 0xa4, 0xe0,
                    0x35, 0xc1, 0x7e, 0x23, 0x29, 0xac, 0xa1, 0x2e,
                    0x21, 0xd5, 0x14, 0xb2, 0x54, 0x66, 0x93, 0x1c,
                    0x7d, 0x8f, 0x6a, 0x5a, 0xac, 0x84, 0xaa, 0x05,
                    0x1b, 0xa3, 0x0b, 0x39, 0x6a, 0x0a, 0xac, 0x97,
                    0x3d, 0x58, 0xe0, 0x91},
    .authdata    = {0xfe, 0xed, 0xfa, 0xce, 0xde, 0xad, 0xbe, 0xef,
                    0xfe, 0xed, 0xfa, 0xce, 0xde, 0xad, 0xbe, 0xef,
                    0xab, 0xad, 0xda, 0xd2},
    .iv          = {0xca, 0xfe, 0xba, 0xbe, 0xfa, 0xce, 0xdb, 0xad,
                    0xde, 0xca, 0xf8, 0x88},
    .tag         = {0x5b, 0xc9, 0x4f, 0xbc, 0x32, 0x21, 0xa5, 0xdb,
                    0x94, 0xfa, 0xe9, 0x5a, 0xe7, 0x12, 0x1a, 0x47},
    .authsize    = 20,
    .datasize    = 60,
    .tagsize     = 16,
    .ivsize      = 12
};
static TestVector const testVectorGCM5 PROGMEM = {
    .name        = "AES-128 GCM #5",
    .key         = {0xfe, 0xff, 0xe9, 0x92, 0x86, 0x65, 0x73, 0x1c,
                    0x6d, 0x6a, 0x8f, 0x94, 0x67, 0x30, 0x83, 0x08},
    .plaintext   = {0xd9, 0x31, 0x32, 0x25, 0xf8, 0x84, 0x06, 0xe5,
                    0xa5, 0x59, 0x09, 0xc5, 0xaf, 0xf5, 0x26, 0x9a,
                    0x86, 0xa7, 0xa9, 0x53, 0x15, 0x34, 0xf7, 0xda,
                    0x2e, 0x4c, 0x30, 0x3d, 0x8a, 0x31, 0x8a, 0x72,
                    0x1c, 0x3c, 0x0c, 0x95, 0x95, 0x68, 0x09, 0x53,
                    0x2f, 0xcf, 0x0e, 0x24, 0x49, 0xa6, 0xb5, 0x25,
                    0xb1, 0x6a, 0xed, 0xf5, 0xaa, 0x0d, 0xe6, 0x57,
                    0xba, 0x63, 0x7b, 0x39},
    .ciphertext  = {0x61, 0x35, 0x3b, 0x4c, 0x28, 0x06, 0x93, 0x4a,
                    0x77, 0x7f, 0xf5, 0x1f, 0xa2, 0x2a, 0x47, 0x55,
                    0x69, 0x9b, 0x2a, 0x71, 0x4f, 0xcd, 0xc6, 0xf8,
                    0x37, 0x66, 0xe5, 0xf9, 0x7b, 0x6c, 0x74, 0x23,
                    0x73, 0x80, 0x69, 0x00, 0xe4, 0x9f, 0x24, 0xb2,
                    0x2b, 0x09, 0x75, 0x44, 0xd4, 0x89, 0x6b, 0x42,
                    0x49, 0x89, 0xb5, 0xe1, 0xeb, 0xac, 0x0f, 0x07,
                    0xc2, 0x3f, 0x45, 0x98},
    .authdata    = {0xfe, 0xed, 0xfa, 0xce, 0xde, 0xad, 0xbe, 0xef,
                    0xfe, 0xed, 0xfa, 0xce, 0xde, 0xad, 0xbe, 0xef,
                    0xab, 0xad, 0xda, 0xd2},
    .iv          = {0xca, 0xfe, 0xba, 0xbe, 0xfa, 0xce, 0xdb, 0xad},
    .tag         = {0x36, 0x12, 0xd2, 0xe7, 0x9e, 0x3b, 0x07, 0x85,
                    0x56, 0x1b, 0xe1, 0x4a, 0xac, 0xa2, 0xfc, 0xcb},
    .authsize    = 20,
    .datasize    = 60,
    .tagsize     = 16,
    .ivsize      = 8
};
#endif // !TEST_SPECK
static TestVector const testVectorGCM10 PROGMEM = {
    .name        = "AES-192 GCM #10",
    .key         = {0xfe, 0xff, 0xe9, 0x92, 0x86, 0x65, 0x73, 0x1c,
                    0x6d, 0x6a, 0x8f, 0x94, 0x67, 0x30, 0x83, 0x08,
                    0xfe, 0xff, 0xe9, 0x92, 0x86, 0x65, 0x73, 0x1c},
    .plaintext   = {0xd9, 0x31, 0x32, 0x25, 0xf8, 0x84, 0x06, 0xe5,
                    0xa5, 0x59, 0x09, 0xc5, 0xaf, 0xf5, 0x26, 0x9a,
                    0x86, 0xa7, 0xa9, 0x53, 0x15, 0x34, 0xf7, 0xda,
                    0x2e, 0x4c, 0x30, 0x3d, 0x8a, 0x31, 0x8a, 0x72,
                    0x1c, 0x3c, 0x0c, 0x95, 0x95, 0x68, 0x09, 0x53,
                    0x2f, 0xcf, 0x0e, 0x24, 0x49, 0xa6, 0xb5, 0x25,
                    0xb1, 0x6a, 0xed, 0xf5, 0xaa, 0x0d, 0xe6, 0x57,
                    0xba, 0x63, 0x7b, 0x39},
    .ciphertext  = {0x39, 0x80, 0xca, 0x0b, 0x3c, 0x00, 0xe8, 0x41,
                    0xeb, 0x06, 0xfa, 0xc4, 0x87, 0x2a, 0x27, 0x57,
                    0x85, 0x9e, 0x1c, 0xea, 0xa6, 0xef, 0xd9, 0x84,
                    0x62, 0x85, 0x93, 0xb4, 0x0c, 0xa1, 0xe1, 0x9c,
                    0x7d, 0x77, 0x3d, 0x00, 0xc1, 0x44, 0xc5, 0x25,
                    0xac, 0x61, 0x9d, 0x18, 0xc8, 0x4a, 0x3f, 0x47,
                    0x18, 0xe2, 0x44, 0x8b, 0x2f, 0xe3, 0x24, 0xd9,
                    0xcc, 0xda, 0x27, 0x10},
    .authdata    = {0xfe, 0xed, 0xfa, 0xce, 0xde, 0xad, 0xbe, 0xef,
                    0xfe, 0xed, 0xfa, 0xce, 0xde, 0xad, 0xbe, 0xef,
                    0xab, 0xad, 0xda, 0xd2},
    .iv          = {0xca, 0xfe, 0xba, 0xbe, 0xfa, 0xce, 0xdb, 0xad,
                    0xde, 0xca, 0xf8, 0x88},
    .tag         = {0x25, 0x19, 0x49, 0x8e, 0x80, 0xf1, 0x47, 0x8f,
                    0x37, 0xba, 0x55, 0xbd, 0x6d, 0x27, 0x61, 0x8c},
    .authsize    = 20,
    .datasize    = 60,
    .tagsize     = 16,
    .ivsize      = 12
};
static TestVector const testVectorGCM16 PROGMEM = {
    .name        = "AES-256 GCM #16",
    .key         = {0xfe, 0xff, 0xe9, 0x92, 0x86, 0x65, 0x73, 0x1c,
                    0x6d, 0x6a, 0x8f, 0x94, 0x67, 0x30, 0x83, 0x08,
                    0xfe, 0xff, 0xe9, 0x92, 0x86, 0x65, 0x73, 0x1c,
                    0x6d, 0x6a, 0x8f, 0x94, 0x67, 0x30, 0x83, 0x08},
    .plaintext   = {0xd9, 0x31, 0x32, 0x25, 0xf8, 0x84, 0x06, 0xe5,
                    0xa5, 0x59, 0x09, 0xc5, 0xaf, 0xf5, 0x26, 0x9a,
                    0x86, 0xa7, 0xa9, 0x53, 0x15, 0x34, 0xf7, 0xda,
                    0x2e, 0x4c, 0x30, 0x3d, 0x8a, 0x31, 0x8a, 0x72,
                    0x1c, 0x3c, 0x0c, 0x95, 0x95, 0x68, 0x09, 0x53,
                    0x2f, 0xcf, 0x0e, 0x24, 0x49, 0xa6, 0xb5, 0x25,
                    0xb1, 0x6a, 0xed, 0xf5, 0xaa, 0x0d, 0xe6, 0x57,
                    0xba, 0x63, 0x7b, 0x39},
    .ciphertext  = {0x52, 0x2d, 0xc1, 0xf0, 0x99, 0x56, 0x7d, 0x07,
                    0xf4, 0x7f, 0x37, 0xa3, 0x2a, 0x84, 0x42, 0x7d,
                    0x64, 0x3a, 0x8c, 0xdc, 0xbf, 0xe5, 0xc0, 0xc9,
                    0x75, 0x98, 0xa2, 0xbd, 0x25, 0x55, 0xd1, 0xaa,
                    0x8c, 0xb0, 0x8e, 0x48, 0x59, 0x0d, 0xbb, 0x3d,
                    0xa7, 0xb0, 0x8b, 0x10, 0x56, 0x82, 0x88, 0x38,
                    0xc5, 0xf6, 0x1e, 0x63, 0x93, 0xba, 0x7a, 0x0a,
                    0xbc, 0xc9, 0xf6, 0x62},
    .authdata    = {0xfe, 0xed, 0xfa, 0xce, 0xde, 0xad, 0xbe, 0xef,
                    0xfe, 0xed, 0xfa, 0xce, 0xde, 0xad, 0xbe, 0xef,
                    0xab, 0xad, 0xda, 0xd2},
    .iv          = {0xca, 0xfe, 0xba, 0xbe, 0xfa, 0xce, 0xdb, 0xad,
                    0xde, 0xca, 0xf8, 0x88},
    .tag         = {0x76, 0xfc, 0x6e, 0xce, 0x0f, 0x4e, 0x17, 0x68,
                    0xcd, 0xdf, 0x88, 0x53, 0xbb, 0x2d, 0x55, 0x1b},
    .authsize    = 20,
    .datasize    = 60,
    .tagsize     = 16,
    .ivsize      = 12
};

TestVector testVector;

GCM<AES128> *gcmaes128 = 0;
GCM<AES192> *gcmaes192 = 0;
GCM<AES256> *gcmaes256 = 0;
GCM<Speck> *gcmspeck = 0;
GCM<SpeckTiny> *gcmspecklm = 0;

byte buffer[128];

bool testCipher_N(AuthenticatedCipher *cipher, const struct TestVector *test, size_t inc)
{
    size_t posn, len;
    uint8_t tag[16];

    crypto_feed_watchdog();

    cipher->clear();
    if (!cipher->setKey(test->key, cipher->keySize())) {
        Serial.print("setKey ");
        return false;
    }
    if (!cipher->setIV(test->iv, test->ivsize)) {
        Serial.print("setIV ");
        return false;
    }

    memset(buffer, 0xBA, sizeof(buffer));

    for (posn = 0; posn < test->authsize; posn += inc) {
        len = test->authsize - posn;
        if (len > inc)
            len = inc;
        cipher->addAuthData(test->authdata + posn, len);
    }

    for (posn = 0; posn < test->datasize; posn += inc) {
        len = test->datasize - posn;
        if (len > inc)
            len = inc;
        cipher->encrypt(buffer + posn, test->plaintext + posn, len);
    }

    if (memcmp(buffer, test->ciphertext, test->datasize) != 0) {
        Serial.print(buffer[0], HEX);
        Serial.print("->");
        Serial.print(test->ciphertext[0], HEX);
        return false;
    }

    cipher->computeTag(tag, sizeof(tag));
    if (memcmp(tag, test->tag, sizeof(tag)) != 0) {
        Serial.print("computed wrong tag ... ");
        return false;
    }

    cipher->setKey(test->key, cipher->keySize());
    cipher->setIV(test->iv, test->ivsize);

    for (posn = 0; posn < test->authsize; posn += inc) {
        len = test->authsize - posn;
        if (len > inc)
            len = inc;
        cipher->addAuthData(test->authdata + posn, len);
    }

    for (posn = 0; posn < test->datasize; posn += inc) {
        len = test->datasize - posn;
        if (len > inc)
            len = inc;
        cipher->decrypt(buffer + posn, test->ciphertext + posn, len);
    }

    if (memcmp(buffer, test->plaintext, test->datasize) != 0)
        return false;

    if (!cipher->checkTag(tag, sizeof(tag))) {
        Serial.print("tag did not check ... ");
        return false;
    }

    return true;
}

void testCipher(AuthenticatedCipher *cipher, const struct TestVector *test)
{
    bool ok;

    memcpy_P(&testVector, test, sizeof(TestVector));
    test = &testVector;

    Serial.print(test->name);
    Serial.print(" ... ");

    ok  = testCipher_N(cipher, test, test->datasize);
    ok &= testCipher_N(cipher, test, 1);
    ok &= testCipher_N(cipher, test, 2);
    ok &= testCipher_N(cipher, test, 5);
    ok &= testCipher_N(cipher, test, 8);
    ok &= testCipher_N(cipher, test, 13);
    ok &= testCipher_N(cipher, test, 16);

    if (ok)
        Serial.println("Passed");
    else
        Serial.println("Failed");
}

void perfCipherSetKey(AuthenticatedCipher *cipher, const struct TestVector *test, const char *name)
{
    unsigned long start;
    unsigned long elapsed;
    int count;

    crypto_feed_watchdog();

    memcpy_P(&testVector, test, sizeof(TestVector));
    test = &testVector;

    Serial.print(name);
    Serial.print(" SetKey ... ");

    start = micros();
    for (count = 0; count < 1000; ++count) {
        cipher->setKey(test->key, cipher->keySize());
        cipher->setIV(test->iv, test->ivsize);
    }
    elapsed = micros() - start;

    Serial.print(elapsed / 1000.0);
    Serial.print("us per operation, ");
    Serial.print((1000.0 * 1000000.0) / elapsed);
    Serial.println(" per second");
}

void perfCipherEncrypt(AuthenticatedCipher *cipher, const struct TestVector *test, const char *name)
{
    unsigned long start;
    unsigned long elapsed;
    int count;

    crypto_feed_watchdog();

    memcpy_P(&testVector, test, sizeof(TestVector));
    test = &testVector;

    Serial.print(name);
    Serial.print(" Encrypt ... ");

    cipher->setKey(test->key, cipher->keySize());
    cipher->setIV(test->iv, test->ivsize);
    start = micros();
    for (count = 0; count < 500; ++count) {
        cipher->encrypt(buffer, buffer, 128);
    }
    elapsed = micros() - start;

    Serial.print(elapsed / (128.0 * 500.0));
    Serial.print("us per byte, ");
    Serial.print((128.0 * 500.0 * 1000000.0) / elapsed);
    Serial.println(" bytes per second");
}

void perfCipherDecrypt(AuthenticatedCipher *cipher, const struct TestVector *test, const char *name)
{
    unsigned long start;
    unsigned long elapsed;
    int count;

    crypto_feed_watchdog();

    memcpy_P(&testVector, test, sizeof(TestVector));
    test = &testVector;

    Serial.print(name);
    Serial.print(" Decrypt ... ");

    cipher->setKey(test->key, cipher->keySize());
    cipher->setIV(test->iv, test->ivsize);
    start = micros();
    for (count = 0; count < 500; ++count) {
        cipher->decrypt(buffer, buffer, 128);
    }
    elapsed = micros() - start;

    Serial.print(elapsed / (128.0 * 500.0));
    Serial.print("us per byte, ");
    Serial.print((128.0 * 500.0 * 1000000.0) / elapsed);
    Serial.println(" bytes per second");
}

void perfCipherAddAuthData(AuthenticatedCipher *cipher, const struct TestVector *test, const char *name)
{
    unsigned long start;
    unsigned long elapsed;
    int count;

    crypto_feed_watchdog();

    memcpy_P(&testVector, test, sizeof(TestVector));
    test = &testVector;

    Serial.print(name);
    Serial.print(" AddAuthData ... ");

    cipher->setKey(test->key, cipher->keySize());
    cipher->setIV(test->iv, test->ivsize);
    start = micros();
    memset(buffer, 0xBA, 128);
    for (count = 0; count < 500; ++count) {
        cipher->addAuthData(buffer, 128);
    }
    elapsed = micros() - start;

    Serial.print(elapsed / (128.0 * 500.0));
    Serial.print("us per byte, ");
    Serial.print((128.0 * 500.0 * 1000000.0) / elapsed);
    Serial.println(" bytes per second");
}

void perfCipherComputeTag(AuthenticatedCipher *cipher, const struct TestVector *test, const char *name)
{
    unsigned long start;
    unsigned long elapsed;
    int count;

    crypto_feed_watchdog();

    memcpy_P(&testVector, test, sizeof(TestVector));
    test = &testVector;

    Serial.print(name);
    Serial.print(" ComputeTag ... ");

    cipher->setKey(test->key, cipher->keySize());
    cipher->setIV(test->iv, test->ivsize);
    start = micros();
    for (count = 0; count < 1000; ++count) {
        cipher->computeTag(buffer, 16);
    }
    elapsed = micros() - start;

    Serial.print(elapsed / 1000.0);
    Serial.print("us per operation, ");
    Serial.print((1000.0 * 1000000.0) / elapsed);
    Serial.println(" per second");
}

void perfCipher(AuthenticatedCipher *cipher, const struct TestVector *test, const char *name)
{
    perfCipherSetKey(cipher, test, name);
    perfCipherEncrypt(cipher, test, name);
    perfCipherDecrypt(cipher, test, name);
    perfCipherAddAuthData(cipher, test, name);
    perfCipherComputeTag(cipher, test, name);
}

void setup()
{
    Serial.begin(9600);

    Serial.println();

#ifndef TEST_SPECK
    Serial.println("State Sizes:");
    Serial.print("GCM<AES128> ... ");
    Serial.println(sizeof(*gcmaes128));
    Serial.print("GCM<AES192> ... ");
    Serial.println(sizeof(*gcmaes192));
    Serial.print("GCM<AES256> ... ");
    Serial.println(sizeof(*gcmaes256));
    Serial.print("GCM<Speck> ... ");
    Serial.println(sizeof(*gcmspeck));
    Serial.print("GCM<SpeckTiny> ... ");
    Serial.println(sizeof(*gcmspecklm));
    Serial.println();
#endif

    Serial.println("Test Vectors:");
    gcmaes128 = new GCM<AES128>();
    testCipher(gcmaes128, &testVectorGCM1);
#ifndef TEST_SPECK
    testCipher(gcmaes128, &testVectorGCM2);
    testCipher(gcmaes128, &testVectorGCM3);
    testCipher(gcmaes128, &testVectorGCM4);
    testCipher(gcmaes128, &testVectorGCM5);
#endif
    delete gcmaes128;
    gcmaes192 = new GCM<AES192>();
    testCipher(gcmaes192, &testVectorGCM10);
    delete gcmaes192;
    gcmaes256 = new GCM<AES256>();
    testCipher(gcmaes256, &testVectorGCM16);
    delete gcmaes256;

    Serial.println();

    Serial.println("Performance Tests:");
#ifndef TEST_SPECK
    gcmaes128 = new GCM<AES128>();
    perfCipher(gcmaes128, &testVectorGCM1, testVectorGCM1.name);
    delete gcmaes128;
    gcmaes192 = new GCM<AES192>();
    perfCipher(gcmaes192, &testVectorGCM10, testVectorGCM10.name);
    delete gcmaes192;
    gcmaes256 = new GCM<AES256>();
    perfCipher(gcmaes256, &testVectorGCM16, testVectorGCM16.name);
    delete gcmaes256;
#endif
#if defined(TEST_SPECK) || !defined(__AVR__)
    gcmspeck = new GCM<Speck>();
    perfCipher(gcmspeck, &testVectorGCM16, "GCM-Speck-256");
    delete gcmspeck;
    gcmspecklm = new GCM<SpeckTiny>();
    perfCipher(gcmspecklm, &testVectorGCM16, "GCM-SpeckTiny-256");
    delete gcmspecklm;
#endif
}

void loop()
{
}
