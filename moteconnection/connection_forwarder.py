""""connection_forwarder.py: SF connection object."""

import logging
import socket
import threading
from codecs import encode

from six import BytesIO

from moteconnection.connection_events import ConnectionEvents
from moteconnection.utils import split_in_two

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


__author__ = "Raido Pahtma"
__license__ = "MIT"


class SfConnection(threading.Thread):

    PROTOCOL_VERSION = b"U "

    def __init__(self, event_queue, host_and_port):
        super(SfConnection, self).__init__()
        self._queue = event_queue

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        host, port = split_in_two(host_and_port, ":")
        if len(port) > 0:
            port = int(port)
        else:
            port = 9002

        self._server_address = (host, port)

        self._alive = threading.Event()
        self._alive.set()

        self._connected = threading.Event()
        self._connected.clear()

        self._recv_length = 0
        self._recv_buf = None

        self.start()

    def send(self, packet):
        data = packet.serialize()
        acked = False
        if self._connected.isSet():
            try:
                self._socket.sendall(chr(len(data)).encode())
                self._socket.sendall(data)
                acked = True
                log.debug("snt %s", encode(data, "hex"))
            except socket.error:
                self._disconnected()
        else:
            log.debug("drop %s", encode(data, "hex"))

        if packet.callback:
            packet.callback(packet, acked)

    def join(self, timeout=None):
        self._alive.clear()
        self._socket.close()
        threading.Thread.join(self, timeout)

    def _disconnected(self):
        log.debug("disconnected")
        self._connected.clear()
        self._queue.put((ConnectionEvents.EVENT_DISCONNECTED, None))
        self._socket.close()

    def _connect(self):
        self._socket.connect(self._server_address)

        log.debug("socket connected")

        self._socket.sendall(self.PROTOCOL_VERSION)
        log.debug("handshake sent")

        buf = BytesIO()
        while len(buf.getvalue()) < 2:
            data = self._socket.recv(2 - len(buf.getvalue()))
            if data:
                buf.write(data)
            else:
                raise socket.error("no data received")

        if buf.getvalue() == b"U ":
            log.debug("handshake success")
            self._connected.set()
            self._queue.put((ConnectionEvents.EVENT_CONNECTED, None))
        else:
            raise socket.error("handshake mismatch {!s} != {!s}".format(self.PROTOCOL_VERSION, buf.getvalue()))

    def _receive(self):
        try:
            if self._recv_length == 0:
                length = self._socket.recv(1)
                if length:
                    self._recv_length = ord(length)
                    self._recv_buf = BytesIO()
                else:
                    raise socket.error("no data received")
            else:
                data = self._socket.recv(self._recv_length - len(self._recv_buf.getvalue()))
                if data:
                    self._recv_buf.write(data)
                    if self._recv_length == len(self._recv_buf.getvalue()):
                        log.debug("rcv %s", encode(self._recv_buf.getvalue(), "hex"))
                        self._recv_length = 0
                        return self._recv_buf.getvalue()
                else:
                    raise socket.error("no data received")

        except socket.timeout:
            pass  # timeouts are normal

        return None

    def run(self):
        try:
            self._connect()
            self._socket.settimeout(0.1)
            while self._alive.isSet():
                data = self._receive()
                if data is not None:
                    self._queue.put((ConnectionEvents.MESSAGE_INCOMING, data))
        except socket.error as e:
            log.error("socket.error: %s", e.args)
        finally:
            self._disconnected()
