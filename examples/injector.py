"""
This example sets up a connection and sends a packet specified on command line as a hex encoded string

To run this example as a script, the following command:
```
$ python -m example.injector sf@location:port DEADBEEFDEADBEEF
```
"""
from __future__ import print_function

from argparse import ArgumentParser
from functools import partial
import logging
import time
from codecs import decode

from moteconnection.connection import Connection
from moteconnection.message import MessageDispatcher, Message


def send_packet(connection_string, amid, dest, src, hex_data):
    """Send the packet with specified AM ID."""

    connection = construct_connection(connection_string, src)

    bin_data = decode(hex_data, "hex")
    msg = Message(amid, dest, bin_data)

    time.sleep(0.2)
    connection.send(msg)
    time.sleep(0.2)

    connection.disconnect()
    connection.join()


def construct_connection(connection_string, src):
    """
    Constructs the connection object and returns it.

    The connection string takes the form of protocol@location:port_or_baud
    Examples: sf@localhost:9002
              serial@/dev/ttyUSB0

    :param str connection string: A string in the form of protocol@location:port_or_baud
    :rtype: moteconnection.connection.Connection
    """
    connection = Connection()
    connection.connect(
        connection_string,
        reconnect=10,
        connected=partial(print, "Connected to {}".format(connection_string)),
        disconnected=partial(print, "Disconnected from {}".format(connection_string))
    )

    dispatcher = MessageDispatcher(src)
    connection.register_dispatcher(dispatcher)
    return connection


def get_args():
    """
    Parses the arguments and returns them.

    :rtype argparse.Namespace
    """
    parser = ArgumentParser(description='An example moteconnection sending program.')
    parser.add_argument('connection',
                        help="The connection string used to connect to the device. "
                             "Can be a serial forwarder address or a serial device address.")
    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        default=False,
                        help='Verbose mode (displays moteconnection logs).')
    parser.add_argument('--amid', '-a',
                        default='0x76',
                        help='AM ID')
    parser.add_argument('--dest', '-d',
                        default='0xFFFF',
                        help='Destination address')
    parser.add_argument('--src', '-s',
                        default='0xCCC4',
                        help='Source address')
    parser.add_argument("data",
                        help='Binary data (hex)')
    return parser.parse_args()


def main():
    """Main entrypoint to the sniffer application."""
    args = get_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    send_packet(args.connection, int(args.amid, base=0), int(args.dest, base=0), int(args.src, base=0), args.data)


if __name__ == '__main__':
    main()
