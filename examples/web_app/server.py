# -*- coding: utf-8 -*-
"""A development server for the browser backend, without dependencies.

Serves one :class:`coolplot.render.web.WebRenderer` to browsers: ``/``
is the page, ``/stream`` the server-sent event stream of patches (a new
client first gets the whole chart), ``/input`` receives pointer input.
It lives with the examples because it is a starting point for an
application, not part of the library: a real application embeds the
renderer in its own web framework (how-to "In the browser" in the documentation).

Some care is taken because a web page in any browser tab can reach a
local server: requests must name this server in their ``Host`` header
(against DNS rebinding) and input must come from the server's own page
(``Origin``) as JSON. A browser that stops reading the stream is
dropped instead of collecting messages without end; its page then
reconnects and starts again from the whole chart.
"""
from __future__ import annotations

import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import List, Optional, Set

from coolplot.render.web import WebRenderer


class _Client(queue.Queue):
    """The messages waiting for one browser; ``dropped`` once it fell too far behind."""

    def __init__(self, maxsize: int):
        super().__init__(maxsize=maxsize)
        self.dropped = False


class WebServer:
    """Serve one renderer to browsers, without dependencies

    ``/`` is the page, ``/stream`` the server-sent event stream of patches
    (a new client first gets the whole chart), ``/input`` receives pointer
    input. Run it with :meth:`start` (in a background thread) and stop it
    with :meth:`stop`. Meant for development and small tools; it binds to
    the local machine by default.

    Some care is taken because a web page in any browser tab can reach a
    local server: requests must name this server in their ``Host`` header
    (against DNS rebinding) and input must come from the server's own page
    (``Origin``) as JSON. A browser that stops reading the stream is
    dropped instead of collecting messages without end; its page then
    reconnects and starts again from the whole chart.
    """

    #: Largest input message, in bytes.
    MAX_INPUT = 64 * 1024
    #: Messages waiting for one browser before it is dropped.
    MAX_QUEUED = 1000

    def __init__(self, renderer: WebRenderer, host: str = "127.0.0.1", port: int = 0, title: str = "CoolPlot"):
        self.renderer = renderer
        self.title = title
        self._clients: List[_Client] = []
        self._clients_lock = threading.Lock()
        self._started = False
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            timeout = 30   # seconds; a browser that stops reading is cut off

            def log_message(self, *args):
                pass   # keep the console quiet

            def _refused(self) -> bool:
                host = self.headers.get("Host", "")
                origin = self.headers.get("Origin")
                if server._hosts is not None and host not in server._hosts:
                    self.send_error(403, "Unknown host")
                    return True
                if origin is not None and origin != "http://" + host:
                    self.send_error(403, "Foreign origin")
                    return True
                return False

            def _reply(self, code: int):
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                if self._refused():
                    return
                if self.path == "/":
                    body = server.renderer.page(stream="/stream", input="/input", title=server.title).encode("ascii")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/stream":
                    self._stream()
                else:
                    self.send_error(404)

            def do_POST(self):
                if self.path != "/input":
                    self.send_error(404)
                    return
                if self._refused():
                    return
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    self.send_error(415, "Input has to be JSON")
                    return
                try:
                    length = int(self.headers.get("Content-Length", ""))
                except ValueError:
                    self.send_error(411)
                    return
                if not 0 < length <= server.MAX_INPUT:
                    self.send_error(413)
                    return
                try:
                    message = server.renderer.check_input(self.rfile.read(length))
                except ValueError:
                    self._reply(400)
                    return
                try:
                    server.renderer.receive(message)
                finally:
                    # Answered after the input is handled: the page sends its
                    # next input only then, so a quick click cannot arrive as
                    # a release before its press on another server thread
                    self._reply(204)

            def _stream(self):
                self.close_connection = True   # a stream has no length: never reuse the socket
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                client = _Client(maxsize=server.MAX_QUEUED)
                # Under the renderer's lock no patch can be sent between
                # the snapshot and the registration of this browser
                with server.renderer.lock:
                    client.put(server.renderer.snapshot())
                    with server._clients_lock:
                        server._clients.append(client)
                try:
                    while not server._stopping.is_set() and not client.dropped:
                        try:
                            message = client.get(timeout=1.0)
                        except queue.Empty:
                            self.wfile.write(b": keep-alive\n\n")
                            self.wfile.flush()
                            continue
                        self.wfile.write(b"data: " + message.encode("ascii") + b"\n\n")
                        self.wfile.flush()
                except OSError:
                    pass   # the browser went away, or stopped reading (timeout)
                finally:
                    with server._clients_lock:
                        server._clients.remove(client)

        self._stopping = threading.Event()
        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self._httpd.daemon_threads = True
        # Host headers that name this server; None when it is bound to a
        # public address, where the name it is reached by is not known
        bound = self._httpd.server_address[1]
        self._hosts: Optional[Set[str]] = None
        if host in ("127.0.0.1", "localhost"):
            self._hosts = {"127.0.0.1:{0}".format(bound), "localhost:{0}".format(bound)}
        self._thread: Optional[threading.Thread] = None
        renderer.listen(self._broadcast)

    def _broadcast(self, message: str):
        with self._clients_lock:
            for client in self._clients:
                try:
                    client.put_nowait(message)
                except queue.Full:
                    client.dropped = True   # its page reconnects and gets the whole chart

    @property
    def url(self) -> str:
        host, port = self._httpd.server_address[:2]
        if isinstance(host, bytes):   # only for a Unix socket, which this server never binds
            host = host.decode()
        return "http://{0}:{1}/".format(host, port)

    def start(self) -> "WebServer":
        self._started = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def serve_forever(self):
        """Serve in the current thread until interrupted."""
        self._started = True
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        self._stopping.set()
        if self._started:   # shutdown() waits for serve_forever, which never ran otherwise
            self._httpd.shutdown()
        self._httpd.server_close()
        self.renderer.unlisten(self._broadcast)
