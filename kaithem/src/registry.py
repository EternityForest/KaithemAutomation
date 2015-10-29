#Copyright Daniel Dunn 2015
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
from . import util,directories,messagebus
import os,time,json,copy,hashlib,threading,copy, traceback, shutil, yaml, validictory
from .util import url, unurl

class PersistanceArea():

    #A special dict that works mostly like a normal one, except for it raises
    #an error if someone puts something non serializable in.

    class PersistanceDict(dict):
        def __init__(self, *args):
            self.md5 = ''
            self.schemas = {}
            dict.__init__(self, *args)

        #True if nothing changed since last marked clean. Used to decide to save or not.
        def isClean(self):
            if self.md5 == hashlib.md5(json.dumps(copy.deepcopy(self)).encode('utf8')).digest():
                return True
            else:
                return False

        #We could use a flag, but using the hash doesn't have possible thread issues.
        def markClean(self):
            self.md5 = hashlib.md5(json.dumps(copy.deepcopy(self)).encode('utf8')).digest()
        
        def __getitem__(self, key):
            val = dict.__getitem__(self, key)
            return val

        #Custom setitem because we want to ensure nobody puts non serializable things in
        #Even though we might use YAML at some point it stil makes sense to limit things to JSON
        #for simplicity
        def __setitem__(self, key, val):
            try:
                json.dumps({key:val})
            except:
                raise RuntimeError("Invalid dict insert %s:%s has a non serializable value or key"%(key,val))
            dict.__setitem__(self, key, val)

    def __init__(self,folder):
        try:
            #We want to loop over all the timestamp named directories till we find a valid one
            #We rename invalid ones to INCOMPLETE<name>
                #This is going to recheck data every time.
                f = None
                if os.path.isfile(os.path.join(folder,"data","kaithem_dump_valid.txt")):
                    f = "data"
                else:
                    for i in(0,15):
                        f = util.getHighestNumberedTimeDirectory(folder)
                        if os.path.isfile(os.path.join(folder,f,"kaithem_dump_valid.txt")):
                            break
                        else:
                            shutil.copytree(os.path.join(folder,f),os.path.join(folder,"INCOMPLETE"+f))
                            shutil.rmtree(os.path.join(folder,f))
                            
                if not os.path.isfile(os.path.join(folder,"data","kaithem_dump_valid.txt")):
                    if os.path.isdir(os.path.join(folder,"data")):
                        shutil.copytree(os.path.join(folder,f),os.path.join(folder,"INCOMPLETE"+f))
        
                #Not that we are in a try block
                if not f:
                    raise RuntimeError("No Folder Found")
                            
                #Handle finding valid directory
                #Take all the json files and make PersistanceDicts, and mark them clean.
                self.files = {}
                for i in util.get_files(os.path.join(folder,f)):
                    if i.endswith('.json'):
                        with open(os.path.join(folder,f,i)) as x:
                            self.files[i[:-5]] = self.PersistanceDict(json.load(x)['data'])
                            self.files[i[:-5]].markClean()
                    


        except Exception as e:
            print(e)
            self.files = {}
        self.folder = folder

    #Save persistane area to folder dump
    def save(self):
        error =0
        save = 0
        #See if we need to save at all, save if we have at least one unclean file
        for i in self.files:
            if not self.files[i].isClean():
                save = 1
        if not save:
            return False

        try:
            t=str(util.time_or_increment())
            util.ensure_dir2(self.folder)
            
            if os.path.isdir(os.path.join(self.folder, "data")):
                #Copy everything except the completion marker
                shutil.copytree(os.path.join(self.folder, "data"), os.path.join(self.folder,t),
                                ignore = shutil.ignore_patterns("kaithem_dump_valid.txt"))
                                                   
                with open(os.path.join(self.folder,t,'kaithem_dump_valid.txt'),"w") as x:
                    util.chmod_private_try(os.path.join(self.folder,t,'kaithem_dump_valid.txt'), execute=False)
                    x.write("This file certifies this folder as valid")
            else:
                util.ensure_dir2(os.path.join(self.folder,"data"))
            
            if os.path.isdir(os.path.join(self.folder,"data","kaithem_dump_valid.txt")):
                os.remove(os.path.join(self.folder,"data","kaithem_dump_valid.txt"))
            #This segment relies on copy and deepcopy being atomic...
            #iterate over files and dump each to a json, set error flag if there are any errors
            for i in self.files.copy():
                try:
                        with open(os.path.join(self.folder,"data",url(i)+".json"),'w') as x:
                            util.chmod_private_try(os.path.join(self.folder,"data",url(i)+".json"), execute=False)
                            json.dump({'data':copy.deepcopy(self.files[i])},x,sort_keys=True,indent=4, separators=(',', ': '))
                except Exception as e:
                    error =1
                    try:
                        messagebus.postMessage("/system/notifications/errors",'Registry save error:' + repr(e))
                    except:
                       pass
                   
            for i in util.get_files(os.path.join(self.folder,"data")):
                print(i)
                try:
                    if (not unurl(i)[:-5] in self.files) and not i=="kaithem_dump_valid.txt":
                        print(unurl(i))
                        os.remove(os.path.join(self.folder,"data",i))
                except Exception as e:
                    error =1
                    try:
                        messagebus.postMessage("/system/notifications/errors",'Registry save error:' + repr(e))
                    except:
                       pass

        except Exception as e:
            print("Failure dumping persistance dicts.")
            messagebus.postMessage("/system/notifications/errors",'Registry save error:' + repr(e))

        if not error:
            with open(os.path.join(self.folder,"data",'kaithem_dump_valid.txt'),"w") as x:
                util.chmod_private_try(os.path.join(self.folder,"data",'kaithem_dump_valid.txt'), execute=False)
                x.write("This file certifies this folder as valid")
        else:
            print("Failure dumping persistance dicts.")
        for i in self.files:
            self.files[i].markClean()
        util.deleteAllButHighestNumberedNDirectories(self.folder,2)
        return True

    def open(self,f):
        if not f in self.files:
            self.files[f]= self.PersistanceDict()
        return self.files[f]

registry = PersistanceArea(directories.regdir)
reglock = threading.Lock()

#This is not the actual way we determine if it is clean or not for saving, that is determined per file in an odd way.
#however, this is used for display purposes.
is_clean = True


def get(key,default=None):
    if not exists(key):
        return default
    prefix = key.split("/")[0]

    with reglock:
        f = registry.open(prefix)
        return copy.deepcopy(f['keys'][key]['data'])


def delete(key):
    prefix = key.split("/")[0]
    with reglock:
        f = registry.open(prefix)
        if not 'keys' in f:
            return False
        k= f['keys']
        del k[key]

def exists(key):
    prefix = key.split("/")[0]
    with reglock:
        f = registry.open(prefix)
        if not 'keys' in f:
            return False
        k= f['keys']
        if key in k:
            return True
        else:
            return False

def set(key,value):
    global is_clean
    is_clean = False
    try:
        json.dumps({key:value})
    except:
        raise Exception
    with reglock:
        prefix = key.split("/")[0]
        f = registry.open(prefix)
        if not 'keys' in f:
            f['keys']={}
        if not key in f['keys']:
            f['keys'][key]={}
        if 'schema' in f['keys'][key]:
            validictory.validate(value, f['keys'][key]['schema'])
        f['keys'][key]['data'] = copy.deepcopy(value)
        
def setschema(key,schema):
    global is_clean
    is_clean = False
    try:
        json.dumps({key:schema})
    except:
        raise Exception
    with reglock:
        prefix = key.split("/")[0]
        f = registry.open(prefix)
        if not 'keys' in f:
            f['keys']={}
        if not key in f['keys']:
            f['keys'][key]={}
        validictory.SchemaValidator(schema)
        f['keys'][key]['schema'] = copy.deepcopy(schema)

def sync():
    global is_clean
    with reglock:
         x = registry.save()
    is_clean = True
    return x
