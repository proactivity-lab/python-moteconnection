"""connection.py: Connection for connecting to serial or sf ports."""

import time
import Queue
import threading

from moteconnection.utils import split_in_two
from moteconnection.connection_events import ConnectionEvents
from moteconnection.connection_serial import SerialConnection
from moteconnection.connection_forwarder import SfConnection

import logging
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


__author__ = "Raido Pahtma"
__license__ = "MIT"


class DispatcherError(Exception):
    pass


class ConnectionBusyException(Exception):
    pass


class ConnectionException(Exception):
    pass


class Connection(threading.Thread):

    def __init__(self, autostart=True):
        super(Connection, self).__init__()
        self._dispatchers = {}

        self._real_connection = None

        self._last_connect = 0

        self._connection_type = None
        self._connection_info = None

        self._reconnect_period = None
        self._event_connected = None
        self._event_disconnected = None

        # New connection types can be added here
        self.connection_types = {"loopback": LoopbackConnection, "sf": SfConnection, "serial": SerialConnection}

        self._queue = Queue.Queue()

        # Can be connected, disconnected or somewhere in between
        self._connected = threading.Event()
        self._connected.clear()
        self._disconnected = threading.Event()
        self._disconnected.set()

        self._alive = threading.Event()
        self._alive.set()

        if autostart:
            self.start()

    def join(self, timeout=None):
        self._alive.clear()
        if self._real_connection is not None:
            self._real_connection.join(timeout)
        threading.Thread.join(self, timeout)

    def send(self, packet):
        if packet.dispatch in self._dispatchers:
            self._dispatchers[packet.dispatch].send(packet)
        else:
            raise DispatcherError("No dispatcher for sending {:02X}".format(packet.dispatch))

    def register_dispatcher(self, dispatcher):
        self.remove_dispatcher(dispatcher.dispatch)
        self._dispatchers[dispatcher.dispatch] = dispatcher
        dispatcher.attach(self._subsend)

    def remove_dispatcher(self, dispatch):
        if dispatch in self._dispatchers:
            self._dispatchers[dispatch].detach()
            del self._dispatchers[dispatch]

    def retrieve_dispatcher(self, dispatch):
        if dispatch in self._dispatchers:
            return self._dispatchers[dispatch]
        return None

    def connected(self):
        return self._connected.isSet() and not self._disconnected.isSet()

    def connect(self, connection_string, reconnect=None, connected=None, disconnected=None):
        """
        :param reconnect: Optional reconnect period. Connection is attempted once if not set.
        :param connected: Optional callback for receiving connection establishment notifications.
        :param disconnected: Optional callback for receiving disconnection notifications.
        :return:
        """
        if self._connected.isSet() is False and self._disconnected.isSet():
            log.debug("connect")
            conntype, conninfo = split_in_two(connection_string, "@")
            if conntype in self.connection_types:
                self._connection_type = conntype
                self._connection_info = conninfo

                self._reconnect_period = reconnect
                self._event_connected = connected
                self._event_disconnected = disconnected

                self._disconnected.clear()
                self._queue.put((ConnectionEvents.EVENT_START_CONNECT, None))
            else:
                raise ConnectionException("Specified connection type {:s} not supported".format(conntype))
        else:
            raise ConnectionBusyException("Busy")

    def disconnect(self):
        self._reconnect_period = None
        log.debug("disconnect")

        while not self._connected.is_set() and not self._disconnected.is_set():  # Connecting
            log.debug("waiting")
            self._connected.wait(0.1)

        if self._real_connection is not None:
            self._real_connection.join()

        self._disconnected.wait()

    def _subsend(self, packet):
        if self._real_connection is not None:
            self._queue.put((ConnectionEvents.MESSAGE_OUTGOING, packet))
        else:
            if packet.callback is not None:
                packet.callback(packet, False)

    def _receive(self, data):
        if len(data) > 0:
            dispatch = ord(data[0])
            if dispatch in self._dispatchers:
                self._dispatchers[dispatch].receive(data)
            else:
                log.debug("No dispatcher for receiving {:02X}".format(dispatch))
        else:
            log.debug("Received 0 bytes of data ...")

    def run(self):
        while self._alive.isSet():
            try:
                item_type, item = self._queue.get(True, 1.0)
                if item_type == ConnectionEvents.MESSAGE_INCOMING:
                    log.debug("incoming {:s}".format(item.encode("hex")))
                    self._receive(item)
                elif item_type == ConnectionEvents.MESSAGE_OUTGOING:
                    log.debug("outgoing {:s}".format(item))
                    self._real_connection.send(item)
                elif item_type == ConnectionEvents.EVENT_CONNECTED:
                    log.info("connected")
                    self._connected.set()
                    self._disconnected.clear()
                    if callable(self._event_connected):
                        self._event_connected()
                elif item_type == ConnectionEvents.EVENT_DISCONNECTED:
                    log.info("disconnected")
                    self._connected.clear()
                    self._disconnected.set()
                    if callable(self._event_disconnected):
                        self._event_disconnected()
                elif item_type == ConnectionEvents.EVENT_START_CONNECT:
                    self._connect()
                else:
                    raise Exception("item_type is unknown!")
            except Queue.Empty:
                if self._disconnected.isSet():
                    if self._reconnect_period is not None and self._reconnect_period >= 0:
                        if time.time() > self._last_connect + self._reconnect_period:
                            self._queue.put((ConnectionEvents.EVENT_START_CONNECT, None))
                continue

    def _connect(self):
        self._last_connect = time.time()
        self._real_connection = self.connection_types[self._connection_type](self._queue, self._connection_info)


class Dispatcher(object):

    def __init__(self, dispatch):
        self._dispatch = dispatch
        self._sender = None

    @property
    def dispatch(self):
        return self._dispatch

    @staticmethod
    def _deliver(receiver, message):
        if isinstance(receiver, Queue.Queue):
            receiver.put(message)
        else:
            receiver(message)

    def attach(self, sender):
        self._sender = sender

    def detach(self):
        self._sender = None

    def send(self, packet):
        raise NotImplementedError

    def receive(self, data):
        raise NotImplementedError


class LoopbackConnection(threading.Thread):

    def __init__(self, event_queue, info):
        super(LoopbackConnection, self).__init__()
        self._queue = event_queue
        self._info = info
        self.start()

    def join(self, timeout=None):
        self._queue.put((ConnectionEvents.EVENT_DISCONNECTED, None))
        threading.Thread.join(self, timeout)

    def send(self, data):
        self._queue.put((ConnectionEvents.MESSAGE_INCOMING, data))

    def run(self):
        self._queue.put((ConnectionEvents.EVENT_CONNECTED, None))
