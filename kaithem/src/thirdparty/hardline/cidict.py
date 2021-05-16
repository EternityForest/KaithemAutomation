import collections

class CaseInsensitiveDict(collections.MutableMapping):
    """ Ordered case insensitive mutable mapping class. """
    def __init__(self, *args, **kwargs):
        self._d = collections.OrderedDict(*args, **kwargs)

    def __len__(self):
        return len(self._d)

    def __iter__(self):
        return iter(self._d)

    def __setitem__(self, k, v):
        self._d[k] = v

    def __getitem__(self, k):
        k=k.lower()
        for i in list(self._d.keys()):
            if i.lower()==k:
                return self._d[i]

        return self._d[k]

    def __delitem__(self, k):
        k=k.lower()
        for i in list(self._d.keys()):
            if i.lower()==k:
                del self._d[i]

    def copy(self):
        d = CaseInsensitiveDict()
        d._d = self._d.copy()
        return d
