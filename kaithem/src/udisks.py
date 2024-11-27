import os
import subprocess

import psutil


def list_drives():
    d = {}

    for i in os.listdir("/dev/disk/by-id"):
        fn = "/dev/disk/by-id/" + i
        if (not i.startswith(("ata", "scsi", "wwn"))) and "-part" in i:
            x = psutil.disk_usage(fn)
            d[i] = {"used": x.used, "total": x.total, "device": fn}
    return d


def is_mounted(path):
    if os.path.islink(path):
        path = os.path.realpath(path)
    m = subprocess.check_output(["mount"]).decode("utf-8")

    return path in m


def mount_drive(drive):
    drive = os.path.realpath(drive)
    subprocess.check_output(["udisksctl mount -b " + drive])


def unmount_drive(drive):
    drive = os.path.realpath(drive)
    subprocess.check_output(["udisksctl unmount -b " + drive])
