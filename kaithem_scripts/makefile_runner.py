import os
import subprocess
import sys

if sys.argv[1].startswith("root-"):
    confirm = input("Are you sure you want to run this command as root? (y/n): ")
    if confirm.lower() != "y":
        print("Command cancelled.")
        sys.exit(0)


def main():
    return subprocess.call(["make"] + sys.argv[1:], cwd=os.path.dirname(os.path.realpath(__file__)))
