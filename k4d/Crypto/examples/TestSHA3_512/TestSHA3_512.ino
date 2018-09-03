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
This example runs tests on the SHA3_512 implementation to verify
correct behaviour.
*/

#include <Crypto.h>
#include <SHA3.h>
#include <string.h>

#define DATA_SIZE 72
#define HASH_SIZE 64
#define BLOCK_SIZE 72

struct TestHashVector
{
    const char *name;
    uint8_t data[DATA_SIZE];
    uint8_t dataSize;
    uint8_t hash[HASH_SIZE];
};

// Some test vectors from https://github.com/gvanas/KeccakCodePackage
static TestHashVector const testVectorSHA3_512_1 = {
    "SHA3-512 #1",
    {0},
    0,
    {0xA6, 0x9F, 0x73, 0xCC, 0xA2, 0x3A, 0x9A, 0xC5,
     0xC8, 0xB5, 0x67, 0xDC, 0x18, 0x5A, 0x75, 0x6E,
     0x97, 0xC9, 0x82, 0x16, 0x4F, 0xE2, 0x58, 0x59,
     0xE0, 0xD1, 0xDC, 0xC1, 0x47, 0x5C, 0x80, 0xA6,
     0x15, 0xB2, 0x12, 0x3A, 0xF1, 0xF5, 0xF9, 0x4C,
     0x11, 0xE3, 0xE9, 0x40, 0x2C, 0x3A, 0xC5, 0x58,
     0xF5, 0x00, 0x19, 0x9D, 0x95, 0xB6, 0xD3, 0xE3,
     0x01, 0x75, 0x85, 0x86, 0x28, 0x1D, 0xCD, 0x26}
};
static TestHashVector const testVectorSHA3_512_2 = {
    "SHA3-512 #2",
    {0x1F, 0x87, 0x7C},
    3,
    {0xCB, 0x20, 0xDC, 0xF5, 0x49, 0x55, 0xF8, 0x09,
     0x11, 0x11, 0x68, 0x8B, 0xEC, 0xCE, 0xF4, 0x8C,
     0x1A, 0x2F, 0x0D, 0x06, 0x08, 0xC3, 0xA5, 0x75,
     0x16, 0x37, 0x51, 0xF0, 0x02, 0xDB, 0x30, 0xF4,
     0x0F, 0x2F, 0x67, 0x18, 0x34, 0xB2, 0x2D, 0x20,
     0x85, 0x91, 0xCF, 0xAF, 0x1F, 0x5E, 0xCF, 0xE4,
     0x3C, 0x49, 0x86, 0x3A, 0x53, 0xB3, 0x22, 0x5B,
     0xDF, 0xD7, 0xC6, 0x59, 0x1B, 0xA7, 0x65, 0x8B}
};
static TestHashVector const testVectorSHA3_512_3 = {
    "SHA3-512 #3",
    {0xE2, 0x61, 0x93, 0x98, 0x9D, 0x06, 0x56, 0x8F,
     0xE6, 0x88, 0xE7, 0x55, 0x40, 0xAE, 0xA0, 0x67,
     0x47, 0xD9, 0xF8, 0x51},
    20,
    {0x19, 0x1C, 0xEF, 0x1C, 0x6A, 0xA0, 0x09, 0xB1,
     0xAB, 0xA6, 0x74, 0xBE, 0x2B, 0x3F, 0x0D, 0xA4,
     0x18, 0xFD, 0xF9, 0xE6, 0xA7, 0xEC, 0xF2, 0xBE,
     0x42, 0xAC, 0x14, 0xF7, 0xD6, 0xE0, 0x73, 0x31,
     0x42, 0x51, 0x33, 0xA8, 0x3B, 0x4E, 0x01, 0x61,
     0xCC, 0x7D, 0xEB, 0xF9, 0xDC, 0xD7, 0xFE, 0x37,
     0x87, 0xDC, 0xB6, 0x62, 0x2A, 0x38, 0x47, 0x51,
     0x89, 0xED, 0xFE, 0x1D, 0xE6, 0xB0, 0x53, 0xD6}
};
static TestHashVector const testVectorSHA3_512_4 = {
    "SHA3-512 #4",
    {0x13, 0xBD, 0x28, 0x11, 0xF6, 0xED, 0x2B, 0x6F,
     0x04, 0xFF, 0x38, 0x95, 0xAC, 0xEE, 0xD7, 0xBE,
     0xF8, 0xDC, 0xD4, 0x5E, 0xB1, 0x21, 0x79, 0x1B,
     0xC1, 0x94, 0xA0, 0xF8, 0x06, 0x20, 0x6B, 0xFF,
     0xC3, 0xB9, 0x28, 0x1C, 0x2B, 0x30, 0x8B, 0x1A,
     0x72, 0x9C, 0xE0, 0x08, 0x11, 0x9D, 0xD3, 0x06,
     0x6E, 0x93, 0x78, 0xAC, 0xDC, 0xC5, 0x0A, 0x98,
     0xA8, 0x2E, 0x20, 0x73, 0x88, 0x00, 0xB6, 0xCD,
     0xDB, 0xE5, 0xFE, 0x96, 0x94, 0xAD, 0x6D},
    71,
    {0xDE, 0xF4, 0xAB, 0x6C, 0xDA, 0x88, 0x39, 0x72,
     0x9A, 0x03, 0xE0, 0x00, 0x84, 0x66, 0x04, 0xB1,
     0x7F, 0x03, 0xC5, 0xD5, 0xD7, 0xEC, 0x23, 0xC4,
     0x83, 0x67, 0x0A, 0x13, 0xE1, 0x15, 0x73, 0xC1,
     0xE9, 0x34, 0x7A, 0x63, 0xEC, 0x69, 0xA5, 0xAB,
     0xB2, 0x13, 0x05, 0xF9, 0x38, 0x2E, 0xCD, 0xAA,
     0xAB, 0xC6, 0x85, 0x0F, 0x92, 0x84, 0x0E, 0x86,
     0xF8, 0x8F, 0x4D, 0xAB, 0xFC, 0xD9, 0x3C, 0xC0}
};
static TestHashVector const testVectorSHA3_512_5 = {
    "SHA3-512 #5",
    {0x1E, 0xED, 0x9C, 0xBA, 0x17, 0x9A, 0x00, 0x9E,
     0xC2, 0xEC, 0x55, 0x08, 0x77, 0x3D, 0xD3, 0x05,
     0x47, 0x7C, 0xA1, 0x17, 0xE6, 0xD5, 0x69, 0xE6,
     0x6B, 0x5F, 0x64, 0xC6, 0xBC, 0x64, 0x80, 0x1C,
     0xE2, 0x5A, 0x84, 0x24, 0xCE, 0x4A, 0x26, 0xD5,
     0x75, 0xB8, 0xA6, 0xFB, 0x10, 0xEA, 0xD3, 0xFD,
     0x19, 0x92, 0xED, 0xDD, 0xEE, 0xC2, 0xEB, 0xE7,
     0x15, 0x0D, 0xC9, 0x8F, 0x63, 0xAD, 0xC3, 0x23,
     0x7E, 0xF5, 0x7B, 0x91, 0x39, 0x7A, 0xA8, 0xA7},
    72,
    {0xA3, 0xE1, 0x68, 0xB0, 0xD6, 0xC1, 0x43, 0xEE,
     0x9E, 0x17, 0xEA, 0xE9, 0x29, 0x30, 0xB9, 0x7E,
     0x66, 0x00, 0x35, 0x6B, 0x73, 0xAE, 0xBB, 0x5D,
     0x68, 0x00, 0x5D, 0xD1, 0xD0, 0x74, 0x94, 0x45,
     0x1A, 0x37, 0x05, 0x2F, 0x7B, 0x39, 0xFF, 0x03,
     0x0C, 0x1A, 0xE1, 0xD7, 0xEF, 0xC4, 0xE0, 0xC3,
     0x66, 0x7E, 0xB7, 0xA7, 0x6C, 0x62, 0x7E, 0xC1,
     0x43, 0x54, 0xC4, 0xF6, 0xA7, 0x96, 0xE2, 0xC6}
};

SHA3_512 sha3_512;

byte buffer[128];

bool testHash_N(Hash *hash, const struct TestHashVector *test, size_t inc)
{
    size_t size = test->dataSize;
    size_t posn, len;
    uint8_t value[HASH_SIZE];

    hash->reset();
    for (posn = 0; posn < size; posn += inc) {
        len = size - posn;
        if (len > inc)
            len = inc;
        hash->update(test->data + posn, len);
    }
    hash->finalize(value, sizeof(value));
    if (memcmp(value, test->hash, sizeof(value)) != 0)
        return false;

    return true;
}

void testHash(Hash *hash, const struct TestHashVector *test)
{
    bool ok;

    Serial.print(test->name);
    Serial.print(" ... ");

    ok  = testHash_N(hash, test, test->dataSize);
    ok &= testHash_N(hash, test, 1);
    ok &= testHash_N(hash, test, 2);
    ok &= testHash_N(hash, test, 5);
    ok &= testHash_N(hash, test, 8);
    ok &= testHash_N(hash, test, 13);
    ok &= testHash_N(hash, test, 16);
    ok &= testHash_N(hash, test, 24);
    ok &= testHash_N(hash, test, 63);
    ok &= testHash_N(hash, test, 64);

    if (ok)
        Serial.println("Passed");
    else
        Serial.println("Failed");
}

void perfHash(Hash *hash)
{
    unsigned long start;
    unsigned long elapsed;
    int count;

    Serial.print("Hashing ... ");

    for (size_t posn = 0; posn < sizeof(buffer); ++posn)
        buffer[posn] = (uint8_t)posn;

    hash->reset();
    start = micros();
    for (count = 0; count < 500; ++count) {
        hash->update(buffer, sizeof(buffer));
    }
    elapsed = micros() - start;

    Serial.print(elapsed / (sizeof(buffer) * 500.0));
    Serial.print("us per byte, ");
    Serial.print((sizeof(buffer) * 500.0 * 1000000.0) / elapsed);
    Serial.println(" bytes per second");
}

// Very simple method for hashing a HMAC inner or outer key.
void hashKey(Hash *hash, const uint8_t *key, size_t keyLen, uint8_t pad)
{
    size_t posn;
    uint8_t buf;
    uint8_t result[HASH_SIZE];
    if (keyLen <= BLOCK_SIZE) {
        hash->reset();
        for (posn = 0; posn < BLOCK_SIZE; ++posn) {
            if (posn < keyLen)
                buf = key[posn] ^ pad;
            else
                buf = pad;
            hash->update(&buf, 1);
        }
    } else {
        hash->reset();
        hash->update(key, keyLen);
        hash->finalize(result, HASH_SIZE);
        hash->reset();
        for (posn = 0; posn < BLOCK_SIZE; ++posn) {
            if (posn < HASH_SIZE)
                buf = result[posn] ^ pad;
            else
                buf = pad;
            hash->update(&buf, 1);
        }
    }
}

void testHMAC(Hash *hash, size_t keyLen)
{
    uint8_t result[HASH_SIZE];

    Serial.print("HMAC-SHA3-512 keysize=");
    Serial.print(keyLen);
    Serial.print(" ... ");

    // Construct the expected result with a simple HMAC implementation.
    memset(buffer, (uint8_t)keyLen, keyLen);
    hashKey(hash, buffer, keyLen, 0x36);
    memset(buffer, 0xBA, sizeof(buffer));
    hash->update(buffer, sizeof(buffer));
    hash->finalize(result, HASH_SIZE);
    memset(buffer, (uint8_t)keyLen, keyLen);
    hashKey(hash, buffer, keyLen, 0x5C);
    hash->update(result, HASH_SIZE);
    hash->finalize(result, HASH_SIZE);

    // Now use the library to compute the HMAC.
    hash->resetHMAC(buffer, keyLen);
    memset(buffer, 0xBA, sizeof(buffer));
    hash->update(buffer, sizeof(buffer));
    memset(buffer, (uint8_t)keyLen, keyLen);
    hash->finalizeHMAC(buffer, keyLen, buffer, HASH_SIZE);

    // Check the result.
    if (!memcmp(result, buffer, HASH_SIZE))
        Serial.println("Passed");
    else
        Serial.println("Failed");
}

void perfFinalize(Hash *hash)
{
    unsigned long start;
    unsigned long elapsed;
    int count;

    Serial.print("Finalizing ... ");

    hash->reset();
    hash->update("abc", 3);
    start = micros();
    for (count = 0; count < 1000; ++count) {
        hash->finalize(buffer, hash->hashSize());
    }
    elapsed = micros() - start;

    Serial.print(elapsed / 1000.0);
    Serial.print("us per op, ");
    Serial.print((1000.0 * 1000000.0) / elapsed);
    Serial.println(" ops per second");
}

void setup()
{
    Serial.begin(9600);

    Serial.println();

    Serial.print("State Size ...");
    Serial.println(sizeof(SHA3_512));
    Serial.println();

    Serial.println("Test Vectors:");
    testHash(&sha3_512, &testVectorSHA3_512_1);
    testHash(&sha3_512, &testVectorSHA3_512_2);
    testHash(&sha3_512, &testVectorSHA3_512_3);
    testHash(&sha3_512, &testVectorSHA3_512_4);
    testHash(&sha3_512, &testVectorSHA3_512_5);
    testHMAC(&sha3_512, (size_t)0);
    testHMAC(&sha3_512, 1);
    testHMAC(&sha3_512, HASH_SIZE);
    testHMAC(&sha3_512, BLOCK_SIZE);
    testHMAC(&sha3_512, BLOCK_SIZE + 1);
    testHMAC(&sha3_512, sizeof(buffer));

    Serial.println();

    Serial.println("Performance Tests:");
    perfHash(&sha3_512);
    perfFinalize(&sha3_512);
}

void loop()
{
}
