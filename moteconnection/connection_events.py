"""connection_events.py: Connection event types."""

from enum import Enum


__author__ = "Raido Pahtma"
__license__ = "MIT"


class ConnectionEvents(Enum):
    MESSAGE_INCOMING = 0
    MESSAGE_OUTGOING = 1
    EVENT_START_CONNECT = 3
    EVENT_CONNECTED = 4
    EVENT_DISCONNECTED = 5
