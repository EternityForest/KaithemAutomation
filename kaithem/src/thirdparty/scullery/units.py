#Copyright Daniel Dunn 2020
#This file is part of Scullery.

#Scullery is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Scullery is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Scullery.  If not, see <http://www.gnu.org/licenses/>.


_ureg = None
#Units datafile.  All the units are all mixed together.  Every type of unit has to have a single base unit
#and everything else is defined in terms of that
units ={

    #Base unit of mass is grams
    "g": 1.0,
    "lb": 453.592,
    "oz": 28, 

    #Base unit of distance is meters
    "m": 1.0,
    "in": 0.0254,

    #Base unit of temperature is Kelvin
    "K": 1.0,
    #Offset unit. It is defined by two functions,the one to convert to the base an one to convert from
    "degC": (lambda x: x+273.15, lambda x: x-273.15),

    #Voltage/Current
    "A": 1,
    "V": 1
}

unitTypes={
     #Base unit of mass is grams
    "g":  "mass",
    "lb": "mass",
    "oz": "mass",

    #Base unit of distance is meters
    "m":  "length",
    "in": "length",

    #Base unit of temperature is Kelvin
    "K":    "temperature",
    #Offset unit. To convert FROM the base divide by the first and add the second number
    "degC": "temperature",
    
    "V": "voltage",
    "A": "current"
}

_prefixes = {"n":10**-9,"u":10**-6, "m":0.001, "k":1000,"M":1000000,"G":1000000000,"T":1000000000000}
def getUnitType(u):
    return unitTypes(u)

def parsePrefix(u):
    if u in units:
        return(units[u],1)
    elif u[0] in _prefixes and u[1:] in units:
        if not isinstance(units[u[1:]], (int, float)):
            raise ValueError("SI prefix not supported with nonlinear units")
        return (units[u[1:]], _prefixes[u[0]])
    
    raise KeyError("No such unit: "+u)

def defineUnit(unitname, multiplier, type, offset=0,base=None):
    """Define a new unit. The multiplier is how many of the base unit one step in the base unit new unit is worth. 
    Base defaults to 1, the global base unit.
    
    Multiplier can also be a tuple of two functions, frombase,tobase, that handle the conversions. 
    Function based units cannot be chained. You must define them in terms of the global default base
    
    """

    if base:
        z = units[base]
        if isinstance(z,(int,float)):
            multiplier*= z
        else:
            raise RuntimeError("Function-based units can only be defined directly in terms of the global base")
        
        if not isinstance(multiplier,(int,float)):
            raise RuntimeError("Function-based units can only be defined directly in terms of the global base")

    if isinstance(multiplier,(int,float)):
        multiplier = multiplier
    units[unitname]= multiplier
    unitTypes[unitname]= type

defineUnit("degF", (lambda x: (x+459.67) * (5/9),  lambda x: (x*(9/5))-459.67), "temperature")
defineUnit("ft", 12, "length", 0, "in")
defineUnit("mile",1609.344, "length")

defineUnit("m3/min",1, "flow")
defineUnit("cfm", 0.028316847, "flow")
defineUnit("gpm", 0.0037854118, "flow")

defineUnit("Pa", 1,"pressure")
defineUnit("psi", 6894.7573, "pressure")
defineUnit("ksi", 1000,"pressure",0,"psi")
defineUnit("mmHg",133.32237,"pressure")

def _loadPint():
    global _ureg
    if not _ureg:
        import pint 
        _ureg = pint.UnitRegistry()

def convert(v, fromUnit, toUnit):
    if fromUnit==toUnit:
        return v
    try:
        fr,frmul = parsePrefix(fromUnit)
        to,tomul = parsePrefix(toUnit)
    #Fallback to pint library
    except KeyError:
        if not _ureg:
            _loadPint()
        x = _ureg.Quantity(v, fromUnit)
        return x.to(toUnit).magnitude

    v*=frmul
    #Convert into the base unit
    if isinstance(fr, (float,int)):
        v=v*fr
    else:
       v = fr[0](v)


    #Convert from the base unit
    if isinstance(to, (float,int)):
        v=v/to
    else:
        v=to[1](v)
        
    return v/tomul


def siFormatNumber(number,digits=2):
    if number == 0:
        return "0"
    if number > 10**15:
        return(str(iround(number/1000000000000000.0,digits))+'P')
    if number > 10**12:
        return(str(iround(number/1000000000000.0,digits))+'T')
    if number > 1000000000:
        return(str(iround(number/1000000000.0,digits))+'G')
    if number > 1000000:
        return(str(iround(number/1000000.0,digits))+'M')
    if number > 1000:
        return(str(iround(number/1000.0,digits))+'K')
    if number < 10**-12:
        return(str(round(number*(10**-15),digits))+'f')
    if number < 10**-9:
        return(str(round(number*1000000000000.0,digits))+'p')
    if number <10**-6:
        return(str(iround(number*1000000000.0,digits))+'n')
    if number < 0.001:
        return(str(iround(number*1000000.0,digits))+'u')
    if number < 0.5:
        return(str(iround(number*1000.0,digits))+'m')
    return str(iround(number,digits))

time_as_seconds ={
'year' : 60*60*24*365,
#A "month" as commonly used is a vauge unit. is it 28 days? 30? 31?
#To solve that, I define it as 1/12th of a solar year.
'month' : 60*60*24*30.4368333333,
'week' : 60*60*24*7,
'day' : 60*60*24,
"hour" : 60*60,
"minute" : 60,
"second" : 1,
"millisecond" : 0.001,
"microsecond" : 0.000001,
"nanosecond"  : 0.000000001,
"picosecond"  : 0.000000000001,
"femtosecond"  :0.000000000000001,
}


time_as_seconds_abbr ={
'yr' : 60*60*24*365,
#A "month" as commonly used is a vauge unit. is it 28 days? 30? 31?
#To solve that, I define it as 1/12th of a solar year.
'month' : 60*60*24*30.4368333333,
'w' : 60*60*24*7,
'd' : 60*60*24,
"h" : 60*60,
"m" : 60,
"s" : 1,
"ms" : 0.001,
"us" : 0.000001,
"ns"  : 0.000000001,
"ps"  : 0.000000000001,
"fs"  :0.000000000000001,
}
def timeIntervalFromString(s):
    """Take a string like '10 hours' or 'five minutes 32 milliseconds'
    or '1 year and 1 day' to a number of seconds"""
    regex = r"([0-9]*)\D*?(year|month|week|day|hour|minute|second|millisecond)s?"
    r = re.compile(regex)
    m = r.finditer(s)
    total = 0
    for i in m:
        multiplier= time_as_seconds[i.group(2).strip()]
        number = float(i.group(1))
        total += number*multiplier
    return total


def formatTimeIntervallong(t,maunitss,clock=False):
    """Take a length of time t in seconds, and return a nicely formatted string
    like "2 hours, 4 minutes, 12 seconds".
    maunitss is the maximum number of units to use in the string(7 will add a milliseconds field to times in years)

    """
    if clock:
        frac = t%1
        t -= frac
        seconds = t%60
        t-= seconds
        minutes = (t-(int(t/3600)*3600))/60
        t -= t%3600
        hours= t/3600

        s = "%02d:%02d"%(hours,minutes)
        if maunitss>2:
            s+= ":%02d"%(seconds)
        if maunitss>3:
            #Adding 0.01 seems to help with some kind of obnoxious rounding bug thing. Prob a better way to do things.
            s+=":%03d"%(0.01+frac*1000)

        return s
    s = ""
    
    for i in sorted(time_as_seconds.items(),key= lambda x:x[1], reverse=True):
        if maunitss == 0:
            return s[:-2]
        x = t%i[1]
        b=(t-x)
        y=(t-x)/i[1]

        t = t-b
        if y>1:
            s += str(int(round(y))) + " " + i[0]+"s, "
            maunitss -=1
        elif y==1:
            s += str(int(round(y))) + " " + i[0]+", "
            maunitss -=1
    return s[:-2]

def formatTimeIntervalabbr(t,maunitss,clock=False):
    """Take a length of time t in seconds, and return a nicely formatted string
    like "2 hours, 4 minutes, 12 seconds".
    maunitss is the maximum number of units to use in the string(7 will add a milliseconds field to times in years)

    """
    if clock:
        frac = t%1
        t -= frac
        seconds = t%60
        t-= seconds
        minutes = (t-(int(t/3600)*3600))/60
        t -= t%3600
        hours= t/3600

        s = "%02d:%02d"%(hours,minutes)
        if maunitss>2:
            s+= ":%02d"%(seconds)
        if maunitss>3:
            #Adding 0.01 seems to help with some kind of obnoxious rounding bug thing. Prob a better way to do things.
            s+=":%03d"%(0.01+frac*1000)

        return s
    s = ""
    for i in sorted(time_as_seconds_abbr.items(),key= lambda x:x[1], reverse=True):
        if maunitss == 0:
            return s[:-1]
        x = t%i[1]
        b=(t-x)
        y=(t-x)/i[1]

        t = t-b
        if y>1: 
            if i[0]=="month":
                s += str(int(round(y))) + i[0]+"s "
            else:
                s += str(int(round(y))) + i[0]+" "
            maunitss -=1
        elif y:
            s += str(int(round(y))) + i[0]+" "
            maunitss -=1
    return s[:-1]

formatTimeInterval = formatTimeIntervalabbr

def strToIntWithSIMultipliers(s):
    """Take a string of the form number[k|m|g] or just number and convert to an actual number
    '0'-> 0, '5k'->5000 etc. Does not do division!!!! m is mega not milli!!!"""
    s = s.lower()
    #This piece of code interprets a string like 89m or 50k as a number like 89 millon or 50,000
    if s.endswith('k'):
        return int(s[:-1])*1000
    elif s.endswith('m'):
        return int(s[:-1])*1000000
    elif s.endswith('g'):
        return int(s[:-1])*1000000000
    else:
        return int(s[:-1])

def iround(number,digits):
    if (number-int(number)==0) or (digits==0):
        return int(number)
    else:
        return round(number,digits)