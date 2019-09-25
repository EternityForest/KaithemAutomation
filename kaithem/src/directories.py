#Copyright Daniel Dunn 2013, 2015
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
import os,pwd,shutil
from .config import config

#Normally we run from one folder. If it's been installed, we change the paths a bit.
dn = os.path.dirname(os.path.realpath(__file__))

srcdir = dn

if "/usr/lib" in dn:
    vardir= "/var/lib/kaithem"
    datadir = "/usr/share/kaithem"
    logdir = "/var/log/kaithem"
else:
    vardir =os.path.normpath(os.path.join(dn,'..'))
    vardir = os.path.join(vardir,config['site-data-dir'])
    datadir = os.path.normpath(os.path.join(dn,'../data'))
    logdir = os.path.join(vardir,'logs')



moduledatadir = os.path.join(vardir,'moduledata')

usersdir = os.path.join(vardir,'users')
regdir = os.path.join(vardir,'registry')
moduledir = os.path.join(vardir,'modules')
htmldir = os.path.join(dn,'html')
if not config['ssl-dir'].startswith("/"):
    ssldir =  os.path.join(vardir,config['ssl-dir'])
else:
    ssldir =  os.path.join(config['ssl-dir'])


def recreate():
    global dn,vardir,usersdir, logdir, regdir, moduledir, datadir, htmldir, ssldir
    dn = os.path.dirname(os.path.realpath(__file__))
    vd =os.path.normpath(os.path.join(dn,'..'))
    vardir = os.path.join(vd,config['site-data-dir'])
    usersdir = os.path.join(vardir,'users')
    logdir = os.path.join(vardir,'logs')
    regdir = os.path.join(vardir,'registry')
    moduledir = os.path.join(vardir,'modules')
    datadir = os.path.normpath(os.path.join(dn,'../data'))
    htmldir = os.path.join(dn,'html')
    ssldir =  os.path.join(vardir,config['ssl-dir'])


def chownIf(f,usr):
    if not pwd.getpwuid(os.stat(f).st_uid).pw_name ==usr:
        shutil.chown(f,usr,usr)

def rchown(d, usr):
    chownIf(d,usr)
    for root, dirs, files in os.path.walk():
        chownIf(root, usr)
        for file in files:
            chownIf(os.path.join(root,file), usr)
        