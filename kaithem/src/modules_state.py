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

#This file is just for keeping track of state info that would otherwise cause circular issues.
import weakref
from threading import RLock
from src import util

#Items must be dicts, with the key being the name of the type, and having the key editpage
#That is a function which takes 3 arguments, module and resource, and the current resource arg,
#and must return an HTML string to be returned to the user.
#The key update must also be defined.
#This must take a module, a resource, the current resource object, and a dict created from a form
#POST, and returing a new updated resource object.

#If you want to be able to move the module, you must define a function 'onmove' that takes(module,resource,newmodule,newresource,object)
#The update function will always run under a lock.

#If you want your resource to do something special when it loads, you must define onload(module,resource,object)

#All of these functions are guaranteed to only be called during times when the entire list of modules is locked, only
#one at a time, etc.

#If you, as is most likely, want to be able to create new pages, define a function createpage(module,resource)
#That returns an HTML page for creating a new page.

#It must post to /modules/module/MODULENAME/addresourcetarget/TYPE/THE/PATH/WITHIN/THE/MODULE with name as a kwarg

#Yes, I know this is an awful way of doing this. It's based on really old code, and I was in a major hurry.

#To actually create the page, define a function create(module,resource, kwargs)
#That will return the JSON object of the module. Onload will be automatically called.

#Note that the actual dict objects are directly passed, you can modify them in place but you still must return them.
additionalTypes = weakref.WeakValueDictionary()

#This is a dict indexed by module/resource tuples that contains the absolute path to what
#The system considers the current "loaded" version.
fileResourceAbsPaths = {}

#When a module is saved outside of the var dir, we put the folder in which it is saved in here.
external_module_locations = {}

unsaved_changed_obj = {}
class ResourceType():
    def __init__(self):
        self.createButton = None

    def createpage(self,module,path):
        return """

        <form method=POST action="/modules/module/{module}/addresourcetarget/example/{path}">
        <input name="name">
        <input type="submit">
        </form>
        """.format(module=module, path=path)

    def create(self,module,path,name,kwargs):
        return {'resource-type':'example'}

    def editpage(self,module,resource,resourceobj):
        return str(resourceobj)

    def update(self,module,resource,resourceobj,**kwargs):
        return resourceobj
    def onload(self,module,resource,resourceobj):
        return True
    def onmove(self,module,resource,toModule,toResource,resourceobj):
        return True
    def ondelete(self,module,resource,obj):
        return True

r = ResourceType()
additionalTypes['example'] = r

class HierarchyDict():
    def __init__(self):
        self.flat = {}
        #This tree only stores the tree structure, actual elements are referenced by flat.
        #Names can be both dirs and entries, and no matter what are marked by dicts in the root.
        #To get the actual item, use root to navigate quickly and use flat to get the actual item
        self.root = {}
    def parsePath(self,s):
        return util.split_escape(s,"/","\\")

    def pathJoin(self,*p):
        return "/".join(p)
    def copy(self):
        return self.flat.copy()

    def ls(self,k):
        p = self.parsePath(k)
        l = self.root
        #Navigate to the last dir in the path, making dirs as needed.
        for i in p:
            if i in l:
                l = l[i]
            else:
                l[i] = {}
                l = l[i]
        return l.keys()

    def __contains__(self,k):
        if k in self.flat:
            return True
        return False

    def __setitem__(self,k,v):
        self.flat[k] = v
        p = self.parsePath(k)
        l = self.root
        #Navigate to the last dir in the path, making dirs as needed.
        #
        for i in p:
            if i in l:
                l = l[i]
            else:
                l[i] = {}
                l = l[i]
    def __getitem__(self,k):
        return self.flat[k]

    def __delitem__(self,k):
        del self.flat[k]
        p = self.parsePath(k)
        l = self.root
        pathTaken = []
        #Navigate to the last dir in the path, making dirs as needed
        for i in p[:-1]:
            if i in l:
                pathTaken.append((l, l[i],i))
                l = l[i]
            else:
                l[i] = {}
                pathTaken.append((l,l[i],i))
                l = l[i]
        #Now delete the "leaf node"
        for i in l[p[-1]]:
            try:
                del self[self.pathJoin(k,i)]
            except KeyError:
                pass

        del l[p[-1]]

        #This deletes the entire chain of empty folders, should such things exist.
        for i in reversed(pathTaken):
            if not i[1]:
                del i[0][2]

#Lets just store the entire list of modules as a huge dict for now at least
ActiveModules = {}

#The total list of al the vresources. We want to store separately so that we can handle the locking easier.
virtualResourceRoot = {}


def addVirtualResource(m,n,o):
    "Adds a resource to ActiveModules that will go away as soon as there are no references."
    def f(r):
        ActiveModules[m].pop(n)
    ActiveModules[m][n] = weakref.ref(o,f)


def in_folder(r,f):
    if not r.startswith(f):
        return False
    #Get the path as a list
    r = util.split_escape(r,'/','\\')
    #Get the path of the folder
    f = util.split_escape(f,'/','\\')
    #make sure the resource path is one longer than module
    if not len(r)==len(f)+1:
        return False
    return True

@util.lrucache(800)
def ls_folder(m,d):
    o = []
    x = ActiveModules[m]
    for i in x:
        if in_folder(i,d):
            o.append(i)
    return o

#
# def if_show_page(page):
#     if 'dont-show-in-index' in page:
#         if page['dont-show-in-index'] == True:
#             return False
#     return True
#
# @util.lrucache(1)
# def getPageListing():
#     x = []
#     for i in sorted(ActiveModules.keys()):
#         x[i] = {}
#         for j in sorted(ActiveModules[i].keys()):
#             if ActiveModules[i][j]['resource-type'] =='page':
#                 if canIGoToThisPage(ActiveModules[i][j]):
#                     x[i].append(j)
#     y ={}
#     for i in x:
#         if x[i]:
#             y[i] sorted(x[i])
#     return y
#


"this lock protects the activemodules thing. Any changes at all should go through this."
modulesLock = RLock()

#Define a place to keep the module private scope obects.
#Every module has a object of class object that is used so user code can share state between resources in
#a module
scopes ={}
