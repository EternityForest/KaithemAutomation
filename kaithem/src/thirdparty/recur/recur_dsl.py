#COPYRIGHT (c) 2016 Daniel Dunn

#GNU GENERAL PUBLIC LICENSE
#   Version 3, 29 June 2007

#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.

#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with this program.  If not, see <http://www.gnu.org/licenses/>.

from . import recur,recur_parser
import datetime,pytz

p = recur_parser.parser

def parseDateTimeWithYearWithDefaults(s):
    "This accepts lots and lots of default options for no real reason other than to handle the starting at alignments"
    t = s.time
    d = s.date
    #Handles things like every 2 weeks starting on monday
    if s.weekday:
        return datetime.datetime.fromordinal(1+parseWeekday(s.weekday))
    return datetime.datetime(
     year=int(d.year) if d and d.year else 1,
     month=parseMonth(d.month) if d and d.month else 1,
     day= int(d.dayofmonth) if d and d.dayofmonth else 1,
     minute=int(t.minute) if t and t.minute else 0,
     hour = int(t.hour) if t and t.hour else 0,
     second=int(t.second) if t and t.second else 0,
     microsecond=int(t.millisecond) if t and t.millisecond else 0)

def parseOrdinal(s):
    "Given either an int or a string like '1', '1st','10th', etc; return an int"
    o = {'other':2,"first":1,"1st":1,"second":2,"2nd":2,"third":3,"3rd":3, 'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
    if s in o:
        return o[s]
    if s.endswith("th"):
        return(int(s[:-2]))
    return(int(s))

intervals = {
'week': 7*24*60*60,
'weeks': 7*24*60*60,

'day': 24*60*60,
'days': 24*60*60,

'hour': 60*60,
'hours': 60*60,

'minute': 60,
'minutes': 60,

'second': 1,
'seconds': 1
}
def parseTime(s):
    "Given the AST for a strng like 4:45pm, return a datetime.time"
    if s.predefined == "midnight":
      return datetime.time(0,0,0)
    if s.predefined== "noon":
      return datetime.time(12,0,0)
    try:
        return datetime.time(
        int(s.hour)+ (12 if s.ampm in ['PM',"pm"] else 0), int(s.minute) if s.minute else 0, int(s.second) if s.second else 0, s.ms*1000 if s.ms else 0)
    except Exception as e:
        raise
        
def parseTimes(s):
    return [parseTime(time) for time in s['times']]
    
def parseWeekday(s):
    try:
        return{
        "mon":0, "monday":0,
        "tue":1, "tuesday":1,
        "wed":2, "wednesday":2,
        "thu": 3, "thurs": 3,"thursday":3,
        "fri":4, "friday":4,
        'sat':5,"saturday":5,
        "sun":6,"sunday":6
        }[s.lower()]
    except:
        raise ValueError(s+" is not a valid weekday")

def parseMonth(s):
    return{
    "jan":1, "january":1,
    "feb":2, "february":2,
    "mar":3, "march":3,
    "apr":4, "april":1,
    "may":5,
    "jun":6, "june":6,
    "jul":7, "july":7,
    "aug":8, "august":8,
    "sep":9, "september":9,
    "oct":10, "october":10,
    "nov":11, "november":11,
    "dec":12, "december":12
    }[s.lower()]

class semantics():
    "Each function here handles a rule in the PEG. Rules are handled bottom up"

    def syntax_error(self,ast):
        raise ValueError("Unexpected token[s]:" + str(ast))

    def nthweekdayconstraint(self, ast):
        return recur.NthWeekdayConstraint(parseOrdinal(ast[0]),parseWeekday(ast[1]))

    def for_statement(self,ast):
        if ast.get("for",None):
            return recur.ForConstraint(ast['c'], float(float(ast['for'][0])*intervals[ast['for'][1]]) )
        if ast.get("for_",None):
            return recur.ForConstraint(ast['c'], float(float(ast['for_'][0])*intervals[ast['for_'][1]]) )
        return ast['c']
  
    def nintervalconstraint(self, ast):
        n = parseOrdinal(ast[1])
        i = ast[2]
        return {
        "minute" : recur.minutely,
        "minutes" : recur.minutely,

        "hour" : recur.hourly,
        "hours" : recur.hourly,

        "day" : recur.daily,
        "days" : recur.daily,

        "second" : recur.secondly,
        "seconds" : recur.secondly,

        "month" : recur.monthly,
        "months" : recur.monthly,

        "year" : recur.yearly,
        "years" : recur.yearly,

        "week": recur.weekly,
        "weeks": recur.weekly
        }[i](n)

    def intervalconstraint(self, ast):
        n = 1
        i = ast[1]
        return {
        "minute" : recur.minutely,
        "minutes" : recur.minutely,

        "hour" : recur.hourly,
        "hours" : recur.hourly,

        "day" : recur.daily,
        "days" : recur.daily,

        "second" : recur.secondly,
        "seconds" : recur.secondly,

        "month" : recur.monthly,
        "months" : recur.monthly,

        "year" : recur.yearly,
        "years" : recur.yearly,

        "week": recur.weekly,
        "weeks": recur.weekly
        }[i](n)

    def startingat(self,ast):
        x = parseDateTimeWithYearWithDefaults(ast)
        #Hack, I don't know why this is running twice for only one starting at statement.
        if hasattr(self,'align') and not self.align == x:
            raise ValueError("Cannot have multiple alignment points in a string, already set to "+str(self.align))
        self.align = x
        return recur.startingat(self.align)
        
    def timezone(self,ast):
        self.tz = ast


    def constraint_list(self, ast):
        x = ast
        c = x.pop()
        while x:
            y = x.pop()
            if y:
                c = c & y
        return c
        
    def for_statements(self, ast):
        x = ast['and']
        #I have no clue what is going on here
        if x==None:
            x=ast['and_']
        c = x.pop()
        while x:
            y = x.pop()
            if y:
                c = c | y
        return c
        
    def and_constraint(self, ast):
        x = ast['allof']
        c = x.pop()
        while x:
            y = x.pop()
            if y:
                c = c | y
        return c

    def betweentimesofdayconstraint(self,ast):
        s = parseTime(ast[0])
        e = parseTime(ast[1])
        #Start before end means range does not cross midnight
        if s<e:
            return recur.aftertime(s) & recur.beforetime(e)
        else:
            #To deal with ranges that cross midnight, we say things from 6 till midnight OR from midnight till 3am
            return recur.aftertime(s) | recur.beforetime(e)
    
    def aftertimeofdayconstraint(self,ast):
        s = parseTime(ast[0])
        return recur.aftertime(*s)
        
    def beforetimeofdayconstraint(self,ast):
        s = parseTime(ast[0])
        return recur.aftertime(*s)

    def dateconstraint(self,ast):
        c = recur.monthday([parseOrdinal(ast['dayofmonth'])]) & recur.month([parseMonth(ast['month'])])
        return c
    
    def beforetimeconstraint(self,ast):
        s = parseDateTimeWithYearWithDefaults(ast['before'])
        return recur.endingat(s)  
           
    def timeofdayconstraint(self,ast):
        s = parseTimes(ast['timeofdayconstraint'])
        return recur.time(*s)       
        
    def yeardayconstraint(self, ast):
        return recur.yearday(parseOrdinal(ast[1]))
    def monthconstraint(self, ast):
        return recur.month([parseMonth(i) for i in ast])
        
    def monthdayconstraint(self,ast):
        l = []
        for i in ast:
            l.append(parseOrdinal(i))
        return recur.monthday(l)

    def weekdayconstraint(self,ast):
        l = []
        for i in ast:
            l.append(parseWeekday(i))
        return recur.weekday(l)

d = datetime.datetime(2016,9,26)

def getConstraint(c):
    c0 = c[0].lower()
    c = c0+c[1:]
    s = semantics()
    s.tz = None
    c= p.parse(c, rule_name="start",semantics =s)
    a = s.align if hasattr(s,"align") else None
    if s.tz:
        import pytz
    tz = pytz.timezone(s.tz) if s.tz else None
    return recur.Selector(c, a,tz)
