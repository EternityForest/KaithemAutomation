import logging
from . import messagebus, pages
import time
import cherrypy


class WebUI():
    @cherrypy.expose
    def scan(self):
        pages.postOnly()
        pages.require("/admin/settings.edit")

        import bluetoothctl
        bt = bluetoothctl.Bluetoothctl()

        try:
            bt.start_scan()
            time.sleep(15)
            bt.stop_scan()

            devs = bt.get_discoverable_devices()
            paired = bt.get_paired_devices()
        finally:
            bt.close(force=True)

        return pages.get_template("settings/bluetooth/scan.html").render(devs=devs, paired=paired)

    @cherrypy.expose
    def pair(self, mac):
        pages.require("/admin/settings.edit")
        pages.postOnly()

        import bluetoothctl
        bt = bluetoothctl.Bluetoothctl()
        bt.set_agent("NoInputNoOutput")

        time.sleep(0.5)
        try:

            # I think this horriby fussy command needs exactlt this order to work.
            if not bt.pair(mac):
                raise RuntimeError("Pairing failed")

            if not bt.connect(mac):
                raise RuntimeError("Pairing suceeded but connection failed")

            if not bt.trust(mac):
                raise RuntimeError("Trusting failed")
        finally:
            bt.close(force=True)

        devs = []
        paired = bt.get_paired_devices()

        return pages.get_template("settings/bluetooth/scan.html").render(devs=devs, paired=paired)

    @cherrypy.expose
    def remove(self, mac):
        pages.require("/admin/settings.edit")
        pages.postOnly()
        import bluetoothctl
        bt = bluetoothctl.Bluetoothctl()
        time.sleep(0.5)
        try:
            devs = bt.get_discoverable_devices()
            paired = bt.get_paired_devices()
            if not bt.remove(mac):
                raise RuntimeError("Removing failed")
        finally:
            bt.close(force=True)

        return pages.get_template("settings/bluetooth/scan.html").render(devs=devs, paired=paired)
