__author__ = "Raido Pahtma"
__license__ = "MIT"

import re
import os
import sys
import glob
import serial


def _list_windows_serial_ports():
    ports = []

    for i in range(256):
        try:
            s = serial.Serial(i)
            ports.append(s.portstr)
            s.close()
        except serial.SerialException as e:
            msg = e.message.lower()
            if msg.find("could not open port") != -1 and msg.find("access is denied") != -1:
                match = re.match("could not open port '(\w+)'", msg)
                if match is not None:
                    ports.append(match.group(1).upper())

    return ports


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


if __name__ == "__main__":
    print list_serial_ports()
