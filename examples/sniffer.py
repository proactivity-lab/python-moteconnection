"""
This example sets up a connection and listens to all incoming packets.

To run this example as a script, the following command:
```
$ python -m example.sniffer sf@location:port
```
"""
from __future__ import print_function

from argparse import ArgumentParser
from functools import partial
import logging
import time

from moteconnection.connection import Connection
from moteconnection.message import MessageDispatcher


def start_listen(connection_string):
    """Begins listening for incoming packets."""

    connection = construct_connection(connection_string)
    while 1:
        try:
            time.sleep(100)
        except (KeyboardInterrupt, SystemExit) as e:
            print("Received {!r}".format(e))
            print("Shutting down")
            connection.disconnect()
            connection.join()
            break

    connection.disconnect()
    connection.join()


def construct_connection(connection_string):
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

    dispatcher = MessageDispatcher()
    # This example uses a callback function (print in this case). The callback function
    # _must_ take exactly 1 positional argument. That argument will be an instance of
    # `moteconnection.message.Message`.
    # The alternatice method to using a callback function is to pass an instance of
    # `queue.Queue` (python3) or `Queue.Queue` (python2) to these methoods.
    dispatcher.register_default_snooper(print)
    dispatcher.register_default_receiver(print)
    connection.register_dispatcher(dispatcher)
    return connection


def get_args():
    """
    Parses the arguments and returns them.

    :rtype argparse.Namespace
    """
    parser = ArgumentParser(description='An example moteconnection listening program.')
    parser.add_argument('connection',
                        help="The connection string used to connect to the device. "
                             "Can be a serial forwarder address or a serial device address.")
    parser.add_argument('--verbose', '-v',
                        action='store_true',
                        default=False,
                        help='Verbose mode (displays moteconnection logs).')
    return parser.parse_args()


def main():
    """Main entrypoint to the sniffer application."""
    args = get_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    start_listen(connection_string=args.connection)


if __name__ == '__main__':
    main()
