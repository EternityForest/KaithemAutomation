#Copyright Daniel Dunn 2013. 2015
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
import sys,os,weakref,threading,gzip,bz2,json, time,logging,hashlib,threading

posix_rename = False
if sys.platform.startswith('linux'):
    posix_rename =True
if sys.platform.startswith('darwin'):
    posix_rename =True


def resolvePath(fn,expand=True):
    if not expand:
        return fn
    return (os.path.expandvars(os.path.expanduser(fn)))



#TODO: Ensure only one thread can save a file at a time

if sys.version_info <(3,0):
    import StringIO
    strio = StringIO.StringIO
else:
    import io
    strio = io.BytesIO

persisters = []

#must be Rlock because load is recursive
lock = threading.RLock()

def saveExecutor(f):
    "Replace this with something that can call f with no args"
    f()

def saveAllAtExit():
    while persisters:
        i = persisters.pop()()
        try:
            i.save()
        except:
            logging.exception()

def chmod_private_try(p, execute=True):
    try:
        if execute:
            os.chmod(p,stat.S_IRUSR|stat.S_IWUSR|stat.S_IXUSR|stat.S_IRGRP|stat.S_IWGRP|stat.S_IXGRP)
        else:
            os.chmod(p,stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IWGRP)
    except Exception as e:
        raise e
def ensure_dir(f):
    d = os.path.dirname(f)
    if not os.path.exists(d):
        os.makedirs(d)

class Persister():
    def __init__(self,fn,default=None):
        self.fn= fn
        try:
            self.reload()
        except:
            self.value = default
        torm = []
        #Before we add ourselves, clear out any old persisters that are no longer needed.
        for i in persisters:
            if not i():
                torm.append(i)
        for i in torm:
            persisters.remove(i)

        persisters.append(weakref.ref(self))

    def save(self):
        save(self.value, self.fn, backup=True)

    def reload(self):
        if os.path.exists(self.fn):
            self.value = load(self.fn)

def save(data,fn, *,private=False,backup=True, expand=True, md5=False):
    """Save data to file. Filename must end in .json, .yaml, .txt, or .bin. Data will be encoded appropriately.
        Also supports compressed versions via filenames ending in .gz or .bz2.
        Args:
            data:
                the data to be written. if fn is a .json or .yaml, must be serializable. If filename is .txt, must be a string.
                If .bin, must be something like bytes.
            private:
                If True, file created with mode 700(Full access to root and owner but not even read to anyone else)
                If False(the default), file created with default mode
            backup:
                Setting this to true is an alias for mode="backup"
    """
    fn = resolvePath(fn, expand)
    with lock:

        #Make sure we don't overwrite a file when we create our dirs, because that behavior is undocumented in makedirs.
        x = os.path.split(fn)[0]
        already = {}

        #Safety counter to stop really wierd loops
        for i in range(64):
            if os.path.isfile(x):
                raise RuntimeError("Required intermediate directory is already present as a file, refusing to overwrite file")
            x = os.path.split(fn)[0]
            #Loop prevention
            if x in already:
                break
            already[x] = True

        if not os.path.exists(os.path.dirname(fn)):
            if private:
                os.makedirs(os.path.dirname(fn), mode=0o700)
            else:
                os.makedirs(os.path.dirname(fn))

        if os.path.isdir(fn):
            raise RuntimeError("Filename is already present as a directory, refusing to overwrite directory")
        #Get base type without compression
        if fn.endswith(".gz"):
            x = fn[:-3]
        elif fn.endswith(".bz2"):
            x = fn[:-4]
        else:
            x=fn
        #Encode the data into our chosen format
        if x.endswith(".json"):
            data = json.dumps(data).encode('utf8')
        elif x.endswith(".yaml"):
            import yaml
            data = yaml.dump(data).encode('utf8')
        elif x.endswith(".txt") or x.endswith(".md") or x.endswith(".rst"):
            data = (str(data).encode('utf8'))
        elif x.endswith(".bin"):
            data = (data)
        else:
            raise ValueError('Unsupported or missing File Extension')



        #We have selected a compressed type. Compress in-memory first so we can read-before-write
        #Note that disk access is slow enough the call to  basically makes no difference in speed here if it's already imported
        if fn.endswith(".gz"):
            i = strio()
            f = gzip.GzipFile(fn,mode='wb',fileobj=i)
            f.write(data)
            f.close()
            data = i.getvalue()

        elif fn.endswith(".bz2"):
            c = bz2.BZ2Compressor()
            c.compress(data)
            data = c.flush()
            del c

        #Do a read-before-write. We don't write if we don't have to
        if os.path.exists(fn):
            with open(fn,"rb") as f:
                if f.read() == data:
                    return

        ensure_dir(os.path.split(fn)[0])

        if backup:
            tempfn = fn+str(time.time())
        else:
            tempfn = fn

        logging.debug("Writing: "+fn)
        #Actually write it
        with open(tempfn,'wb') as f:

            #In backup mode, pre truncate and flush.
            #This means that even if an error occors during writing, we will be able to tell by the
            #mtime that the tilde file is the right one.
            if backup:
                f.flush()
                os.fsync(f.fileno())

            #Chmod it before we write anything to it.
            if private:
                chmod_private_try(tempfn)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        if backup:
            os.replace(tempfn, fn)

        if md5:
            with open(fn+ ".md5" , "w") as md5f:
                md5f.write(hashlib.md5(data).hexdigest())



def load(filename, *,expand=True):
    """Load a file. Return str if file extension is .txt, bytes on .bin, dict on .yaml or .json.

    After that may be a .bz2 or a .gz for compression.

    """
    filename = resolvePath(filename, expand)

    with lock:
        try:
             #Open the file and get the filename without the compression type attached to it.
            if filename.endswith(".gz"):
                f = gzip.GzipFile(filename,mode='rb')
                x = filename[:-3]
            elif filename.endswith(".bz2"):
                x = filename[:-4]
                f = bz2.BZ2File(filename,mode='rb')
            else:
                f = open(filename,'rb')
                x = filename

            if x.endswith(".json"):
                r=json.loads(f.read().decode('utf8'))
            elif x.endswith(".yaml"):
                import yaml
                r=yaml.load(f.read().decode('utf8'))
            elif x.endswith(".txt") or x.endswith(".md") or x.endswith(".rst"):
                r=f.read().decode('utf8')
            elif x.endswith(".bin"):
                r=f.read()
            else:
                raise ValueError('Unsupported File Extension')
        except Exception as e:
            try:
                f.close()
            except:
                pass
            raise
        try:
            f.close()
        except:
            pass

        return r
