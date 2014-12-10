import re
import pprint


offsets = { 'july': 7, 'jul': 7, 'august': 8, 'aug': 8, 'september': 9, 'sep': 9 }

rMonth = re.compile(r'''(\s?|^)
                        (?P<month>(
                                   (?P<mthname>(july|august|september|jul|aug|sep))
                                   (\s?(?P<year>(\d\d\d\d)))?
                                  ))
                        (\s?|$|[^0-9a-zA-Z])''',
                    re.IGNORECASE + re.VERBOSE)
rDay = re.compile(r'''(?P<day>\d\d?)(?P<suffix>(nd|st|rd|th)?)''', re.IGNORECASE + re.VERBOSE)


def _check(dateString, dYear, dMonth, dDay):
    yr  = []
    mth = []
    dy  = []


    items = dateString.split(' ')

    print len(items), items

    n = 0
    while True:
        if len(items) == 0:
            break

        t = items[n].strip()

        print yr, mth, dy, items, n, t

        # m = self.ptc.CRE_MONTH.search(t)
        m = rMonth.search(t)
        if m and m.group('mthname') == t:
            print t, m.group('mthname')
            # mth  = self.ptc.MonthOffsets[m.group('mthname')]
            mth.append(offsets[m.group('mthname')])
            del items[n]
            n = len(items)
            continue

        # m = self.ptc.CRE_DAY2.search(t)
        m = rDay.search(t)
        if m:
            s = m.group('suffix')
            d = m.group('day')

            print t, d, s

            if len(s) > 0:
                d = d.replace(s, '')
                del items[n]
                n = len(items)
                dy.append(int(d))
                continue
            else:
                if len(d) <= 2 and len(s) == len(d):
                    del items[n]
                    n = len(items)
                    dy.append(int(d))
                    continue

        if len(t) == 4:
            yr.append(int(t))
            continue

        n = n + 1
        if n >= len(items):
            n = 0

        print yr, mth, dy, items, n
        print '-'*42

    return yr, mth, dy


l = [ '23 aug 2008',
      '23rd aug 2008',
      # 'aug 23 2008',
      # 'aug 23rd 2008',
      # 'aug 3 2008',
      # 'aug 3rd 2008',
      # 'aug 1 2008',
      # 'aug 1st 2008',
      # 'aug 23',
      # 'aug 23, 2008 5pm',
    ]

for t in l:
    print _check(t, 2008, 10, 28)

