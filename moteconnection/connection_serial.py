""""connection_serial.py: Serial connection object."""

try:
    import Queue
    from StringIO import StringIO
except ImportError:
    import queue as Queue
    from io import StringIO

import serial
import time
import struct

import threading
from moteconnection.utils import split_in_two
from moteconnection.connection_events import ConnectionEvents

import logging
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


__author__ = "Raido Pahtma"
__license__ = "MIT"


def itut_g16_crc(data):
    crc = 0
    for abyte in data:
        crc ^= ord(abyte) << 8
        for i in range(0, 8):
            if crc & 0x8000 != 0:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


class SerialPacketException(Exception):
    pass


class SerialConnection(threading.Thread):

    HDLC_FRAMING_BYTE = 0x7e
    HDLC_ESCAPE_BYTE = 0x7d
    HDLC_XOR_BYTE = 0x20
    SERIAL_PROTOCOL_ACK = 0x43
    SERIAL_PROTOCOL_PACKET = 0x44
    SERIAL_PROTOCOL_NO_ACK_PACKET = 0x45
    SERIAL_ACK_TIMEOUT = 0.2
    SERIAL_PORT_TIMEOUT = 0.01
    SERIAL_SEND_TRIES = 1

    def __init__(self, event_queue, port_and_baud, require_acks=True):
        super(SerialConnection, self).__init__()
        self._queue = event_queue

        self._serial_port = None

        self._settings_port, baud = split_in_two(port_and_baud, ":")
        if len(baud) > 0:
            self._settings_baud = int(baud)
        else:
            self._settings_baud = 115200

        self._alive = threading.Event()
        self._alive.set()

        self._connected = threading.Event()
        self._connected.clear()

        if require_acks:
            self._seq_out = 0
        else:
            self._seq_out = None
        self._seq_in = None

        self._outqueue = Queue.Queue()
        self._recv_length = 0
        self._recv_buf = None

        self.start()

    def send(self, packet):
        if self._connected.isSet():
            log.debug("snd {:s}".format(packet))
            self._outqueue.put(packet)
        else:
            log.debug("drop {:s}".format(packet))

    def join(self, timeout=None):
        self._alive.clear()
        if self._serial_port is not None:
            self._serial_port.close()
        threading.Thread.join(self, timeout)

    def _disconnected(self):
        log.debug("disconnected")
        self._connected.clear()
        self._queue.put((ConnectionEvents.EVENT_DISCONNECTED, None))

    def _process_incoming_packet(self, data):
        log.debug("recv {:s}".format(data.encode("hex")))
        if len(data) > 2:
            packet_data = data[:len(data)-2]
            lcrc = ord(data[len(data)-2:-1])
            mcrc = ord(data[len(data)-1:])
            packet_crc = (mcrc << 8) + lcrc
            crc = itut_g16_crc(packet_data)
            if crc != packet_crc:
                raise SerialPacketException("crc mismatch {:04X} != {:04X}".format(crc, packet_crc))

            if len(packet_data) > 0:
                packet_protocol = ord(data[0])
                packet_data = packet_data[1:]

                if packet_protocol == self.SERIAL_PROTOCOL_ACK:
                    if len(packet_data) > 0:
                        return ord(packet_data[0]), None
                    else:
                        raise SerialPacketException("not enough data for SERIAL_PROTOCOL_ACK")

                if packet_protocol == self.SERIAL_PROTOCOL_PACKET:
                    if len(packet_data) > 1:
                        return ord(packet_data[0]), packet_data[1:]
                    else:
                        raise SerialPacketException("not enough data for SERIAL_PROTOCOL_PACKET")

                elif packet_protocol == self.SERIAL_PROTOCOL_NO_ACK_PACKET:
                    return None, packet_data

                else:
                    raise SerialPacketException("unknown serial packet protocol {:02X}".format(packet_protocol))
            else:
                raise SerialPacketException("not enough data for serial protocols")
        else:
            raise SerialPacketException("not enough data for serial protocols")

    def _write(self, seq, packet):
        data = StringIO()
        if seq is None:
            data.write(chr(self.SERIAL_PROTOCOL_NO_ACK_PACKET))
        else:
            if packet is None:
                data.write(chr(self.SERIAL_PROTOCOL_ACK))
            else:
                data.write(chr(self.SERIAL_PROTOCOL_PACKET))
            data.write(chr(seq))
        data.write(packet)
        data.write(struct.pack("<H", itut_g16_crc(data.getvalue())))

        escaped = StringIO()
        escaped.write(chr(self.HDLC_FRAMING_BYTE))
        for abyte in data.getvalue():
            obyte = ord(abyte)
            if obyte == self.HDLC_ESCAPE_BYTE or obyte == self.HDLC_FRAMING_BYTE:
                escaped.write(chr(self.HDLC_ESCAPE_BYTE))
                escaped.write(chr(obyte ^ self.HDLC_XOR_BYTE))
            else:
                escaped.write(abyte)
        escaped.write(chr(self.HDLC_FRAMING_BYTE))

        log.debug("write {:s}".format(escaped.getvalue().encode("hex")))
        self._serial_port.write(escaped.getvalue())

    def run(self):
        try:
            self._serial_port = serial.Serial(self._settings_port, self._settings_baud,
                                              bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                                              stopbits=serial.STOPBITS_ONE, xonxoff=False, rtscts=False,
                                              timeout=self.SERIAL_PORT_TIMEOUT)

            self._serial_port.flushInput()

            self._connected.set()
            self._queue.put((ConnectionEvents.EVENT_CONNECTED, None))
            log.debug("connected")

            outgoing = None
            serialized = None
            timestamp = None
            tries = 0

            recv_buf = StringIO()
            escape = False

            while self._alive.isSet():
                data = self._serial_port.read()
                if len(data) > 0:
                    data = ord(data)
                    # log.debug("rcv {:02X}".format(data))
                    if data == self.HDLC_FRAMING_BYTE:
                        if recv_buf.len > 0:
                            try:
                                seq, packet = self._process_incoming_packet(recv_buf.getvalue())
                                if seq is None:
                                    if packet is not None:
                                        self._queue.put((ConnectionEvents.MESSAGE_INCOMING, packet))
                                    else:
                                        log.warning("incoming data dropped")

                                else:
                                    if packet is not None:
                                        if seq != self._seq_in:
                                            self._seq_in = seq
                                            self._queue.put((ConnectionEvents.MESSAGE_INCOMING, packet))
                                        else:
                                            log.warning("duplicate for {:02X}".format(seq))

                                        self._write(seq, None)  # Ack in any case
                                    else:
                                        if outgoing is not None and self._seq_out is not None:
                                            if seq == self._seq_out:
                                                log.debug("ack for {:02X}".format(seq))
                                                if outgoing.callback is not None:
                                                    outgoing.callback(outgoing, True)
                                                outgoing = None
                                                self._seq_out = (self._seq_out + 1) & 0xFF
                                            else:
                                                log.warning("ack for {:02X}, waiting {:02X}".format(seq, self._seq_out))
                                        else:
                                            log.warning("ack for {:02X}, waiting none".format(seq))

                            except SerialPacketException as e:
                                log.warning(e.message)
                            finally:
                                recv_buf = StringIO()

                    elif data == self.HDLC_ESCAPE_BYTE:
                        escape = True
                    else:
                        if escape:
                            escape = False
                            data ^= self.HDLC_XOR_BYTE
                        recv_buf.write(chr(data))
                else:
                    if outgoing is None:
                        try:
                            outgoing = self._outqueue.get_nowait()
                            serialized = outgoing.serialize()
                            tries = self.SERIAL_SEND_TRIES
                            timestamp = 0
                        except Queue.Empty:
                            pass

                    if outgoing is not None:
                        if time.time() > timestamp + self.SERIAL_ACK_TIMEOUT:
                            if tries > 0:
                                self._write(self._seq_out, serialized)
                                if self._seq_out is not None:
                                    tries -= 1
                                    timestamp = time.time()
                                else:
                                    if outgoing.callback is not None:
                                        outgoing.callback(outgoing, False)
                                    outgoing = None
                            else:
                                if outgoing.callback is not None:
                                    outgoing.callback(outgoing, False)
                                outgoing = None
                                if self._seq_out is not None:
                                    log.warning("ack for {:02X} not received".format(self._seq_out))
                                    self._seq_out = (self._seq_out + 1) & 0xFF

        except (serial.SerialException, OSError) as e:
            log.error("serial.error: {:s}".format(e.message))
        finally:
            self._disconnected()
