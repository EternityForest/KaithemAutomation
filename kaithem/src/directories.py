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

#This is for the ability to move directories. 
#State is for modules ad persistance files
#cfg is any user configurable things
#Log is the log files

#[]Put these in approprite places when running on linux
import os
from config import config

dn = os.path.dirname(os.path.realpath(__file__))

usersdir = os.path.join(dn,'../var/users')
moduledir = os.path.join(dn,'../var/modules')
htmldir = os.path.join(dn, '../data/html')
datadir = os.path.join(dn, '../data')
ssldir =  os.path.join(dn,'..',config['ssl-dir'])