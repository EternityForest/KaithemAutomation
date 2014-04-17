from . import util,directories
import os,time,json,copy,hashlib,threading

class PersistanceArea():
    
    #A special dict that works mostly like a normal one, except for it raises
    #an error if someone puts something non serializable in.
    
    class PersistanceDict(dict):
        def __init__(self, *args):
            self.md5 = ''
            dict.__init__(self, *args)
        
        def isClean(self):
            if self.md5 == hashlib.md5(json.dumps(copy.deepcopy(self)).encode('utf8')).digest():
                return True
            else:
                return False
        
        def markClean(self):
            self.md5 = hashlib.md5(json.dumps(copy.deepcopy(self)).encode('utf8')).digest()
    
        def __getitem__(self, key):
            val = dict.__getitem__(self, key)
            return val
    
        def __setitem__(self, key, val):
            try:
                json.dumps({key:val})
            except:
                raise RuntimeError("Invalid dict insert %s:%s"%(key,val))
            dict.__setitem__(self, key, val)
        
    def __init__(self,folder):
        try:
            while(1):
                f = util.getHighestNumberedTimeDirectory(folder)
                if os.path.isfile(os.path.join(folder,f,"kaithem_dump_valid.txt")):
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
    
    def save(self):
        error =0
        save = 0
        for i in self.files:
            if not self.files[i].isClean():
                save = 1
        if not save:
            return
                
        try:
            t=str(time.time())
            os.mkdir(os.path.join(self.folder,t))
            #This segment relies on copy and deepcopy being atomic...
            for i in self.files.copy():
                try:
                        with open(os.path.join(self.folder,t,i+".json"),'w') as x:
                            json.dump({'data':copy.deepcopy(self.files[i])},x,sort_keys=True,indent=4, separators=(',', ': '))
                except:
                    error =1
        except:
            print("Failure dumping persistance dicts.")
        if not error:
            with open(os.path.join(self.folder,t,'kaithem_dump_valid.txt'),"w") as x:
                x.write("This file certifies this folder as valid")
        for i in self.files:
            self.files[i].markClean()
        util.deleteAllButHighestNumberedNDirectories(self.folder,2)
        
    def open(self,f):
        if not f in self.files:
            self.files[f]= self.PersistanceDict()
        return self.files[f]

registry = PersistanceArea(directories.regdir)
reglock = threading.Lock()

def get(key):
    prefix = key.split("/")[0]
    with reglock:
        f = registry.open(prefix)
        return f['keys'][key]['data']

def set(key,value):
    try:
        json.dumps({key:value})
    except:
        raise Exception
    with reglock:
        prefix = key.split("/")[0]
        f = registry.open(prefix)
        if not 'data' in f:
            f['keys']={}
        if not key in f['keys']:
            f['keys'][key]={}
        f['keys'][key]['data'] = value
        
def sync():
    with reglock:
        registry.save()
        
set("turd","botdom")
print(get("turd"))
sync()

