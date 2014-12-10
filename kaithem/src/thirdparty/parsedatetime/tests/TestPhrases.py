#!/usr/bin/env python

"""
Test parsing of strings that are phrases
"""

import unittest, time, datetime
import parsedatetime.parsedatetime as pt

  # a special compare function is used to allow us to ignore the seconds as
  # the running of the test could cross a minute boundary
def _compareResults(result, check, debug=False):
    target, t_flag = result
    value,  v_flag = check

    t_yr, t_mth, t_dy, t_hr, t_min, _, _, _, _ = target
    v_yr, v_mth, v_dy, v_hr, v_min, _, _, _, _ = value

    if debug:
        print target, t_flag
        print t_yr, t_mth, t_dy, t_hr, t_min, t_sec, t_wd, t_yd, t_isdst, t_flag
        print value, v_flag
        print v_yr, v_mth, v_dy, v_hr, v_min, v_sec, v_wd, v_yd, v_isdst, v_flag

    return ((t_yr == v_yr) and (t_mth == v_mth) and (t_dy == v_dy) and
            (t_hr == v_hr) and (t_min == v_min)) and (t_flag == v_flag)

class test(unittest.TestCase):
    def setUp(self):
        self.cal = pt.Calendar()
        self.yr, self.mth, self.dy, self.hr, self.mn, self.sec, self.wd, self.yd, self.isdst = time.localtime()

    def testPhrases(self):
        start  = datetime.datetime(self.yr, self.mth, self.dy, self.hr, self.mn, self.sec).timetuple()
        target = datetime.datetime(self.yr, self.mth, self.dy, 16, 0, 0).timetuple()

        self.assertTrue(_compareResults(self.cal.parse('flight from SFO at 4pm', start), (target, 2)))

        target = datetime.datetime(self.yr, self.mth, self.dy, 17, 0, 0).timetuple()

        self.assertTrue(_compareResults(self.cal.parse('eod',         start), (target, 2)))
        self.assertTrue(_compareResults(self.cal.parse('meeting eod', start), (target, 2)))
        self.assertTrue(_compareResults(self.cal.parse('eod meeting', start), (target, 2)))

        target = datetime.datetime(self.yr, self.mth, self.dy, 17, 0, 0) + datetime.timedelta(days=1)
        target = target.timetuple()

        self.assertTrue(_compareResults(self.cal.parse('tomorrow eod', start), (target, 3)))
        self.assertTrue(_compareResults(self.cal.parse('eod tomorrow', start), (target, 3)))


    def testPhraseWithDays_DOWStyle_1_False(self):
        s = datetime.datetime.now()

          # find out what day we are currently on
          # and determine what the next day of week is
        t      = s + datetime.timedelta(days=1)
        start  = s.timetuple()

        (yr, mth, dy, _, _, _, wd, yd, isdst) = t.timetuple()

        target = (yr, mth, dy, 17, 0, 0, wd, yd, isdst)

        d = self.wd + 1
        if d > 6:
            d = 0

        day = self.cal.ptc.Weekdays[d]

        self.assertTrue(_compareResults(self.cal.parse('eod %s' % day, start), (target, 3)))

          # find out what day we are currently on
          # and determine what the previous day of week is
        t = s + datetime.timedelta(days=6)

        (yr, mth, dy, hr, mn, sec, wd, yd, isdst) = t.timetuple()

        target = (yr, mth, dy, 17, 0, 0, wd, yd, isdst)

        d = self.wd - 1
        if d < 0:
            d = 6

        day = self.cal.ptc.Weekdays[d]

        self.assertTrue(_compareResults(self.cal.parse('eod %s' % day, start), (target, 3)))


    def testEndOfPhrases(self):
        s = datetime.datetime.now()

          # find out what month we are currently on
          # set the day to 1 and then go back a day
          # to get the end of the current month
        (yr, mth, _, hr, mn, sec, _, _, _) = s.timetuple()

        mth += 1
        if mth > 12:
            mth = 1
            yr += 1

        t = datetime.datetime(yr, mth, 1, 9, 0, 0) + datetime.timedelta(days=-1)

        start  = s.timetuple()
        target = t.timetuple()

        self.assertTrue(_compareResults(self.cal.parse('eom',         start), (target, 1)))
        self.assertTrue(_compareResults(self.cal.parse('meeting eom', start), (target, 1)))

        s = datetime.datetime.now()

        (yr, mth, dy, hr, mn, sec, wd, yd, isdst) = s.timetuple()

        t = datetime.datetime(yr, 12, 31, hr, mn, sec)

        start  = s.timetuple()
        target = t.timetuple()

        self.assertTrue(_compareResults(self.cal.parse('eoy',         start), (target, 1)))
        self.assertTrue(_compareResults(self.cal.parse('meeting eoy', start), (target, 1)))

