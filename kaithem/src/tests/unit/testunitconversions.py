import common
import src.unitsofmeasure
import src.random

x = unitsofmeasure.timeIntervalFromString("1 minute")
if not x == 60:
    common.fail(x)
    
x = unitsofmeasure.timeIntervalFromString("1 minute 10 seconds")
if not x == 70:
    common.fail(x)
    
x = unitsofmeasure.timeIntervalFromString("1 minute and 10 secondsbutwithanextra42milliseconds")
if not x == 70.042:
    common.fail(x)
    
if not unitsofmeasure.formatTimeInterval(60.1,2) == '1 minute, 100 milliseconds':
    common.fail()
    
if not unitsofmeasure.strToIntWithSIMultipliers('10k') ==10000:
    common.fail()

common.suceed("Success testing unitsofmeasure.py")
    