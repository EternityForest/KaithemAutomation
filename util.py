import auth,modules,os,threading,copy,sys

#2 and 3 have basically the same module with diferent names
if sys.version_info < (3,0):
    from urllib import quote
else:
    from urllib.parse import quote

	
def url(string):
    return quote(string,'')
	
def SaveAllState():
	auth.dumpDatabase()
	modules.saveAll()
	
def ensure_dir(f):
    d = os.path.dirname(f)
    if not os.path.exists(d):
        os.makedirs(d)

#This is a threadsafe dictionary.
#It should be resistant to modification while iteration
class SafeDict(dict):
    def __init__(self,*args,**kwargs):
        #Some locked functions call other locked functions so we must use a reentrant lock
        self.mylock=threading.RLock(); 
        super(SafeDict, self).__init__(*args, **kwargs)

    def __setitem__(self,*args,**kwargs):
        with self.mylock:
            super(SafeDict,self).__setitem__(*args,**kwargs)

    def copy(self):
        with self.mylock:
            return copy.copy(self)



