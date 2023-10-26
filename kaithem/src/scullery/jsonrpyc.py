# coding: utf-8

"""
Minimal python RPC implementation in a single file based on the JSON-RPC 2.0 specs from
http://www.jsonrpc.org/specification.
"""


__author__ = "Marcel Rieger"
__email__ = "python-jsonrpyc@googlegroups.com"
__copyright__ = "Copyright 2016-2021, Marcel Rieger"
__credits__ = ["Marcel Rieger"]
__contact__ = "https://github.com/riga/jsonrpyc"
__license__ = "BSD-3-Clause"
__status__ = "Development"
__version__ = "1.1.1"
__all__ = ["RPC"]

import logging
import select

import sys
import json
import io
import time
import threading
import weakref
import traceback
import os


server_only = False


class Spec(object):
    """
    This class wraps methods that create JSON-RPC 2.0 compatible string representations of
    request, response and error objects. All methods are class members, so you might never want to
    create an instance of this class, but rather use the methods directly:

    .. code-block:: python

        Spec.request("my_method", 18)  # the id is optional
        # => '{"jsonrpc":"2.0","method":"my_method","id": 18}'

        Spec.response(18, "some_result")
        # => '{"jsonrpc":"2.0","id":18,"result":"some_result"}'

        Spec.error(18, -32603)
        # => '{"jsonrpc":"2.0","id":18,"error":{"code":-32603,"message":"Internal error"}}'
    """

    @classmethod
    def check_id(cls, id, allow_empty=False):
        """
        Value check for *id* entries. When *allow_empty* is *True*, *id* is allowed to be *None*.
        Raises a *TypeError* when *id* is neither an integer nor a string.
        """
        if (id is not None or not allow_empty) and not isinstance(id, (int, str)):
            raise TypeError(
                "id must be an integer or string, got {} ({})".format(id, type(id)))

    @classmethod
    def check_method(cls, method):
        """
        Value check for *method* entries. Raises a *TypeError* when *method* is not a string.
        """
        if not isinstance(method, str):
            raise TypeError(
                "method must be a string, got {} ({})".format(method, type(method)))

    @classmethod
    def check_code(cls, code):
        """
        Value check for *code* entries. Raises a *TypeError* when *code* is not an integer, or a
        *KeyError* when there is no :py:class:`RPCError` subclass registered for that *code*.
        """
        if not isinstance(code, int):
            raise TypeError(
                "code must be an integer, got {} ({})".format(id, type(id)))

        if not get_error(code):
            raise ValueError(
                "unknown code, got {} ({})".format(code, type(code)))

    @classmethod
    def request(cls, method, id=None, params=None):
        """
        Creates the string representation of a request that calls *method* with optional *params*
        which are encoded by ``json.dumps``. When *id* is *None*, the request is considered a
        notification.
        """
        try:
            cls.check_method(method)
            cls.check_id(id, allow_empty=True)
        except Exception as e:
            raise RPCInvalidRequest(str(e))

        # start building the request string
        req = "{{\"jsonrpc\":\"2.0\",\"method\":\"{}\"".format(method)

        # add the id when given
        if id is not None:
            # encode string ids
            if isinstance(id, str):
                id = json.dumps(id)
            req += ",\"id\":{}".format(id)

        # add parameters when given
        if params is not None:
            try:
                req += ",\"params\":{}".format(json.dumps(params))
            except Exception as e:
                raise RPCParseError(str(e))

        # end the request string
        req += "}"

        return req

    @classmethod
    def response(cls, id, result):
        """
        Creates the string representation of a respone that was triggered by a request with *id*.
        A *result* is required, even if it is *None*.
        """
        try:
            cls.check_id(id)
        except Exception as e:
            raise RPCInvalidRequest(str(e))

        # encode string ids
        if isinstance(id, str):
            id = json.dumps(id)

        # build the response string
        try:
            res = "{{\"jsonrpc\":\"2.0\",\"id\":{},\"result\":{}}}".format(
                id, json.dumps(result))
        except Exception as e:
            raise RPCParseError(str(e))

        return res

    @classmethod
    def error(cls, id, code, data=None):
        """
        Creates the string representation of an error that occured while processing a request with
        *id*. *code* must lead to a registered :py:class:`RPCError`. *data* might contain
        additional, detailed error information and is encoded by ``json.dumps`` when set.
        """
        try:
            cls.check_id(id)
            cls.check_code(code)
        except Exception as e:
            raise RPCInvalidRequest(str(e))

        # build the inner error data
        message = get_error(code).title
        err_data = "{{\"code\":{},\"message\":\"{}\"".format(
            code, message).replace("\n", '').replace("\r", '')

        # insert data when given
        if data is not None:
            try:
                err_data += ",\"data\":{}}}".format(json.dumps(data))
            except Exception as e:
                raise RPCParseError(str(e))
        else:
            err_data += "}"

        # encode string ids
        if isinstance(id, str):
            id = json.dumps(id)

        # start building the error string
        err = "{{\"jsonrpc\":\"2.0\",\"id\":{},\"error\":{}}}".format(
            id, err_data)

        return err


leakDebug = weakref.WeakValueDictionary()


class RPC(object):
    """
    The main class of *jsonrpyc*. Instances of this class wrap an input stream *stdin* and an output
    stream *stdout* in order to communicate with other services. A service is not even forced to be
    written in Python as long as it strictly implements the JSON-RPC 2.0 specification. RPC
    instances may wrap a *target* object. By means of a :py:class:`Watchdog` instance, incoming
    requests are routed to methods of this object whose result might be sent back as a response.
    The watchdog instance is created but not started yet, when *watch* is not *True*.
    Example implementation:

    *server.py*

    .. code-block:: python

        import jsonrpyc

        class MyTarget(object):

            def greet(self, name):
                return f"Hi, {name}!"

       jsonrpc.RPC(MyTarget())

    *client.py*

    .. code-block:: python

        import jsonrpyc
        from subprocess import Popen, PIPE

        p = Popen(["python", "server.py"], stdin=PIPE, stdout=PIPE)
        rpc = jsonrpyc.RPC(stdout=p.stdin, stdin=p.stdout)

        # non-blocking remote procedure call with callback and js-like signature
        def cb(err, res=None):
            if err:
                throw err
            print(f"callback got: {res}")

        rpc("greet", args=("John",), callback=cb)

        # cb is called asynchronously which prints
        # => "callback got: Hi, John!"

        # blocking remote procedure call with 0.1s polling
        print(rpc("greet", args=("John",), block=0.1))
        # => "Hi, John!"

        # shutdown the process
        p.stdin.close()
        p.stdout.close()
        p.terminate()
        p.wait()

    .. py:attribute:: target

       The wrapped target object. Might be *None* when no object is wrapped, e.g. for the *client*
       RPC instance.

    .. py:attribute:: stdin

       The input stream, re-opened with ``"rb"``.

    .. py:attribute:: stdout

       The output stream, re-opened with ``"wb"``.

    .. py:attribute:: watch

       The :py:class:`Watchdog` instance that optionally watches *stdin* and dispatches incoming
       requests.
    """

    EMPTY_RESULT = object()

    def __init__(self, target=None, stdin=None, stdout=None, watch=True, **kwargs):
        super(RPC, self).__init__()
        self.fastResponseFlag = threading.Event()

        # the wrapped target object
        self.target = weakref.ref(target)
        leakDebug[id(self)] = self

        # open streams
        stdin = sys.stdin if stdin is None else stdin
        stdout = sys.stdout if stdout is None else stdout
        self.stdin = io.open(stdin.fileno(), "rb")
        self.stdout = io.open(stdout.fileno(), "wb")

        # other attributes
        self._i = -1
        self._callbacks = {}
        self._results = {}
        self.stopFlag = False

        # create and optionall start the watchdog
        kwargs["start"] = watch
        kwargs.setdefault("daemon", target is None)
        self.watchdog = Watchdog(self, **kwargs)

        self.threadStopped = False

    def __del__(self):
        if server_only:
            try:
                self.stdin.close()
            except Exception:
                pass
            try:
                self.stdout.close()
            except Exception:
                pass

            watchdog = getattr(self, "watchdog", None)
            if watchdog:
                watchdog.stop()

    def __call__(self, *args, **kwargs):
        """
        Shorthand for :py:meth:`call`.
        """
        return self.call(*args, **kwargs)

    def call(self, method, args=(), kwargs=None, callback=None, block=0, timeout=60):
        """
        Performs an actual remote procedure call by writing a request representation (a string) to
        the output stream. The remote RPC instance uses *method* to route to the actual method to
        call with *args* and *kwargs*. When *callback* is set, it will be called with the result of
        the remote call. When *block* is larger than *0*, the calling thread is blocked until the
        result is received. In this case, *block* will be the poll interval, emulating synchronuous
        return value behavior. When both *callback* is *None* and *block* is *0* or smaller, the
        request is considered a notification and the remote RPC instance will not send a response.
        """
        # default kwargs
        if kwargs is None:
            kwargs = {}

        # check if the call is a notification
        is_notification = callback is None and block <= 0

        # create a new id for requests expecting a response
        id = None
        if not is_notification:
            self._i += 1
            id = self._i

        # register the callback
        if callback is not None:
            self._callbacks[id] = callback

        # store an empty result for the meantime
        if block > 0:
            self._results[id] = self.EMPTY_RESULT

        # create the request
        params = {"args": args, "kwargs": kwargs}
        req = Spec.request(method, id=id, params=params)
        self.fastResponseFlag.clear()

        self._write(req)

        st = time.time()

        # blocking return value behavior
        if block > 0:

            while True:
                if self._results[id] != self.EMPTY_RESULT:
                    result = self._results[id]
                    del self._results[id]
                    if isinstance(result, Exception):
                        raise result
                    else:
                        return result
                # Block for up to the specified time, but also, whenever any new data comes in we immediately check.

                if self.fastResponseFlag.wait(block):
                    self.fastResponseFlag.clear()
                if timeout and (time.time() - st) > timeout:
                    raise TimeoutError("Request Timed Out")

    def _handle(self, line):
        """
        Handles an incoming *line* and dispatches the parsed object to the request, response, or
        error handlers.
        """
        try:
            obj = json.loads(line)
        except Exception:
            print("Bad JSON", line)
            # What if we just didn't?
            return

        # dispatch to the correct handler
        if "method" in obj:
            # request
            self._handle_request(obj)
        elif "error" not in obj:
            # response
            self._handle_response(obj)
        else:
            # error
            self._handle_error(obj)

    def _handle_request(self, req):
        """
        Handles an incoming request *req*. When it containes an id, a response or error is sent
        back.
        """
        try:
            method = self._route(req["method"])
            result = method(*req["params"]["args"], **req["params"]["kwargs"])
            if "id" in req:
                res = Spec.response(req["id"], result)
                self._write(res)
        except Exception as e:
            sys.stderr.write(traceback.format_exc())
            if "id" in req:
                if isinstance(e, RPCError):
                    err = Spec.error(req["id"], e.code, e.data)
                else:
                    err = Spec.error(req["id"], -32603,
                                     str(traceback.format_exc()))

                self._write(err)

    def _handle_response(self, res):
        """
        Handles an incoming successful response *res*. Blocking calls are resolved and registered
        callbacks are invoked with the first error argument being set to *None*.
        """
        # set the result
        if res["id"] in self._results:
            self._results[res["id"]] = res["result"]

        # lookup and invoke the callback
        if res["id"] in self._callbacks:
            callback = self._callbacks[res["id"]]
            del self._callbacks[res["id"]]
            callback(None, res["result"])

    def _handle_error(self, res):
        """
        Handles an incoming failed response *res*. Blocking calls throw an exception and
        registered callbacks are invoked with an exception and the second result argument set to
        *None*.
        """
        # extract the error and create an actual error instance to raise
        err = res["error"]
        error = get_error(err["code"])(err.get("data", err["message"]))

        # set the error
        if res["id"] in self._results:
            self._results[res["id"]] = error

        # lookup and invoke the callback
        if res["id"] in self._callbacks:
            callback = self._callbacks[res["id"]]
            del self._callbacks[res["id"]]
            callback(error, None)

    def _route(self, method):
        """
        Returnes the method of the wrapped target object to be called when *method* is requested.
        Example:

        .. code-block:: python

            MyClassB(object):
                def foo(self):
                    return 123

            MyClassA(object):
                def __init__(self):
                    self.b = MyClassB()

                def bar(self):
                    return "test"

            rpc = RPC(MyClassA())

            rpc._route("bar")
            # => <bound method MyClassA.bar ...>

            rpc._route("b.foo")
            # => <bound method MyClassB.foo ...>
        """
        # recursively traverse target attributes
        obj = self.target()

        for part in method.split("."):
            if not hasattr(obj, part):
                break
            obj = getattr(obj, part)
        else:
            return obj

        raise RPCMethodNotFound(data=method)

    def _write(self, s):
        """
        Writes a string *s* to the output stream.
        """
        self.stdout.write(bytearray(s + "\n", "utf-8"))
        self.stdout.flush()


wdl = weakref.WeakValueDictionary()


class Watchdog(threading.Thread):
    """
    This class represents a thread that watches the input stream of an :py:class:`RPC` instance for
    incoming content and dispatches requests to it.

    .. py:attribute:: rpc

       The :py:class:`RPC` instance.

    .. py:attribute:: name

       The thread's name.

    .. py:attribute:: interval

       The polling interval of the run loop.

    .. py:attribute:: daemon

       The thread's daemon flag.
    """

    def __init__(self, rpc, name="nostartstoplog.rpcwatchdog", interval=0.02, daemon=False, start=True):
        super(Watchdog, self).__init__()
        wdl[id(self)] = self

        # store attributes
        self.rpc = weakref.ref(rpc)
        self.name = name
        self.interval = interval
        self.daemon = daemon

        # register a stop event
        self._stop = threading.Event()

        if start:
            self.start()

    def start(self):
        """
        Starts with thread's activity.
        """
        super(Watchdog, self).start()

    def stop(self):
        """
        Stops with thread's activity.
        """
        self._stop.set()

    def run(self):
        try:
            # reset the stop event
            self._stop.clear()

            # stop here when stdin is not set or closed
            if not self.rpc().stdin or self.rpc().stdin.closed:
                return

            # read new incoming lines
            last_pos = 0
            while not self._stop.is_set():
                rpc = self.rpc()
                if not rpc:
                    return
                lines = None

                # stop when stdin is closed
                if rpc.stdin.closed:
                    break

                if rpc.stopFlag:
                    break

                # read from stdin depending on whether it is a tty or not
                if rpc.stdin.isatty():
                    cur_pos = rpc.stdin.tell()
                    if cur_pos != last_pos:
                        rpc.stdin.seek(last_pos)
                        lines = rpc.stdin.readlines()
                        last_pos = rpc.stdin.tell()
                        rpc.stdin.seek(cur_pos)
                else:
                    try:
                        rfds, wfds, efds = select.select(
                            [rpc.stdin.fileno()], [], [], self.interval)
                        # On some systems it seems we never got the select return,
                        # So we had to resort to polling way too much.
                        # It seems that might be fixed, so if possible we go back to slower
                        # polling and select() based response.
                        if rfds:
                            self.interval = 0.1
                        # We should exit if we detect we have been adopted by pid1
                        if os.getppid() < 2:
                            exit(1)

                        lines = [rpc.stdin.readline()]
                    except IOError:
                        # prevent residual race conditions occurring when stdin is closed externally
                        pass

                # handle new lines if any
                if lines and lines[0]:
                    rpc.fastResponseFlag.set()
                    for line in lines:
                        try:
                            line = line.decode("utf-8").strip()
                        except Exception:
                            print("Bad line", line)
                        if line:
                            rpc._handle(line)
                else:
                    self._stop.wait(self.interval)
                del rpc
        except Exception:
            print(traceback.format_exc())

        finally:
            if server_only:
                try:
                    self.rpc().stdin.close()
                    self.rpc().stdout.close()
                except Exception:
                    pass

            x = self.rpc()
            if x:
                x.threadStopped = True


class RPCError(Exception):

    """
    Base class for RPC errors.

    .. py:attribute:: message

       The message of this error, i.e., ``"<title> (<code>)[, data: <data>]"``.

    .. py:attribute:: data

       Additional data of this error. Setting the data attribute will also change the message
       attribute.
    """

    def __init__(self, data=None):
        # build the error message
        message = "{} ({})".format(self.title, self.code)
        if data is not None:
            message += ", data: {}".format(data)
        self.message = message

        super(RPCError, self).__init__(message)

        self.data = data

    def __str__(self):
        return self.message


error_map_distinct = {}
error_map_range = {}


def is_range(code):
    return (
        isinstance(code, tuple) and
        len(code) == 2 and
        all(isinstance(i, int) for i in code) and
        code[0] < code[1]
    )


def register_error(cls):
    """
    Decorator that registers a new RPC error derived from :py:class:`RPCError`. The purpose of
    error registration is to have a mapping of error codes/code ranges to error classes for faster
    lookups during error creation.

    .. code-block:: python

       @register_error
       class MyCustomRPCError(RPCError):
           code = ...
           title = "My custom error"
    """
    # it would be much cleaner to add a meta class to RPCError as a registry for codes
    # but in CPython 2 exceptions aren't types, so simply provide a registry mechanism here
    if not issubclass(cls, RPCError):
        raise TypeError("'{}' is not a subclass of RPCError".format(cls))

    code = cls.code

    if isinstance(code, int):
        error_map = error_map_distinct
    elif is_range(code):
        error_map = error_map_range
    else:
        raise TypeError("invalid RPC error code {}".format(code))

    if code in error_map:
        raise AttributeError("duplicate RPC error code {}".format(code))

    error_map[code] = cls

    return cls


def get_error(code):
    """
    Returns the RPC error class that was previously registered to *code*. *None* is returned when no
    class could be found.
    """
    if code in error_map_distinct:
        return error_map_distinct[code]

    for (lower, upper), cls in error_map_range.items():
        if lower <= code <= upper:
            return cls

    return None


@register_error
class RPCParseError(RPCError):

    code = -32700
    title = "Parse error"


@register_error
class RPCInvalidRequest(RPCError):

    code = -32600
    title = "Invalid Request"


@register_error
class RPCMethodNotFound(RPCError):

    code = -32601
    title = "Method not found"


@register_error
class RPCInvalidParams(RPCError):

    code = -32602
    title = "Invalid params"


@register_error
class RPCInternalError(RPCError):

    code = -32603
    title = "Internal error"


@register_error
class RPCServerError(RPCError):

    code = (-32099, -32000)
    title = "Server error"
