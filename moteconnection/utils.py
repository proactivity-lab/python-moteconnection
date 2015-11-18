"""utils.py: Random utility functions for moteconnection."""


__author__ = "Raido Pahtma"
__license__ = "MIT"


def split_in_two(text, separator):
    parts = text.split(separator)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]
