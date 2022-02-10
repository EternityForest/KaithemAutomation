from email.mime import audio
from mako.lookup import TemplateLookup
from matplotlib.pyplot import connect
from numpy import append
from scullery import iceflow
import os
import time
import threading
import logging
import weakref
import traceback
import shutil


logger = logging.Logger("plugins.nvr")

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    def onIncomingCall(self,number):
        # Uncomment to accept all incoming calls
        # self.accept()
        pass
"""


mediaFolders = weakref.WeakValueDictionary()


class Pipeline(iceflow.GstreamerPipeline):
    def onAppsinkData(self, *a, **k):
        self.dev.onAppsinkData(*a, **k)

    def getGstreamerSourceData(self, s):
        self.h264source = self.mp3src = False
        self.syncFile = False

        # The source is an HLS stream
        if s.endswith(".m3u8") and s.startswith("http"):
            self.addElement("souphttpsrc", location=s)
            self.addElement("hlsdemux")
            self.addElement("tsdemux")
            self.h264source = self.addElement("parsebin")

        elif s.startswith("file://"):
            if not os.path.exists(s[len("file://"):]):
                raise RuntimeError("Bad file: " + s)
            self.addElement(
                "multifilesrc", location=s[len("file://"):], loop=True)
            if s.endswith(".mkv"):
                self.addElement("matroskademux")
            else:
                self.addElement("qtdemux")
            self.h264source = self.addElement(
                "h264parse", connectWhenAvailable="video/x-h264", config_interval=1)
            self.syncFile = True

        # Make a video test src just for this purpose
        elif not s:
            self.addElement("videotestsrc", is_live=True)
            self.addElement(
                "capsfilter", caps="video/x-raw, format=I420, width=320, height=240")
            self.addElement("videoconvert")
            self.addElement("x264enc", tune="zerolatency",
                            byte_stream=True, rc_lookahead=0)
            self.h264source = self.addElement("h264parse")

        # Make a video test src just for this purpose
        elif s == "test":
            self.addElement("videotestsrc", is_live=True, pattern="checkers")
            self.addElement(
                "capsfilter", caps="video/x-raw, format=I420, width=320, height=240")
            self.addElement("videoconvert")
            self.addElement("x264enc", tune="zerolatency")
            self.h264source = self.addElement("h264parse")

        elif s == "webcam" or s == "webcam_audio":
            self.addElement("v4l2src")
            self.addElement("videoconvert")
            self.addElement("queue")
            try:
                self.addElement("omxh264enc", interval_intraframes=60)
            except Exception:
                self.addElement("x264enc", tune="zerolatency",
                                rc_lookahead=0, bitrate=2048, key_int_max=30)
            self.addElement(
                "capsfilter", caps="video/x-h264, profile=baseline")
            self.h264source = self.addElement("h264parse")

            self.addElement("alsasrc", connectToOutput=False)
            self.addElement("audioconvert")

            self.addElement("voaacenc")
            self.addElement("aacparse")

            self.mp3src = self.addElement("queue")

        # Tested
        # rtspsrc location=rtsp://192.168.1.6:8080/h264_pcm.sdp latency=100 ! queue ! rtph264depay ! h264parse

        return s


import iot_devices.device as devices


class NVRChannel(devices.Device):
    device_type = 'NVRChannel'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode

    def putTrashInBuffer(self):
        "Force a wake up of a thread sitting around waiting for the pipe"
        if os.path.exists("/dev/shm/nvr_pipe.ts"):

            import select
            try:
                f = os.open("/dev/shm/nvr_pipe.ts",
                            flags=os.O_NONBLOCK | os.O_APPEND)
                for i in range(188 * 42):
                    r, w, x = select.select([], [f], [], 0.2)
                    if w:
                        f.write(b'b')
                    else:
                        return
            except Exception:
                print(traceback.format_exc())

    def thread(self):
        self.threadExited = False

        b = b''
        while not os.path.exists("/dev/shm/nvr_pipe.ts"):
            time.sleep(1)

        f = open("/dev/shm/nvr_pipe.ts", 'rb')
        initialValue = self.runWidgetThread
        lp = time.monotonic()

        while self.runWidgetThread and (self.runWidgetThread == initialValue):
            try:
                b += f.read(188 * 24)
            except OSError:
                time.sleep(0.2)
            except TypeError:
                print(traceback.format_exc())

            if self.runWidgetThread:
                if len(b) > (188 * 512) or (lp<(time.monotonic() -0.25) and b):
                    lp = time.monotonic()
                    self.push_bytes("raw_feed", b)
                    b = b''
        self.threadExited = True

    def close(self):

        try:
            self.process.stop()
        except Exception:
            print(traceback.format_exc())

        self.runWidgetThread = False
        try:
            self.putTrashInBuffer()
        except Exception:
            print(traceback.format_exc())

        s = 10
        while s:
            s -= 1
            if self.threadExited:
                break
            time.sleep(0.1)

        devices.Device.close(self)
        try:
            shutil.rmtree("/dev/shm/knvr/" + self.name)
        except Exception:
            pass

        try:
            self.checker.unregister()
        except Exception:
            logger.exception("Unregistering")

    def __del__(self):
        self.close()

    def onRawTSData(self, data):
        pass

    def connect(self):
        if time.monotonic() - self.lastStart < 15:
            return

        self.lastStart = time.monotonic()
        try:
            os.makedirs("/dev/shm/knvr/" + self.name)
        except Exception:
            pass

        try:
            os.chmod("/dev/shm/knvr/" + self.name, 0o755)
        except Exception:
            pass

        # Close the old thread
        self.runWidgetThread = time.monotonic()
        self.putTrashInBuffer()
        s = 10
        while s:
            s -= 1
            if self.threadExited:
                break
            time.sleep(0.1)
        # Exec is needed so we can kill it
        # self.process = reap.Popen("exec gst-launch-1.0 -q "+getGstreamerSourceData(self.data.get('device.source','')) +"! ",shell=True)
        self.process = Pipeline()
        self.process.dev = self
        self.process.getGstreamerSourceData(self.data.get('device.source', ''))
        self.process.addElement("mpegtsmux", connectToOutput=(
            self.process.h264source, self.process.mp3src))

        import os
        # Path to be created
        path = "/dev/shm/nvr_pipe.ts"

        # Get rid of the old one, it could be clogged
        try:
            os.remove(path)
        except OSError:
            print("Failed to delete FIFO")
        try:
            os.mkfifo(path)
        except OSError:
            print("Failed to create FIFO")
        self.process.addElement("queue")
        self.process.addElement("filesink", location=path,
                                buffer_mode=2, sync=self.process.syncFile)

        self.datapusher = threading.Thread(
            target=self.thread, daemon=True, name="NVR")
        self.datapusher.start()

        self.process.start()

    def check(self):
        with self.streamLock:
            if self.process:
                try:
                    if self.process.isActive:
                        self.set_data_point('running', 1)
                        return
                except Exception:
                    pass
            self.set_data_point('running', 0)

            if self.datapoints['switch']:
                self.connect()

    def commandState(self, v, t, a):
        with self.streamLock:
            if not v:
                if self.process:
                    self.process.stop()
                self.runWidgetThread = False
                try:
                    self.putTrashInBuffer()
                except Exception:
                    print(traceback.format_exc())

                s = 10
                while s:
                    s -= 1
                    if self.threadExited:
                        break
                    time.sleep(0.1)
            else:
                self.check()

    def handle_web_request(self, relpath, params, method, **kwargs):
        if relpath[0] == "live":
            self.serve_file(os.path.join(
                "/dev/shm/knvr/", self.name, *(relpath[1:])))

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        try:
            self.runWidgetThread = True
            self.threadExited = True

            self.tsQueue = b''

            self.bytestream_data_point("raw_feed",
                                       subtype='mpegts',
                                       writable=False)

            self.numeric_data_point("switch",
                                    min=0,
                                    max=1,
                                    subtype='bool',
                                    interval=300,
                                    default=1,
                                    handler=self.commandState)

            self.numeric_data_point("running",
                                    min=0,
                                    max=1,
                                    subtype='bool')

            self.set_config_default("device.source", '')

            self.streamLock = threading.RLock()
            self.lastStart = 0

            mediaFolders[name] = self

            self.connect()
            self.check()
            from src import scheduling
            self.checker = scheduling.scheduler.every(self.check, 5)

        except Exception:
            self.handleException()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)
