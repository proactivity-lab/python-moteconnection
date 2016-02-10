from setuptools import setup

setup(name='moteconnection',
      version='0.1.1',
      description='Python library for using TinyOS inspired serial and tcp connections.',
      url='http://github.com/proactivity-lab/python-moteconnection',
      author='Raido Pahtma',
      author_email='raido.pahtma@ttu.ee',
      license='MIT',
      install_requires=[
        "pyserial",
      ],
      packages=['moteconnection'],
      zip_safe=False)
