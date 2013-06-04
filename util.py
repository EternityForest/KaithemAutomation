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

import auth,modules,os,threading,copy,sys,shutil

#2 and 3 have basically the same module with diferent names
if sys.version_info < (3,0):
    from urllib import quote
    from urllib import unquote as unurl
else:
    from urllib.parse import quote
    from urllib.parse import unquote as unurl

	
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

#Get the names of all subdirectories in a folder but not full paths
def get_immediate_subdirectories(folder):
    return [name for name in os.listdir(folder)
            if os.path.isdir(os.path.join(folder, name))]

#Get a list of all filenames but not the full paths
def get_files(folder):
    return [name for name in os.listdir(folder)
            if not os.path.isdir(os.path.join(folder, name))]
            
#fix this to not be ugly     
def getHighestNumberedTimeDirectory(where):
    """Given a directory containing entirely folders named after floating point values get the name of the highest. ignore files.
        and also ignoring non-timestapt float looking named directories
    """
    asnumbers = {}
    
    for i in get_immediate_subdirectories(where):
        try:
            asnumbers[float(i)] = i
        except ValueError:
            pass
        
    return asnumbers[sorted(asnumbers.keys(), reverse=True)[0]]

def deleteAllButHighestNumberedNDirectories(where,N):
    """In a directory full of folders named after time values, we delete all but the highest N directores ignoring files
       and also ignoring non-timestapt float looking named directories
    """
    asnumbers = {}
    for i in get_immediate_subdirectories(where):
            try:
                asnumbers[float(i)] = i
            except ValueError:
                pass
    
    for i in sorted(asnumbers.keys())[0:-N]:
        shutil.rmtree(os.path.join(where,asnumbers[i]))

