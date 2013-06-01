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

import auth,modules,os,threading,copy,sys

#2 and 3 have basically the same module with diferent names
if sys.version_info < (3,0):
    from urllib import quote
else:
    from urllib.parse import quote

	
def url(string):
    return quote(string,'')
	
def SaveAllState():
	auth.dumpDatabase()
	modules.saveAll()
	
def ensure_dir(f):
    d = os.path.dirname(f)
    if not os.path.exists(d):
        os.makedirs(d)
        
def readfile(f):
    try:
        fh = open(f)
        r = fh.read()
    finally:
        fh.close()
    return r



