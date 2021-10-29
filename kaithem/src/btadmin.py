import logging
from src import messagebus,pages
import time 
import cherrypy


class WebUI():
    @cherrypy.expose
    def scan(self):
        pages.require("/admin/settings.edit")
        
        import bluetoothctl
        bt = bluetoothctl.Bluetoothctl()

        try:
            bt.start_scan()
            time.sleep(5)
            bt.stop_scan()

            devs = bt.get_discoverable_devices()
            paired = bt.get_paired_devices()
        finally:
            bt.close(force=True)

        return pages.get_template("settings/bluetooth/scan.html").render(devs=devs,paired=paired)

    @cherrypy.expose
    def pair(self,mac):
        pages.require("/admin/settings.edit")
                
        import bluetoothctl
        bt = bluetoothctl.Bluetoothctl()
        try:
            devs =[]
            paired = bt.get_paired_devices()
            if not bt.pair(mac):
                raise RuntimeError("Pairing failed")
            if not bt.trust(mac):
                raise RuntimeError("Trusting failed")
            if not bt.connect(mac):
                raise RuntimeError("Pairing suceeded but connection failed")
        finally:
            bt.close(force=True)

        return pages.get_template("settings/bluetooth/scan.html").render(devs=devs)


    @cherrypy.expose
    def remove(self,mac):
        pages.require("/admin/settings.edit")
        import bluetoothctl
        bt = bluetoothctl.Bluetoothctl()
        try:
            devs =[]
            paired = bt.get_pared_devices()
            if not bt.remove(mac):
                raise RuntimeError("Removing failed")
        finally:
            bt.close(force=True)

        return pages.get_template("settings/bluetooth/scan.html").render(devs=devs)

        