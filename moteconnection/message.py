__author__ = "Raido Pahtma"
__license__ = "MIT"

import struct
from moteconnection.connection import Dispatcher
from moteconnection.packet import Packet

import logging
log = logging.getLogger(__name__)


AM_BROADCAST_ADDR = 0xFFFF


class Message(Packet):
    STRUCT_FORMAT_STRING = "! B H H B B B"
    STRUCT_FORMAT_SIZE = struct.calcsize(STRUCT_FORMAT_STRING)

    def __init__(self):
        """ Fields are initialized to None to detect if the user has set them
        or they should be set by a messaging layer to a default value."""
        super(Message, self).__init__(dispatch=0)
        self._destination = None
        self._source = None
        self._group = None
        self._type = None
        self._payload = ""
        self._footer = ""

    @property
    def group(self):
        if self._group is None:
            return 0
        return self._group

    @group.setter
    def group(self, group):
        self._group = group

    @property
    def destination(self):
        if self._destination is None:
            return 0
        return self._destination

    @destination.setter
    def destination(self, destination):
        self._destination = destination

    @property
    def source(self):
        if self._source is None:
            return 0
        return self._source

    @source.setter
    def source(self, source):
        self._source = source

    @property
    def type(self):
        if self._type is None:
            return 0
        return self._type

    @type.setter
    def type(self, ptype):
        self._type = ptype

    def __str__(self):
        return "{{{0.group:02X}}}{0.source:04X}->{0.destination:04X}[{0.type:02X}]{1:3d}: {2:s}".format(
            self, len(self._payload), self._payload.encode("hex").upper())

    def serialize(self):
        return struct.pack(Message.STRUCT_FORMAT_STRING, self.dispatch, self.destination, self.source,
                           len(self._payload), self.group, self.type) + self._payload + self._footer

    @staticmethod
    def deserialize(data):
        m = Message()
        try:
            m._dispatch, m._destination, m._source, length, m._group, m._type = struct.unpack(
                Message.STRUCT_FORMAT_STRING, data[:Message.STRUCT_FORMAT_SIZE])
            rest = data[Message.STRUCT_FORMAT_SIZE:]
            if length <= len(rest):
                m._payload = rest[:length]
                m._footer = rest[length:]
            else:
                raise ValueError("Message payload length > actual length {} > {}".format(length, len(rest)))
        except struct.error as e:
            raise ValueError("Message unpacking error: {}".format(e.message))

        return m


class MessageDispatcher(Dispatcher):

    def __init__(self, address=0x0001, group=0x22, dispatch=0):
        super(MessageDispatcher, self).__init__(dispatch)
        self._address = address
        self._group = group
        self._receivers = {}
        self._default_receiver = None
        self._snoopers = {}
        self._default_snooper = None

    def send(self, message):
        if message._source is None:
            message._source = self._address
        if message._group is None:
            message._group = self._group

        self._sender(message)

    def register_receiver(self, ptype, receiver):
        if receiver is None and ptype in self._receivers:
            del self._receivers[ptype]
        else:
            self._receivers[ptype] = receiver

    def register_default_receiver(self, receiver):
        self._default_receiver = receiver

    def register_snooper(self, ptype, snooper):
        if snooper is None and ptype in self._snoopers:
            del self._snoopers[ptype]
        else:
            self._snoopers[ptype] = snooper

    def register_default_snooper(self, snooper):
        self._default_snooper = snooper

    def receive(self, data):
        try:
            m = Message.deserialize(data)
            if m.destination in (self._address, 0, AM_BROADCAST_ADDR):
                if m.type in self._receivers:
                    self._deliver(self._receivers[m.type], m)
                elif self._default_receiver is not None:
                    self._deliver(self._default_receiver, m)
            else:
                if m.type in self._snoopers:
                    self._deliver(self._snoopers[m.type], m)
                elif self._default_snooper is not None:
                    self._deliver(self._default_snooper, m)
        except ValueError as e:
            log.warning("Failed to deserialize message {}: {}".format(data.encode("hex").upper(), e.message))
