## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
{continual: false, enable: true, once: true, priority: interactive, rate-limit: 0.0,
  resource-timestamp: 1566264981202440, resource-type: event}

"""

__trigger__='False'

if __name__=='__setup__':
    """
    LivingNight is an algorithm to simulate complex interactions between random-ish systems, like the fact that a cricket might get quieter when someone walks past.
    
    """
    
    
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    
    import threading,weakref
    
    lock= threading.Lock()
    
    domains = {}
    
    class Domain():
        def __init__(self,name):
            self.name = name
            self.aspects = {}
            with lock:
                domains[name]= weakref.ref(self)
        
        def __del__(self):
            with lock:
                del domains[self.name]
    
    
    class Influence():
        def __init__(self,aspect, value):
            self.value = value
            self.aspect = aspect
    
            domain=''
    
            with lock:
                if not domain in domains:
                    self.domain = Domain(domain)
                else:
                    self.domain=domains[domain]
                
                if not aspect in self.domain.aspects:
                    self.domain.aspects[aspect]=0
    
                self.domain.aspects[aspect]+= self.value
                kaithem.message.post("/LivingNight/aspect/"+aspect, self.domain.aspects[aspect])
                    
        def __del__(self):
            with lock:
                self.domain.aspects[self.aspect]-= self.value
                kaithem.message.post("/LivingNight/aspect/"+self.aspect, self.domain.aspects[aspect])
    
                if self.domain.aspects[self.aspect]==0:
                    del self.domain.aspects[self.aspect]
                if not self.domain.aspects:
                    del domains[self.domain.name]
    
                    
    
    def calculateEffect(value, **kwargs):
        domain = ''
        with lock:
            d = domains[domain]
            for i in kwargs:
                if i in d.aspects:
                    value = value * kwargs[i]**d.aspects[i]
    
    
    module.lnEffect= calculateEffect
    module.LNInfluence = Influence

def eventAction():
    pass
