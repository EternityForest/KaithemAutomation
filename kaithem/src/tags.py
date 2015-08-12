import weakref,traceback, time
from src import util

# A tag point is very similar to a variable, except for the fact that you can subscribe to it and be notified if it changes py passing a function that takes
# one argument to tag.subscribe. You must maintain a reference to f or it will be garbage collected.
#
# The subscribe function returns a value that may be passed to unsubscribe for a more reliable means of deletion,
#
# To read the current value of a tag point, simply call it. The value will be returned, and if there are any subscribers, it will be passed to them as well.
#
# To write to the tag point, simply call it with one numeric argument.
#
# If you have set up a getter, the getter will be called whenever the tag points value is requested, and the value it returns will be used.
#
# tag.interval determines how long tag values can be cached for in seconds. tag.age is a property(not a function) that gives the total time since last updated.
#
# tag.require tells the tag point that a permission is needed to read to write.
#
# tag.meter takes the same parameters as widget.Meter and returns a meter that shows the value of the tag point.
# Its permissions will be exactly the same as the point.

#Tag

tags = {}

class Tag():
    def __init__(self,name, getter=None, default=0, min=None,
     max=None,high=None, low=None, high_warn=None,
      low_warn=None, step=None, normal_low= None,
      normal_high=None, clip_range=True):
        __doc__ = """

        This is a tag point, much like any SCADA tag point. It's a like a mutable variable, that you can subscribe to changes in, that raises exceptions
        if you try to pass non numeric or out of range values. All those arguments in the list can be modifier at any time(e.g. tag.max = xyz)

        Tag points are callable. Calling one gives you it's current value. Calling tag.age gives you the time in seconds since it got a new value.

        Tag points have configurable getters. If you say tag.getter = f, than whenever you call tag(), the value of f() will be returned.
        (Unless f returns an invalid value, than it raises an exception)

        Tag points can cache. If you set tag.interval to something other than 0, than values from tag.getter will be cached for that many seconds.
        Tag point intervals default to 0.015

        Tag points are writable. Saying tag(val) lets you directly push a value to a tag point

        Tag points are subscribable. Saying tag.subscribe(f) will result in f being called whenever a the tag point's value changes.
        This includes when you read from the point and the getter fires. You must keep a reference to f or it will be unsubscribed(it uses weakref)

        An easy way to use a tag point is to call it repeatedly in an event, and let other functions subscribe to it.

        One must be careful not to create cycles of tags that might call each other in a gigantic loop. However, the interval setting can be used to break loops,
        as a tag with a valid cache value will return that instead of calling upstream tags.

        Args:
            name: A simple natural language name, like "InputVoltage" or something. No restrictions on characters or formatting.
            getter: If supplied, must be a function of no arguments. reading the tagpoint's value will return the result of the function
            default: The inital value of the tag point
            min: The minimum value. Attempts to set lower values will clip or raise an error depending on clip_range
            max; The maximum value. Will clip or raise error depeding on clip_range
            high: A value that is considered to be excessively high, usually so mmuch so that action should be taken. May send a notification if exceeded
            low: A value that is considered to be excessively low.
            high_warn: A value considered to be at the upper edge of normal operation, enough that a warning may be produced
            low_warn: A value considered to be at the lower edge of normal operation.
            normal_low: The lowest value considered completely normal
            normal_high: The highest value considered completely normal
            step: The "resolution" of the tag point. All writes will be rounded to the nearest multiple of this.
            clip_range: Default is true. if true, clip high and low values exceeding min and max instead of raising an exception
        """
        self.subscribers = {}
        self.value = default
        self.read_permissions = []
        self.write_permissions = []
        self.getter = getter
        self.name = name
        self.updated = 0
        self.interval = 0.015
        self.min = min
        self.max = max
        self.high = high
        self.low= low
        self.high_warn = high_warn
        self.low_warn = low_warn
        self.normal_high = normal_high
        self.normal_low = normal_low
        self.step = step
        self.clip_range = clip_range
        self.is_normal = True
        self.autopoll = False

    #Complicated. terrible, and unmaintainable code using parts of things that were't supposed to be public.
    #Watch out to either refactor this or not make breaking changes in widget.py

    #Basically this creates a meter object, modifies it to share permissions with self,
    #then modifies things to pass through reads and writes. Actually checking permissions is handled by widget.py.
    def meter(self,*args,**kwargs):
        m = widgets.Meter(*args,**kwargs)
        m._write_perms = self.write_permissions
        m._read_perms = self.read_permissions
        def f(obj, usr):
            return self()
        m.onRequest = f
        return m

    def slider(self,*args,**kwargs):
        m = widgets.Slider(*args,**kwargs)
        m._write_perms = self.write_permissions
        m._read_perms = self.read_permissions
        def f(obj, usr):
            return self()
        m.onRequest = f
        def f(obj,user,val):
            self(val)
        m.onUpdate = f
        return m

    def __bool__(self):
        return self()>0.5

    def __nonzero__(self):
        return self()>0,5

    def _push(self, value):
        for i in self.subscribers:
            try:
                self.subscribers[i]()(value)
            except:
                pass

    def __call__(self,*args):
        if args:
            self.write(args[0])
            self.updated = time.time()
            return self.value
        #Maybe this should not call age and should do it direct and then we wouldn't have to deal with recursion and
        #Could still call self in age to find out what's up?
        if self.getter and self.age>self.interval:
            try:
                self.write(self.getter())
                self.updated = time.time()
            except Exception as e:
                messagebus.postMessage("system/tagpoints/errors", traceback.format_tb(6))
        return self.value

    @property
    def age(self):
        return time.time()-self.updated

    def _handle_new_value(self,value):
            "Even in this class, one should direct all writes to value throught this to keep alarms and constraints in one place. "
            if not self.min == None:
                if value<self.min:
                    if self.clip_range:
                        value = self.min
                    else:
                        raise RuntimeError("Value of " + str(value) + " out of range for TagPoint")

            if not self.max == None:
                if value > self.max:
                    if self.clip_range:
                        value = self.max
                    else:
                        raise RuntimeError("Value of " + str(value)+ " out of range for TagPoint")

            if not self.step ==None:
                value = util.roundto(value, self.step)
            self.value = float(value)
            self.updated = time.time()
            self._push(value)

    def write(self,value):
        "Handle either the user or the getter writing to the tag point"
        self._handle_new_value(value)

    def begin_autopoll(self):
        try:
            self.evt.unregister()
        except:
            pass
        self.evt = PolledInternalSystemEvent(lambda: True, self,continual=True, ratelimit = self.interval)
        self.evt,register()

    def end_autopoll(self):
        try:
            self.evt.unregister()
        except:
            pass

    def __del__(self):
        try:
            self.end_autopoll()
        except:
            pass

    def subscribe(self,f):
        id = util.unique_number()
        def g(o):
            self.unsubscribe(id)
        self.subscribers[id] = weakref.ref(f,g)
        if self.autopoll:
            self.begin_autopoll()
        return id

    def unsubscribe(self,id):
        try:
            del self.subscribers[id]
            if not self.subscribers:
                self.end_autopoll()
        except:
            pass

    def require(self, p):
        self.read_permissions.append(p)
        self.write_permissions.append(p)

    def requireToWrite(self,p):
        self.write_permissions.append(p)


class FilterTag(Tag):
        def __init__(self,*args,**kwargs):
            Tag.__init__(self,*args,**kwargs)
            self.last_input = 0

        def filter_step(self):
            "This is called BEFORE any read or write and must return a value. That value is what is returned to the user. any writes go directly to last_input"
            return self.last_input

        def __call__(self,*args):
            x = self.filter_step()
            self._handle_new_value(x)
            if args:
                self.last_input=args[0]
                self.updated = time.time()
            if self.getter and self.age>self.interval:
                try:
                    self.last_input=self.getter()
                    self.updated = time.time()
                except Exception as e:
                    messagebus.postMessage("system/tagpoints/errors", traceback.format_tb(6))
            return x

class ConstTag():
    def __init__(self, val):
        self.value = float(val)
        Tag.__init__(self)
        self.updated = time.time()

    def __call__(self,*args):
        return self.value

class CVFilterTag(FilterTag):
    def __init__(self, *args,**kwargs):
        FilterTag.__init__(self,*args,**kwargs)
        self.rate = kwargs['rate'] if "rate" in kwargs else 1
        self.last_input = 0
        self.position = 0

    def filter_step(self):
        if self.updated:
            change = time.time()-self.updated*self.rate
            if self.position < self.last_input:
                self.position = min(self.last_input, self.position+change)
            if self.position > self.last_input:
                self.position = max(self.last_input, self.position-change)
        return self.position

class FunctionTag(Tag):
    """The function tag's value is always a tag.f(tag.a()). In other words, it has a a property f that must be a 1 argument function, and a property a that must be a
    tag point. If you set a to a numeric value, it will be wrapped as a ConstTag.
    """
    def __init__(name=""):
        self._a = ConstTag(0)
        self.f = lambda x: x
    @property
    def a(self):
        return self._a

    @a.setter
    def seta(self,v):
        self._a = wrap(v)

    def __call__(self):
        if self.age>self.interval:
            try:
                x= self._a()
                self.updated = max(self.updated,self._a.updated)
                self.write(self.f(x))
            except Exception as e:
                messagebus.postMessage("system/tagpoints/errors", traceback.format_tb(6))
        else:
        	return self.value

class BinaryFunctionTag(Tag):
    """The function tag's value is always a tag.f(tag.a(), tag.b()). In other words, it has a a property f that must be a 2 argument function, and  properties a and that must be a
    tag point(defaulting to 0). If you set a to a numeric value, it will be wrapped as a ConstTag. Will cache values for tag.interval seconds.

    Asking the tag point's age will return the youngest age of it's two inputs.
    """
    def __init__(name=""):
        Tag.__init__(self,name)
        self._a = ConstTag(0)
        self._b = ConstTag(0)
        self.value = 0

    @property
    def a(self):
        return self._a

    @a.setter
    def seta(self,v):
        self._a = wrap(v)

    @property
    def b(self):
        return self._b

    @b.setter
    def setb(self,v):
        self._b = wrap(v)

    def __call__(self):
        if self.age>self.interval:
            try:
                x= self._a()
                self.updated = max(self.updated,self._a.updated)
                y= self._b()
                self.updated = max(self.updated,self._b.updated)
                self.write(self.f(x,y))
            except Exception as e:
                messagebus.postMessage("system/tagpoints/errors", traceback.format_tb(6))
        return self.value


class SwitchTag(Tag):
    "This tag has 3 input properties, a, b and s, all of which default to 0 and may be set to tag points or numbers. If s> 0.5, the output will be a, else it will be b"
    def __init__(name=""):
        Tag.__init__(self,name)
        self._s = ConstTag(1)
        self._a = ConstTag(0)
        self._b = ConstTag(0)

    @property
    def a(self):
        return self._a

    @a.setter
    def seta(self,v):
        self._a = wrap(v)

    @property
    def b(self):
        return self._b

    @b.setter
    def setb(self,v):
        self._b = wrap(v)

    @property
    def s(self):
        return self._s

    @s.setter
    def sets(self,v):
        self._s = wrap(v)

    def __call__(self):
        x=self._s()
        self.updated=max(self._s.updated, self.updated)
        if x:
            a = self._a()
            self.updated=max(self._a.updated, self.updated)
            return a
        else:
            b = self._b()
            self.updated=max(self._b.updated, self.updated)
            return b

def wrap(t):
    if isinstance(t, Tag):
        return t
    else:
        return ConstTag(t)

t = CVFilterTag("Butt")
def f(x):
    print(x)
t.subscribe(f)

t(10)
time.sleep(1)
t(10)
time.sleep(1)
t(10)
time.sleep(1.2)
t(10)
def f(x):
    print(x)
