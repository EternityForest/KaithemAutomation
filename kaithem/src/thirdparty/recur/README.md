# recur: Fast Recurring Events for Python

Recur is a Python library providing support for specifying recurring events with a plain English like syntax using the Grako PEG parser generator.

recur can find the next match for simple expressions in under 30 microseconds.

recur depends on TatSu to handle the parsing.

For example, `every 3 days at 3pm`
is internally translated to a set of "constraint objects" where the first constraint is one that matches `every 3 day`and the second is one that matches 3pm on any given day. Events occur at times when all constraints match.

Constraints can also represent ranges of times, and in this case an event occurs at the beginning of each matching period.

Recur is optimized so that constraints like `every 2 seconds on Mondays` will never sift through every single second just to find the one on Monday.

Instead, recur first skips to midnight on the next Monday(recur knows which constraints to match first based on the average time between matches), then asks the "2 seconds" constraint what the next match is after midnight.

Recur expressions always match a given set of days no matter when the expression is evaluated, and there are no references in the language to "today" or "tomorrow" or "now" in any way.

## API
To obtain a selector object, use `recur.getSelector(s)`, where s is a recur DSL expression.

Selector objects have the following methods:

`s.after(dt, inclusive=True)`
Return the start of the first matching time period after dt. If inclusive is true and dt is within a match, return the start of that match.

`s.before(dt)` Return the start of the first matching time period before dt. If dt is within a match, return the start of that match.

`s.end(dt)`
Return the end of the matching time period that dt is in, or return dt if dt is not within a matching time period.


## Recur DSL
The expression creation syntax is fairly simple. Generally you can enter plain English expressions and they will usually just work.


### Data types
While there are no "variables" and the language is purely declarative, there are datatypes that are required as arguments to the constraints.

#### Integers
Integers always just look as you would expect. 1, 2, 3, etc.

#### Ordinals
An ordinal is a number  such as `1st`, `2nd`, `3rd`, etc. The word `other` is also considered an ordinal equal to 2, and first, second, and thrid behave as expected.

#### Months
A month may be specified in full, as in `june`, `july`, `august`, or by the first three letters of it's name, as in `jun`, `jul`,`aug`

#### Years
Years must always be specified as full 4 or more digit years. If you need to reference a year before `1000`, use leading zeros as in `0001`

#### Days of the month
A day of the month is simply specified as an integers

#### Times of day
The following are all valid time formats: `4pm`, `4:46pm`, `16:14`(Times without am or pm are assumed to use 24h time),
`1:14pm`, `1:56:44`, `11:56:44am`, `1:12:34:0068am`(The last four are the milliseconds).

#### Dates
The following are all valid date formats: `jun 2 2016`, `feb 3rd 2016`, `2 jan 2016`

#### Dates without years
For dates not associated with a year the following are valid: `2 jun`, `2 june`, `june 4th`, `the 2nd of june`

#### Weekdays
These can be specified as `mon`, `tue`, `thurs`, or `Monday`, `Tuesday`, `Thursday`

#### Intervals
These are used in expressions like `every 3 weeks`, The valid intervals are `week`, `day`, `hour`, `minute`, `second`.
You may use the signular or plural forms as appropriate in most places(e.g. `every week` and `every 2 weeks`)


#### Lists
Lists are delimited by the comma and by the word and. `1,2, and 3` is a list of integers, while `1st, 2nd, and 3rd` is a list of ordinals.


### Constraints
A constraint is an object that matches a set of ranges of time. Putting two or more constraints next to each other creates a meta-constraint acting as a set intersection, in other words matching only the time matched by all of it's members.

For example, `every five minutes in january` matches only those times that are part of the fifth minute and also in january.

Note that we consider there to be a zero width non matching space between matches of a constraint, so 12:05 and 12:10 are separate matches.

#### Alignment
By default constraints "align" to 1/1/1. This means that the expression "every year" will match a set of ranges starting Jan 1 at midnight each year. To change this we can use the "starting at" expression, which acts globally for the entire expression, and accepts a date, date with a year, time, or any combination thereof. Missing fields will be replaced with the corresponding value from midnight 1/1/1(So "Jan 1 0001 at midnight" is the same as "midnight").

`every year starting Jan 9 2014` matches a set of ranges starting on Jan 9 every year. In effect, it "offsets the phase" of matches.

The "Starting at" constraint also behaves as a normal constraint, excluding matches before the given time, however it may only occur once.

#### Nth weekday
`every <ordinal> <weekday> of the month` matches the entirety of one specified day in every month. It is always aligned to midnight.

#### Interval
`every <ordinal> <interval` and `every <integer> <ordinal>` and `every <interval` will all match the entire specified period.
For example `every 3 weeks` will match the entirety of every third week. By default intervals containing "weeks" are aligned to Mondays, while the others are aligned to 1/1/1. "every 2 weeks starting at 2pm" will match a series of 7*24 periods that start and end at 2pm.

For the purpose of this constraint, a month is considered an interval. It will always use calendar months, and can be aligned. If the align point is past the end of a month, the last day of the month is used. For example `every month starting on Jan 30` will end on the 28th or 29th on leap years in February because there is no Feb 30.


#### Day of year
`on the <ordinal> day of the year` Will match the entirety of that calender day in the year, from midnight to midnight. Alignment has no effect on this constraint.


#### Day of the month
`on the <ordinal>` and `on the <ordinal> day of the month` will match the entirety of a specified day of each month regardless of Alignment.


#### Exact time
`at <time>` will match one moment in time on every day. Alignment has no effect.

#### Between times
`between <time> and <time>` will match that range of time every day. Time ranges that cross midnight are correctly handled, and alignment has no effect.

#### Weekday
`on <weekday>` will match the entirety of that day every week without regard to alignment.

### The And operator
You may wish to specify multiple times somethng should happen. To enable this, the and operator can be used as follows:

`every day in june and every hour in july`

### Duration
You may wish to specify the length of an event. To do this, one uses the for operator as follows:

`Every day at 2pm for five minutes`
`Every three hours and every minute on tuesday for ten seconds`

The for operator has lower precedence than and.

### Parens

Parens work as expected to override precedence.
`every ten seconds (at 2pm for five minutes)`

Runs at 2pm. 2:00:10PM, 2:00:20PM, etc, until 2:05PM.


