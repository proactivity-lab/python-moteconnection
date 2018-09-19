"""
moteconnection: library for using TinyOS inspired serial and tcp connections.

moteconnection supports connection strings like serial@PORT:BAUDRATE and
sf@HOST:SFPORT. Default BAUDRATE is 115200 and default SFPORT is 9002.
"""

from setuptools import setup

import moteconnection

doclines = __doc__.split("\n")

setup(name='moteconnection',
      version=moteconnection.version,
      description='Python library for using TinyOS inspired serial and tcp connections.',
      long_description='\n'.join(doclines[2:]),
      url='http://github.com/proactivity-lab/python-moteconnection',
      author='Raido Pahtma',
      author_email='raido.pahtma@ttu.ee',
      license='MIT',
      platforms=["any"],
      install_requires=["pyserial", "six", "enum34"],
      tests_required=['nose', 'mock'],
      packages=['moteconnection'],
      zip_safe=False)
