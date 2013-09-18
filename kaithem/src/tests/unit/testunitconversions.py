import common
import src.unitsofmeasure as unitsofmeasure
import random

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

x = unitsofmeasure.DayOfWeek("Tuesday")
if not x == 1:
    common.fail()
    
if not x == 'tue':
    common.fail()
    
if not x == 'Tuesday':
    common.fail()
    
if  x == 'Monday':
    common.fail()

if not x == unitsofmeasure.DayOfWeek("Tuesday"):
    common.fail()
    
x = unitsofmeasure.Month("May")

if not x == 5:
    common.fail()
    
if not x == unitsofmeasure.Month(5):
    common.fail()
    
common.suceed("Success testing unitsofmeasure.py")
    
