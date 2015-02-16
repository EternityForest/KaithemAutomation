#!/usr/bin/python3
#Copyright Daniel Dunn 2013
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

#For reliability, this file manages the lifetime of the Kaithem server.
#If the Kaithem program returns with returncode 0, the program will simply exit.
#Any other code will cause it to restart the program.
#The reason for this is the very slight possibility of some kind of memory leak, deadlock, lockup, etc.
#This gives us the ability to restart the interpreter.

import subprocess,sys

kaithemfile = os.path.join(os.path.dirname(os.path.realpath(__file__)),'src','kaithem.py')

#Just run the executable in a big old loop
while 1:
    x = subprocess.call([sys.executable,kaithemfile]+sys.argv)
    if x == 0:
        break