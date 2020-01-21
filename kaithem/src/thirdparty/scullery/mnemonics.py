import hashlib, struct,os

wordlist = [s.strip() for s in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'words_mnemonic.txt'))]

def memorableBlakeHash(x, num=3, separator=""):
    "Use the diceware list to encode a blake hash of x. This IS meant to be secure-ish(For long enough hashes)"
    o = ""

    if isinstance(x, str):
        x = x.encode("utf8")
    
    hash = hashlib.blake2b(x).digest()

    x=hash

    for i in range(num):
        # 1024 is an even divisor of 2**16
        n = struct.unpack("<H",x[:2])[0]
        
        #We are going to rehash here, to avoid any modulo bias
        while n>2**16 - len(wordlist):
            hash = hashlib.blake2b(hash).digest()
            x=hash
            n = struct.unpack("<H",x[:2])[0]

        n = n%len(wordlist)

        o+= wordlist[n] + separator
        x=x[2:]   
    return o[:-len(separator)] if separator else o
