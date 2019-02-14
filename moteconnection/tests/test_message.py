import codecs
from unittest import TestCase

from moteconnection.message import Message


class MessageConversionTester(TestCase):
    def setUp(self):
        self.message = Message(ptype=0xF0, destination=0x0015, payload=b'\x12\xAB')
        self.expected = str(self.message)

    def test_old_format(self):
        result = '%s' % self.message
        self.assertEqual(result, self.expected)

    def test_new_format(self):
        result = '{!s}'.format(self.message)
        self.assertEqual(result, self.expected)
