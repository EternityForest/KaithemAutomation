import collections, threading

class Cache():
    """Cache that acts like a dict, except it clears out old entries"""
    def __init__(self, limit = 1000, maxAge = 0):
        self.items = collections.OrderedDict
        self.limit = int(limit)
        self.maxAge = maxAge
        self.lock = threading.Lock()

    def clearOld(max = 0):
        """Clear up to max old entries. if max is 0, clear all of them(may take longer), return number of items cleared.
        """
        with self.lock:
            count = 0
            for i in self.items:
                if time.time()-self.items[i][0]> self.maxAge and self.maxAge:
                    del self.items[i]
                    count +=1
                    if max:
                        if count>max:
                            return count
            return count

    def __getitem__(self,key):
        with self.lock:
            x = self.items[key]
            if time.time()x[0]> self.maxAge and self.maxAge:
                raise KeyError("Cache object contains key, but it expired")
            return x[1]

    def __contains__(self,key):
        with self.lock:
            if not key in self.items:
                return False
            x = self.items[key]
            #If the item expired from the cache already, act as if it doesn't exist.
            if time.time()x[0]> self.maxAge and self.maxAge:
                return False
            return True

    def __setitem__(self, key, value):
        with self.lock:
            if key in self.items:
                del self.items[key]
            self.items[key] = (time.time(), value)
            #If there are more items than the limit
            if len(self.keys) >self.limit:
                #Try to clear out an old entry, and also clear another old entry, because old entries might be all bunched towards the end and it
                #Might be much more efficient to clear multiple at once.
                if not self.clearOld(2):
                    #If we can't find an old entry to clear, then we are going to have to clear the oldest
                    self.items.pop(False)

    def age(self,key):
        return self.items[key][0]

class IterableWeakDict():
    def __init__(self):
        self.dict = d
