#Copyright Daniel Black 2013
#This file is part of Kaithem Automation.

#Kaithem Automation is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Kaithem Automation is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

import time,pytz,datetime,re
from .config import config
from . import auth,pages

class DayOfWeek(str):
    """This class it a value object that will appear like a string but supports intelligent comparisions like Dow=='Thu' etc.
        supports upper ad lower case and abbreviations and numbers(monday=0).
        If you don't pass it a weekday day when initializing it it will default to today in local time
    
    """
    def __init__(self,day=""):
    
        #If no day supplied, default to today
        if day == "":
            day = time.localtime().tm_wday
            
        self.namestonumbers= {
                'Mon':0,'Monday':0,'M':0, 0:0,
                'Tue':1,'Tuesday':1, 'Tues':1,'Tu':1, 1:1,
                'Wed':2,'Wednesday':'2', 'W':2, 2:2,
                'Thu':3,"Thursday":3, 'Th':3,'Thurs':3,'Thur':3, 3:3,
                "Fri":4,'Friday':4, 4:4,
                'Sat':5,'Saturday':5, 5:5,
                'Sun':6,'Sunday':6,
                6:6,
               }
               
        self.numberstonames=[
                        ['Monday','Mon'],
                        ['Tuesday','Tue','Tu','Tues'],
                        ['Wednesday','Wed'],
                        ['Thursday','Thu','Th','Thurs','Thur'],
                        ['Friday','Fri'],
                        ['Saturday','Sat'],
                        ['Sunday','Sun']
                      ]
        try:
            if isinstance(day,str):
                day=day.capitalize()
            self.value = self.namestonumbers[day]
        except Exception as e:
            raise e#ValueError('Does not appear to be any valid day of the week')
     
    def __str__(self):
        return(self.numberstonames[self.value][0])
    
    def __int__(self):
        return self.value
     
    def __repr__(self):
         return(self.numberstonames[self.value][0])
     
    def __eq__(self,other):
         try:
             if isinstance(other,DayOfWeek):
                 if self.value == other.value:
                     return True
             
             if isinstance(other,str):
                 other=other.capitalize()
                 
             if self.namestonumbers[other] == self.value:
                 return True
             else:
                 return False
             
         except KeyError:
             raise RuntimeError("Invalid to compare day of week to " + repr(other))
         
class Month(str):
    """This class it a value object that will appear like a string but supports intelligent comparisions like Dow=='Thu' etc.
        supports upper ad lower case and abbreviations and numbers(monday=0).
        If you don't pass it a weekday day when initializing it it will default to today in local time
    
    """
    def __init__(self,month=None):
    
        #If no day supplied, default to today
        if month ==None:
            self.value = time.localtime().tm_mon
            
        self.namestonumbers= {
                "Jan":1, "January":1,
                "Feb":2, "February":2,
                "Mar":3, "March":3,
                "Apr":4, "April":4,
                "May":5,
                "Jun":6, "June":6,
                "Jul":7, "July":7,
                "Aug":8, "August":8,
                "Sep":9, "September":9,
                "Oct":10, "October":10,
                "Nov":11,"November":11,
                "Dec":12,"December":12,
                1:1,2:2,3:3,4:4, 5:5, 6:6,7:7,8:8,9:9,10:10,11:11,12:12
               }
               
        self.numberstonames=[
                             ["January"],["February"],["March"],["April"],["May"],["June"],["July"],["August"],
                             ["September"],['October'],['November'],['December']
                      ]
        try:
            if isinstance(month,str):
                self.value=month.capitalize()
            elif isinstance(month,int):
                self.value = month
            self.value = self.namestonumbers[self.value]
        except KeyError as e:
            raise ValueError('Does not appear to be any valid Month')
     
    def __str__(self):
        return(self.numberstonames[self.value][0])
    
    def __int__(self):
        return(self.value)
    
    def __repr__(self):
         return(self.numberstonames[self.value][0])
     
#     def __cmp__(self,other):
#          try:
#             if isinstance(other,Month):
#                 otherval = other.value
#             elif isinstance(other,str):
#                 other=other.capitalize()     
#                 otherval = self.namestonumbers[other]
#             else:
#                 otherval = other
#                 
#                 if self.value == otherval:
#                     return 0
#                 if self.value > otherval:
#                     return 1
#                 return -1
#             
#          except KeyError:
#             return -1
     
    def __eq__(self,other):
         try:
            if isinstance(other,Month):
                if self.value == other.value:
                    return True
                
            if isinstance(other,str):
                other=other.capitalize()
                 
            if self.namestonumbers[other] == self.value:
                 return True
            else:
                 return False
         except KeyError:
             return False
        
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
    

def formatTimeInterval(t,maxunits):
    """Take a length of time t in seconds, and return a nicely formatted string
    like "2 hours, 4 minutes, 12 seconds".
    maxunits is the maximum number of units to use in the string(7 will add a milliseconds field to times in years)
    
    """
    s = ""
    for i in sorted(time_as_seconds.items(),key= lambda x:x[1], reverse=True):
        if maxunits == 0:
            return s[:-2]
        x = t%i[1]
        b=(t-x)
        y=(t-x)/i[1]
        
        t = t-b
        if y>1:
            s += str(int(round(y))) + " " + i[0]+"s, "
            maxunits -=1
        elif y==1:
            s += str(int(round(y))) + " " + i[0]+", "
            maxunits -=1
    return s[:-2]
    e

def strToIntWithSIMultipliers(s):
    """Take a string of the form number[k|m|g] or just number and convert to an actual number
    '0'-> 0, '5k'->5000 etc"""
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

def siFormatNumber(number,digits=2):
    if number > 1000000000:
        return(str(round(number/1000000000,digits))+' G')
    if number > 1000000:
        return(str(round(number/1000000,digits))+' M')
    if number > 1000:
        return(str(round(number/1000,digits))+' K')
    
    if number < 0.00001:
        return(str(round(number*1000000000,digits))+' n')
    if number < 0.001:
        return(str(round(number*1000000,digits))+' u')
    if number < 0.01:
        return(str(round(number*1000,digits))+' m')
    
    return number



def strftime(*arg):
    tz = pytz.timezone(auth.getUserSetting(pages.getAcessingUser(),'timezone'))
    if arg:
        d = datetime.datetime.utcfromtimestamp(*arg).replace(tzinfo=pytz.utc)
    else:
        d = datetime.datetime.utcfromtimestamp(time.time()).replace(tzinfo=pytz.utc)
        
    return tz.normalize(d.astimezone(tz)).strftime(auth.getUserSetting(pages.getAcessingUser(),'strftime'))

    
    "Format a time according to the time-format option in the configuration file"
    return time.strftime(config['time-format'], *arg)
