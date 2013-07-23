import common
import modules
import pages
import auth
import cherrypy,time
from kaithemobj import kaithem

#Disable the stuff that depends on the internet/browsers/cookies/etc
oldrequire = pages.require
def dummy(xyz):
    pass
pages.require = dummy

class BSException(Exception):
    pass

#THis lets us handle/ignore HTTP redirect exceptions
oldredirect = cherrypy.HTTPRedirect
cherrypy.HTTPRedirect = BSException

from modules import ActiveModules
wb = modules.WebInterface()

######################################################################################
#Add a new module
try:
   wb.newmoduletarget(name='TEST')
except BSException:
    pass


#Make sure the module shows up in the index
if not 'TEST' in wb.index():
    common.fail("Added new module, but it did not show up in the index")
######################################################################################
#Create a page called testpage
try:
    wb.module('TEST','addresourcetarget','page',name="testpage")
except BSException:
    pass

#View the module's main page and make sure our new page shows up.
if not 'testpage' in wb.module('TEST'):
    common.fail("Made a new module but it didn't show up in the module's index")
###################################################################################### 
#Create a new event
try:
    wb.module('TEST','addresourcetarget','event',name="testevent")
except BSException:
    pass

#Cause that event to respond to kaithem.globals.x being 17 by setting it to 0
try:
    wb.module('TEST','updateresource','testevent',
        trigger='kaithem.globals.x == 17',
        
        action='kaithem.globals.x = 0',
        setup='kaithem.globals.x = 0'
        )
    
except BSException:
    pass

try:
    kaithem.globals.x 
except NameError:
    common.fail("Event did not set up kaithem.globals.x")

#Lets see if the event notices like it's supposed to
kaithem.globals.x = 17
time.sleep(0.25)
if not kaithem.globals.x == 0:
    common.fail("Event did not set kaithem.globals.x to 0 when it was manually set to 17")
    
#Now let's delete that event
try:
    wb.module('TEST','deleteresourcetarget',name='testevent')
except BSException:
    pass



#And make sure it is really gone
kaithem.globals.x = 17
time.sleep(0.25)
if not kaithem.globals.x == 17:
    common.fail("Deleting event did not remove it's effects")
######################################################################################
#Create a new permission
try:
    wb.module('TEST','addresourcetarget','permission',name="TestPermission",description="some BS")
except BSException:
    pass

if not 'TestPermission' in auth.Permissions:
    common.failure("Created a new permission but it did not appear in the auth list.")
######################################################################################   
#Create a new event
try:
    wb.module('TEST','addresourcetarget','event',name="testevent")
except BSException:
    pass

#Cause that event to respond to kaithem.globals.x being 17 by setting it to 0
try:
    wb.module('TEST','updateresource','testevent',
        trigger='kaithem.globals.x == 17',
        action='kaithem.globals.x = 0',
        setup='kaithem.globals.x = 0'
        )
    
except BSException:
    pass

    
#Now let's delete the WHOLE MODULE the event is in
try:
    wb.deletemoduletarget(name='TEST')
except BSException:
    pass

#And make sure it is really gone
kaithem.globals.x = 17
time.sleep(0.25)
if not kaithem.globals.x == 17:
    common.fail("Deleting event did not remove its effects.")

#Make sure the module is really gone from the index
if 'TEST' in wb.index():
    common.fail("Deleted module, but it was still in the index.")
######################################################################################




common.suceed("Sucess in testing modules system")