# tornado_wsgi.py

# Source: https://stackoverflow.com/questions/26015116/making-tornado-to-serve-a-request-on-a-separate-thread
# by skrause


import itertools
import logging
import sys
import tempfile
from concurrent import futures
from io import BytesIO

from tornado import escape, gen, web
from tornado.iostream import StreamClosedError
from tornado.wsgi import to_wsgi_str
from . import auth
from . import pages

_logger = logging.getLogger(__name__)


@web.stream_request_body
class WSGIHandler(web.RequestHandler):
    thread_pool_size = 20

    def initialize(self, wsgi_application):
        self.wsgi_application = wsgi_application

        self.body_chunks = []
        self.body_tempfile = None

    def environ(self, request):
        """
        Converts a `tornado.httputil.HTTPServerRequest` to a WSGI environment.
        """
        hostport = request.host.split(":")
        if len(hostport) == 2:
            host = hostport[0]
            port = int(hostport[1])
        else:
            host = request.host
            port = 443 if request.protocol == "https" else 80

        if self.body_tempfile is not None:
            body = self.body_tempfile
            body.seek(0)
        elif self.body_chunks:
            body = BytesIO(b"".join(self.body_chunks))
        else:
            body = BytesIO()

        environ = {
            "REQUEST_METHOD": request.method,
            "SCRIPT_NAME": "",
            "PATH_INFO": to_wsgi_str(
                escape.url_unescape(request.path, encoding=None, plus=False)
            ),
            "QUERY_STRING": request.query,
            "REMOTE_ADDR": request.remote_ip,
            "SERVER_NAME": host,
            "SERVER_PORT": str(port),
            "SERVER_PROTOCOL": request.version,
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": request.protocol,
            "wsgi.input": body,
            "wsgi.errors": sys.stderr,
            "wsgi.multithread": False,
            "wsgi.multiprocess": True,
            "wsgi.run_once": False,
        }
        if "Content-Type" in request.headers:
            environ["CONTENT_TYPE"] = request.headers.pop("Content-Type")
        if "Content-Length" in request.headers:
            environ["CONTENT_LENGTH"] = request.headers.pop("Content-Length")
        for key, value in request.headers.items():
            environ["HTTP_" + key.replace("-", "_").upper()] = value
        return environ

    def prepare(self):
        # Accept up to 2GB upload data.
        self.request.connection.set_max_body_size(2 << 30)

    @gen.coroutine
    def data_received(self, chunk):
        if self.body_tempfile is not None:
            yield self.executor.submit(lambda: self.body_tempfile.write(chunk))
        else:
            self.body_chunks.append(chunk)

            limit = auth.getUserLimit(
                pages.getAcessingUser(self.request), "web.maxbytes"
            )

            # User has not configured limits, use at least 1M
            limit = max(10**6, limit)

            if sum(len(c) for c in self.body_chunks) > limit:
                raise RuntimeError("Reques body too big for user limit")

            # When the request body grows larger than 5 MB we dump all receiver chunks into
            # a temporary file to prevent high memory use. All subsequent body chunks will
            # be directly written into the tempfile.
            if sum(len(c) for c in self.body_chunks) > (10**6 * 5):
                self.body_tempfile = tempfile.NamedTemporaryFile("w+b")

                def copy_to_file():
                    for c in self.body_chunks:
                        self.body_tempfile.write(c)
                    # Remove the chunks to clear the memory.
                    self.body_chunks[:] = []

                yield self.executor.submit(copy_to_file)

    @gen.coroutine
    def get(self):
        data = {}
        response = []

        def start_response(status, response_headers, exc_info=None):
            data["status"] = status
            data["headers"] = response_headers
            return response.append

        environ = self.environ(self.request)
        app_response = yield self.executor.submit(
            self.wsgi_application, environ, start_response
        )
        app_response = iter(app_response)

        if not data:
            raise Exception("WSGI app did not call start_response")

        try:
            exhausted = object()

            def next_chunk():
                try:
                    return next(app_response)
                except StopIteration:
                    return exhausted

            for i in itertools.count():
                chunk = yield self.executor.submit(next_chunk)
                if i == 0:
                    status_code, reason = data["status"].split(None, 1)
                    status_code = int(status_code)
                    headers = data["headers"]
                    self.set_status(status_code, reason)
                    for key, value in headers:
                        self.set_header(key, value)
                    c = b"".join(response)
                    if c:
                        self.write(c)
                        yield self.flush()
                if chunk is not exhausted:
                    self.write(chunk)
                    yield self.flush()
                else:
                    break
        except StreamClosedError:
            _logger.debug("stream closed early")
        finally:
            # Close the temporary file to make sure that it gets deleted.
            if self.body_tempfile is not None:
                try:
                    self.body_tempfile.close()
                except OSError as e:
                    _logger.warning(e)

            if hasattr(app_response, "close"):
                yield self.executor.submit(app_response.close)

    post = put = delete = head = options = get

    @property
    def executor(self):
        cls = type(self)
        if not hasattr(cls, "_executor"):
            cls._executor = futures.ThreadPoolExecutor(cls.thread_pool_size)
        return cls._executor
