__author__ = "Raido Pahtma"
__license__ = "MIT"

import glob
import sys
import os


def _list_windows_serial_ports():
    raise NotImplementedError("windows support")


def _list_unix_serial_ports(additional=None):
    ports = []

    port_list = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyAMA*') + glob.glob('/dev/ttyMI*')

    if additional is not None:
        for location in additional:
            port_list += glob.glob(location)

    for port in port_list:
        if os.path.exists(port):
            ports.append(port)

    return ports


def list_serial_ports(additional=None):
    if sys.platform == "win32":
        return _list_windows_serial_ports()
    return _list_unix_serial_ports(additional)
