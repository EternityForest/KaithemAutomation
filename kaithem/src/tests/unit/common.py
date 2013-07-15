import os,sys
dn = os.path.dirname(os.path.realpath(__file__))

sys.path.append(os.path.join(dn,"../.."))

class UtterFailure(Exception):
    pass
    

def fail(x):
    raise UtterFailure(x)
    
    
