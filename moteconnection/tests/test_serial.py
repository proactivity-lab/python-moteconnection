import codecs
from unittest import TestCase
from contextlib import contextmanager

import mock
import six
from six.moves import queue
import serial

from moteconnection.connection import Connection
from moteconnection.packet import Packet, PacketDispatcher


class IncomingPacketTester(TestCase):
    def setUp(self):
        serial_patch = mock.patch('moteconnection.connection_serial.serial.Serial')
        self.serial_mock = serial_patch.start()
        self.addCleanup(serial_patch.stop)

    def test_incoming_ack_packet(self):
        """
        Tests the incoming ack packets over serial.
        """

        def iterator(packet):
            for i in range(len(packet)):
                yield packet[i:i + 1]
            while 1:
                yield b''

        def compare(actual, expected):
            self.assertEqual(actual.dispatch, expected.dispatch)
            self.assertEqual(actual.payload, expected.payload)

        # Our sequence numbers don't grow... New connection each time should fix that
        @contextmanager
        def get_connection(receiver, packet):
            self.serial_mock.return_value.read.side_effect = iterator(packet)
            connection = Connection()
            dispatcher = PacketDispatcher(0xFF)
            dispatcher.register_receiver(receiver)
            connection.register_dispatcher(dispatcher)
            dispatcher = PacketDispatcher(0x0E)
            dispatcher.register_receiver(receiver)
            connection.register_dispatcher(dispatcher)
            connection.connect('serial@/dev/fake:123456789')
            try:
                yield connection
            finally:
                connection.disconnect()
                connection.join()

        receive_queue = queue.Queue()

        # First packet
        try:
            with get_connection(receive_queue, b'\x7E\x44\x00\xFF\x9D\xDF\x7E'):
                packet = receive_queue.get(timeout=1)
        except queue.Empty:
            self.fail('Did not receive enough packets (0)')
        expected = Packet(0xFF)
        compare(packet, expected)

        # Seconds packet
        try:
            with get_connection(receive_queue,
                                b'\x7E\x44\x00\x0E\x01\x02\x03\x04\x05\x06\x07'
                                b'\x08\x09\x0A\x0B\x0C\x0D\x0E\x0F\x3B\x8B\x7E'):
                packet = receive_queue.get(timeout=1)
        except queue.Empty:
            self.fail('Did not receive enough packets (1)')
        expected = Packet(0x0E)
        expected.payload = b'\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0A\x0B\x0C\x0D\x0E\x0F'
        compare(packet, expected)

        # Third packet
        try:
            with get_connection(receive_queue, b'\x7E\x44\x00\x0E\x7D\x5E\x7D\x5E\x7D\x5E\xED\xB9\x7E'):
                packet = receive_queue.get(timeout=1)
        except queue.Empty:
            self.fail('Did not receive enough packets (2)')
        expected = Packet(0x0E)
        expected.payload = b'\x7E\x7E\x7E'
        compare(packet, expected)

        # Fourth packet
        try:
            with get_connection(receive_queue, b'\x7E\x44\x00\x0E\x7D\x5D\x7D\x5E\x33\x62\x7E'):
                packet = receive_queue.get(timeout=1)
        except queue.Empty:
            self.fail('Did not receive enough packets (3)')
        expected = Packet(0x0E)
        expected.payload = b'\x7D\x7E'
        compare(packet, expected)

    def test_incoming_noack_packet(self):
        """
        Tests the incoming noack packets over serial.
        """
        pass


class OutgoingPacketTester(TestCase):
    def test_outgoing_ack_packet(self):
        """
        Tests the outgoing ack packets overs serial.
        """
        pass

    def test_outgoing_noack_packet(self):
        """
        Tests the outgoing noack packets overs serial.
        """
        pass
