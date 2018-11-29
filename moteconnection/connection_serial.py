""""connection_serial.py: Serial connection object."""

from six.moves import queue
from six import BytesIO

from codecs import encode
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
    for p in range(len(data)):
        crc ^= ord(data[p:p+1]) << 8
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

    HDLC_FRAMING_BYTE = b'\x7e'
    HDLC_ESCAPE_BYTE = b'\x7d'
    HDLC_XOR_BYTE = b'\x20'
    SERIAL_PROTOCOL_ACK = b'\x43'
    SERIAL_PROTOCOL_PACKET = b'\x44'
    SERIAL_PROTOCOL_NO_ACK_PACKET = b'\x45'
    SERIAL_ACK_TIMEOUT = 0.2
    SERIAL_PORT_TIMEOUT = 0.01
    SERIAL_SEND_TRIES = 1

    def __init__(self, event_queue, port_and_baud):
        super(SerialConnection, self).__init__()
        self._queue = event_queue

        self._serial_port = None

        self._settings_port, baud_acks = split_in_two(port_and_baud, ":")

        baud, acks = split_in_two(baud_acks, "*")
        if len(baud) > 0:
            self._settings_baud = int(baud)
        else:
            self._settings_baud = 115200

        require_acks = True
        if len(acks) > 0:
            if acks == "ACK":
                require_acks = True
            elif acks == "NOACK":
                require_acks = False
            else:
                log.warning("Unrecognized ACK configuration '%s'", acks)

        self._alive = threading.Event()
        self._alive.set()

        self._connected = threading.Event()
        self._connected.clear()

        if require_acks:
            self._seq_out = 0
        else:
            self._seq_out = None
        self._seq_in = None

        self._outqueue = queue.Queue()
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
        """

        :param bytes data:
        :return:
        """
        log.debug("recv %s", encode(data, "hex"))
        if len(data) > 2:
            packet_data = data[:-2]
            lcrc = ord(data[-2:-1])
            mcrc = ord(data[-1:])
            packet_crc = (mcrc << 8) + lcrc
            crc = itut_g16_crc(packet_data)
            if crc != packet_crc:
                raise SerialPacketException("crc mismatch {:04X} != {:04X}".format(crc, packet_crc))

            if len(packet_data) > 0:
                packet_protocol = data[0:1]    # python3 compatibility trick
                packet_data = packet_data[1:]

                if packet_protocol == self.SERIAL_PROTOCOL_ACK:
                    if len(packet_data) > 0:
                        return ord(packet_data[0:1]), None
                    else:
                        raise SerialPacketException("not enough data for SERIAL_PROTOCOL_ACK")

                if packet_protocol == self.SERIAL_PROTOCOL_PACKET:
                    if len(packet_data) > 1:
                        return ord(packet_data[0:1]), packet_data[1:]
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
        data = BytesIO()
        if seq is None:
            data.write(self.SERIAL_PROTOCOL_NO_ACK_PACKET)
        else:
            if packet is None:
                data.write(self.SERIAL_PROTOCOL_ACK)
            else:
                data.write(self.SERIAL_PROTOCOL_PACKET)
            data.write(chr(seq).encode())
        # Python3 does not allow writing 'None' to BytesIO
        if packet is not None:
            data.write(packet)
        data.write(struct.pack("<H", itut_g16_crc(data.getvalue())))

        escaped = BytesIO()
        escaped.write(self.HDLC_FRAMING_BYTE)
        datavalue = data.getvalue()
        for i in range(len(datavalue)):
            obyte = datavalue[i:i+1]
            if obyte == self.HDLC_ESCAPE_BYTE or obyte == self.HDLC_FRAMING_BYTE:
                escaped.write(self.HDLC_ESCAPE_BYTE)
                escaped.write(encode(chr(obyte ^ ord(self.HDLC_XOR_BYTE))))
            else:
                escaped.write(obyte)
        escaped.write(self.HDLC_FRAMING_BYTE)

        log.debug("write %s", encode(escaped.getvalue(), "hex"))
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

            recv_buf = BytesIO()
            escape = False

            while self._alive.isSet():
                data = self._serial_port.read()
                if len(data) > 0:
                    # log.debug("rcv %02X", data)
                    if data == self.HDLC_FRAMING_BYTE:
                        if len(recv_buf.getvalue()) > 0:
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
                                            log.warning("duplicate for %02X", seq)

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
                                                log.warning("ack for %02X, waiting %02X", seq, self._seq_out)
                                        else:
                                            log.warning("ack for %02X, waiting none", seq)

                            except SerialPacketException as e:
                                log.warning(e.args[0])
                            finally:
                                recv_buf = BytesIO()

                    elif data == self.HDLC_ESCAPE_BYTE:
                        escape = True
                    else:
                        if escape:
                            escape = False
                            data = encode(chr(ord(data[0:1]) ^ ord(self.HDLC_XOR_BYTE)))
                        recv_buf.write(data)
                else:
                    if outgoing is None:
                        try:
                            outgoing = self._outqueue.get_nowait()
                            serialized = outgoing.serialize()
                            tries = self.SERIAL_SEND_TRIES
                            timestamp = 0
                        except queue.Empty:
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
                                    log.warning("ack for %02X not received", self._seq_out)
                                    self._seq_out = (self._seq_out + 1) & 0xFF

        except (serial.SerialException, OSError) as e:
            log.error("serial.error: %s", e.args)
        finally:
            self._disconnected()
