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
This example runs tests on the GHASH implementation to verify correct behaviour.
*/

#include <Crypto.h>
#include <GHASH.h>
#include <string.h>

// Test vectors from Appendix B of:
// http://csrc.nist.gov/groups/ST/toolkit/BCM/documents/proposedmodes/gcm/gcm-revised-spec.pdf

struct TestVector
{
    const char *name;
    uint8_t key[16];
    uint8_t data[112];
    size_t dataLen;
    uint8_t hash[16];
};

static TestVector const testVectorGHASH_1 = {
    .name     = "GHASH #1",
    .key      = {0x66, 0xe9, 0x4b, 0xd4, 0xef, 0x8a, 0x2c, 0x3b,
                 0x88, 0x4c, 0xfa, 0x59, 0xca, 0x34, 0x2b, 0x2e},
    .data     = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    .dataLen  = 16,
    .hash     = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}
};
static TestVector const testVectorGHASH_2 = {
    .name     = "GHASH #2",
    .key      = {0x66, 0xe9, 0x4b, 0xd4, 0xef, 0x8a, 0x2c, 0x3b,
                 0x88, 0x4c, 0xfa, 0x59, 0xca, 0x34, 0x2b, 0x2e},
    .data     = {0x03, 0x88, 0xda, 0xce, 0x60, 0xb6, 0xa3, 0x92,
                 0xf3, 0x28, 0xc2, 0xb9, 0x71, 0xb2, 0xfe, 0x78,
                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80},
    .dataLen  = 32,
    .hash     = {0xf3, 0x8c, 0xbb, 0x1a, 0xd6, 0x92, 0x23, 0xdc,
                 0xc3, 0x45, 0x7a, 0xe5, 0xb6, 0xb0, 0xf8, 0x85}
};
static TestVector const testVectorGHASH_3 = {
    .name     = "GHASH #3",
    .key      = {0xb8, 0x3b, 0x53, 0x37, 0x08, 0xbf, 0x53, 0x5d,
                 0x0a, 0xa6, 0xe5, 0x29, 0x80, 0xd5, 0x3b, 0x78},
    .data     = {0x42, 0x83, 0x1e, 0xc2, 0x21, 0x77, 0x74, 0x24,
                 0x4b, 0x72, 0x21, 0xb7, 0x84, 0xd0, 0xd4, 0x9c,
                 0xe3, 0xaa, 0x21, 0x2f, 0x2c, 0x02, 0xa4, 0xe0,
                 0x35, 0xc1, 0x7e, 0x23, 0x29, 0xac, 0xa1, 0x2e,
                 0x21, 0xd5, 0x14, 0xb2, 0x54, 0x66, 0x93, 0x1c,
                 0x7d, 0x8f, 0x6a, 0x5a, 0xac, 0x84, 0xaa, 0x05,
                 0x1b, 0xa3, 0x0b, 0x39, 0x6a, 0x0a, 0xac, 0x97,
                 0x3d, 0x58, 0xe0, 0x91, 0x47, 0x3f, 0x59, 0x85,
                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00},
    .dataLen  = 80,
    .hash     = {0x7f, 0x1b, 0x32, 0xb8, 0x1b, 0x82, 0x0d, 0x02,
                 0x61, 0x4f, 0x88, 0x95, 0xac, 0x1d, 0x4e, 0xac}
};
static TestVector const testVectorGHASH_4 = {
    .name     = "GHASH #4",
    .key      = {0xb8, 0x3b, 0x53, 0x37, 0x08, 0xbf, 0x53, 0x5d,
                 0x0a, 0xa6, 0xe5, 0x29, 0x80, 0xd5, 0x3b, 0x78},
    .data     = {0xfe, 0xed, 0xfa, 0xce, 0xde, 0xad, 0xbe, 0xef,
                 0xfe, 0xed, 0xfa, 0xce, 0xde, 0xad, 0xbe, 0xef,
                 0xab, 0xad, 0xda, 0xd2, 0x00, 0x00, 0x00, 0x00,
                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                 0x42, 0x83, 0x1e, 0xc2, 0x21, 0x77, 0x74, 0x24,
                 0x4b, 0x72, 0x21, 0xb7, 0x84, 0xd0, 0xd4, 0x9c,
                 0xe3, 0xaa, 0x21, 0x2f, 0x2c, 0x02, 0xa4, 0xe0,
                 0x35, 0xc1, 0x7e, 0x23, 0x29, 0xac, 0xa1, 0x2e,
                 0x21, 0xd5, 0x14, 0xb2, 0x54, 0x66, 0x93, 0x1c,
                 0x7d, 0x8f, 0x6a, 0x5a, 0xac, 0x84, 0xaa, 0x05,
                 0x1b, 0xa3, 0x0b, 0x39, 0x6a, 0x0a, 0xac, 0x97,
                 0x3d, 0x58, 0xe0, 0x91, 0x00, 0x00, 0x00, 0x00,
                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xa0,
                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0xe0},
    .dataLen  = 112,
    .hash     = {0x69, 0x8e, 0x57, 0xf7, 0x0e, 0x6e, 0xcc, 0x7f,
                 0xd9, 0x46, 0x3b, 0x72, 0x60, 0xa9, 0xae, 0x5f}
};

GHASH ghash;

byte buffer[128];

bool testGHASH_N(GHASH *hash, const struct TestVector *test, size_t inc)
{
    size_t size = test->dataLen;
    size_t posn, len;

    hash->reset(test->key);

    for (posn = 0; posn < size; posn += inc) {
        len = size - posn;
        if (len > inc)
            len = inc;
        hash->update(test->data + posn, len);
    }

    hash->finalize(buffer, 16);

    return !memcmp(buffer, test->hash, 16);
}

void testGHASH(GHASH *hash, const struct TestVector *test)
{
    bool ok;

    Serial.print(test->name);
    Serial.print(" ... ");

    ok  = testGHASH_N(hash, test, test->dataLen);
    ok &= testGHASH_N(hash, test, 1);
    ok &= testGHASH_N(hash, test, 2);
    ok &= testGHASH_N(hash, test, 5);
    ok &= testGHASH_N(hash, test, 8);
    ok &= testGHASH_N(hash, test, 13);
    ok &= testGHASH_N(hash, test, 16);
    ok &= testGHASH_N(hash, test, 24);
    ok &= testGHASH_N(hash, test, 63);
    ok &= testGHASH_N(hash, test, 64);

    if (ok)
        Serial.println("Passed");
    else
        Serial.println("Failed");
}

void perfGHASH(GHASH *hash)
{
    unsigned long start;
    unsigned long elapsed;
    int count;

    Serial.print("Hashing ... ");

    for (size_t posn = 0; posn < sizeof(buffer); ++posn)
        buffer[posn] = (uint8_t)posn;

    hash->reset(testVectorGHASH_1.key);
    start = micros();
    for (count = 0; count < 200; ++count) {
        hash->update(buffer, sizeof(buffer));
    }
    elapsed = micros() - start;

    Serial.print(elapsed / (sizeof(buffer) * 200.0));
    Serial.print("us per byte, ");
    Serial.print((sizeof(buffer) * 200.0 * 1000000.0) / elapsed);
    Serial.println(" bytes per second");
}

void perfGHASHSetKey(GHASH *hash)
{
    unsigned long start;
    unsigned long elapsed;
    int count;

    Serial.print("Set Key ... ");

    start = micros();
    for (count = 0; count < 1000; ++count) {
        hash->reset(testVectorGHASH_1.key);
    }
    elapsed = micros() - start;

    Serial.print(elapsed / 1000.0);
    Serial.print("us per op, ");
    Serial.print((1000.0 * 1000000.0) / elapsed);
    Serial.println(" ops per second");
}

void perfGHASHFinalize(GHASH *hash)
{
    unsigned long start;
    unsigned long elapsed;
    int count;

    Serial.print("Finalize ... ");

    hash->reset(testVectorGHASH_1.key);
    hash->update("abc", 3);
    start = micros();
    for (count = 0; count < 1000; ++count) {
        hash->finalize(buffer, 16);
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

    Serial.print("State Size ... ");
    Serial.println(sizeof(GHASH));
    Serial.println();

    Serial.println("Test Vectors:");
    testGHASH(&ghash, &testVectorGHASH_1);
    testGHASH(&ghash, &testVectorGHASH_2);
    testGHASH(&ghash, &testVectorGHASH_3);
    testGHASH(&ghash, &testVectorGHASH_4);

    Serial.println();

    Serial.println("Performance Tests:");
    perfGHASH(&ghash);
    perfGHASHSetKey(&ghash);
    perfGHASHFinalize(&ghash);
}

void loop()
{
}
