""" Classes and metaclasses for easier ``__slots__`` handling.  """

from itertools import tee
from inspect import getmro
import dis

__version__ = '2018.8.1'
__all__ = ['Slots', 'SlotsMeta', 'SlotsPlusDict', 'SlotsPlusDictMeta']


def assignments_to_self(method) -> set:
    """Given a method, collect all the attribute names for assignments
    to "self"."""
    # Get the name of the var used to refer to the instance. Usually,
    # this will be "self". It's the first parameter to the
    # __init__(self, ...)  method call. If there are no parameters,
    # just pretend it was "self".
    instance_var = next(iter(method.__code__.co_varnames), 'self')
    # We need to scan all the bytecode instructions to see all the times
    # an attribute of "self" got assigned-to. First get the list of
    # instructions.
    instructions = dis.Bytecode(method)
    # Assignments to attributes of "self" are identified by a first
    # LOAD_FAST (with a value of "self") immediately followed by a
    # STORE_ATTR (with a value of the attribute name). So we will need
    # to look at a sequence of pairs through the bytecode. The easiest
    # way to do this is with two iterators.
    i0, i1 = tee(instructions)
    # March the second one ahead by one step.
    next(i1, None)
    names = set()
    # a and b are a pair of bytecode instructions; b follows a.
    for a, b in zip(i0, i1):
        accessing_self = (a.argval == instance_var and a.opname == 'LOAD_FAST')
        storing_attribute = (b.opname == 'STORE_ATTR')
        if accessing_self and storing_attribute:
            names.add(b.argval)
    return names


class SlotsMeta(type):
    def __new__(mcs, name, bases, ns):
        # Caller may have already provided slots, in which case just
        # retain them and keep going. Note that we make a set() to make
        # it easier to avoid dupes.
        slots = set(ns.get('__slots__', ()))
        if '__init__' in ns:
            slots |= assignments_to_self(ns['__init__'])
        ns['__slots__'] = slots
        return super().__new__(mcs, name, bases, ns)


class Slots(metaclass=SlotsMeta):
    pass


def super_has_dict(cls):
    return hasattr(cls, '__slots__') and '__dict__' in cls.__slots__


class SlotsPlusDictMeta(SlotsMeta):
    def __new__(mcs, name, bases, ns):
        slots = set(ns.get('__slots__', ()))
        # It seems like "__dict__" is only allowed to appear once in
        # the entire MRO slots hierarchy, so check them all to see
        # whether to add __dict__ or not.
        if not any(super_has_dict(s) for b in bases for s in getmro(b)):
            slots.add('__dict__')
        ns['__slots__'] = slots
        return super().__new__(mcs, name, bases, ns)


class SlotsPlusDict(metaclass=SlotsPlusDictMeta):
    pass
