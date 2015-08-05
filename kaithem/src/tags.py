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
        if self.getter and self.age>self.interval:
            try:
                self.write(self.getter())
                self.updated = time.time()
            except Exception as e:
                messagebus.postMessage("system/tagpoints/errors", traceback.format_tb(6))
        else:
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
