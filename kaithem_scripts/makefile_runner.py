import os
import subprocess
import sys


def main():
    return subprocess.call(["make"] + sys.argv[1:], cwd=os.path.dirname(os.path.realpath(__file__)))
