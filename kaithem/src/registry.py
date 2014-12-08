from . import util,directories,messagebus
import os,time,json,copy,hashlib,threading

class PersistanceArea():
    
    #A special dict that works mostly like a normal one, except for it raises
    #an error if someone puts something non serializable in.
    
    class PersistanceDict(dict):
        def __init__(self, *args):
            self.md5 = ''
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
        
        #Custom getitem because we want to ensure nobody puts non serializable things in
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
            while(1):
                f = util.getHighestNumberedTimeDirectory(folder)
                if os.path.isfile(os.path.join(folder,f,"kaithem_dump_valid.txt")):
                    
                    #Handle finding valid directory
                    #Take all the json files and make PersistanceDicts, and mark them clean.
                    self.files = {}
                    for i in util.get_files(os.path.join(folder,f)):
                        if i.endswith('.json'):
                            with open(os.path.join(folder,f,i)) as x:
                                self.files[i[:-5]] = self.PersistanceDict(json.load(x)['data'])
                                self.files[i[:-5]].markClean()
                    break
                else:
                    os.rename(os.path.join(folder,f),os.path.join(folder,"INCOMPLETE"+f))
            
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
            util.ensure_dir(self.folder)
            os.mkdir(os.path.join(self.folder,t))
            #This segment relies on copy and deepcopy being atomic...
            #iterate over files and dump each to a json, set error flag if there are any errors
            for i in self.files.copy():
                try:
                        with open(os.path.join(self.folder,t,i+".json"),'w') as x:
                            json.dump({'data':copy.deepcopy(self.files[i])},x,sort_keys=True,indent=4, separators=(',', ': '))
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
            with open(os.path.join(self.folder,t,'kaithem_dump_valid.txt'),"w") as x:
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

def get(key,default=None):
    if not exists(key):
        return default
    prefix = key.split("/")[0]

    with reglock:
        f = registry.open(prefix)
        return f['keys'][key]['data']


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
        f['keys'][key]['data'] = value
        
def sync():
    with reglock:
         x = registry.save()
    return x

