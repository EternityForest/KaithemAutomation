
from src import kaithemobj,tagpoints

def civilTwilight():
    try:
        if kaithemobj.kaithem.isDark():
            return 1
        else:
            return 0
    except:
        return -1

twilightTag = tagpoints.Tag("/sky/civilTwilight")
twilightTag.min =-1
twilightTag.max = 1
twilightTag.interval = 60
twilightTag.description="Unless overridden, 1 if dark, else 0, -1 if no location is set"

def night():
    try:
        if kaithemobj.kaithem.isNight():
            return 1
        else:
            return 0
    except:
        return -1

nTag = tagpoints.Tag("/sky/night")
nTag.min =-1
nTag.max = 1
nTag.interval = 60
nTag.description="Unless overridden, 1 if night, else 0, -1 if no location is set"