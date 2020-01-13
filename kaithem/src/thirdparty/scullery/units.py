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

