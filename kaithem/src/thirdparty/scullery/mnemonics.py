import hashlib, struct,os

mnemonic_wordlist = [s.strip() for s in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'words_mnemonic.txt'))]

def memorableBlakeHash(x, num=3, separator=""):
    "Use the diceware list to encode a blake hash of x. This IS meant to be secure"
    o = ""

    if isinstance(x, str):
        x = x.encode("utf8")
    
    x = hashlib.blake2b(x).digest()

    for i in range(num):
        # 4096 is an even divisor of 2**16
        n = struct.unpack("<H",x[:2])[0]%4096
        o+= mnemonic_wordlist[n] + separator
        x=x[2:]   
    return o[:-len(separator)] if separator else o