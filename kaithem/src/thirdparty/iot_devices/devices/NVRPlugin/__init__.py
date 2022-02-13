from email.mime import audio
from pydoc import locate
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

    def onMotionBegin(self, *a, **k):
        self.mcb(True)

    def onMotionEnd(self, *a, **k):
        self.mcb(False)

    def onVideoAnalyze(self, *a, **k):
        self.acb(*a)

    def onBarcode(self, *a, **k):
        self.bcb(*a, **k)

    def onAppsinkData(self, *a, **k):
        self.dev.onAppsinkData(*a, **k)

    def getGstreamerSourceData(self, s, cfg):
        self.config = cfg
        self.h264source = self.mp3src = False
        self.syncFile = False

        # The source is an HLS stream
        if s.endswith(".m3u8") and s.startswith("http"):
            self.addElement("souphttpsrc", location=s)
            self.addElement("hlsdemux")
            self.addElement("tsdemux")
            self.addElement("parsebin")
            self.h264source = self.addElement("tee")

        elif s.startswith("file://"):
            if not os.path.exists(s[len("file://"):]):
                raise RuntimeError("Bad file: " + s)
            self.addElement(
                "multifilesrc", location=s[len("file://"):], loop=True)
            if s.endswith(".mkv"):
                dm = self.addElement("matroskademux")
            else:
                dm = self.addElement("qtdemux")
            self.addElement(
                "h264parse", connectWhenAvailable="video/x-h264")
            #self.addElement('identity', sync=True)
            self.syncFile = True
            self.addElement('queue',max_size_time=10000000)

            self.h264source = self.addElement("tee")
            self.addElement("decodebin3", connectToOutput=dm, connectWhenAvailable="audio")
            self.addElement("audioconvert",connectWhenAvailable="audio")

            self.addElement("audiorate")
            self.addElement("queue", max_size_time=10000000)
            self.addElement("voaacenc")
            self.addElement("aacparse")

            self.mp3src = self.addElement("queue", max_size_time=10000000)

        # Make a video test src just for this purpose
        elif not s:
            self.addElement("videotestsrc", is_live=True)
            self.addElement("videorate")
            self.addElement("capsfilter", caps="video/x-raw,framerate=" +
                            (self.config.get('device.fps', '4') or '4') + "/1")
            self.addElement(
                "capsfilter", caps="video/x-raw, format=I420, width=320, height=240")

            self.addElement("videoconvert")
            self.addElement("x264enc", tune="zerolatency",
                            byte_stream=True, rc_lookahead=0)
            self.addElement("h264parse")
            self.h264source = self.addElement("tee")

        # Make a video test src just for this purpose
        elif s == "test":
            self.addElement("videotestsrc", is_live=True)
            self.addElement("capsfilter", caps="video/x-raw,framerate=" +
                            (self.config.get('device.fps', '4') or '4') + "/1")

            self.addElement(
                "capsfilter", caps="video/x-raw, format=I420, width=320, height=240")
            self.addElement("videoconvert")
            self.addElement("x264enc", tune="zerolatency", key_int_max=int(
                (self.config.get('device.fps', '4') or '4')) * 2)
            self.addElement("h264parse")
            self.h264source = self.addElement("tee")

        elif s == "webcam" or s == "webcam_audio":
            self.addElement("v4l2src")
            self.addElement("videorate", drop_only=True)
            self.addElement("capsfilter", caps="video/x-raw,framerate=" +
                            (self.config.get('device.fps', '4') or '4') + "/1")
            self.addElement("videoconvert")
            self.addElement("queue", max_size_time=10000000)
            try:
                self.addElement("omxh264enc", interval_intraframes=int(
                    (self.config.get('device.fps', '4') or '4')) * 2)
            except Exception:
                self.addElement("x264enc", tune="zerolatency",
                                rc_lookahead=0, bitrate=2048, key_int_max=int((self.config.get('device.fps', '4') or '4')) * 2)
            self.addElement(
                "capsfilter", caps="video/x-h264, profile=main")
            self.addElement("h264parse",config_interval=1)
            self.h264source = self.addElement("tee")

            self.addElement("alsasrc", connectToOutput=False)
            self.addElement("queue")
            self.addElement("audioconvert")

            self.addElement("voaacenc")
            self.addElement("aacparse")

            self.mp3src = self.addElement("queue", max_size_time=10000000)

        elif s.startswith("rtsp://"):
            rtsp = self.addElement(
                "rtspsrc", location=s, latency=100, async_handling=True)
            self.addElement("rtph264depay", connectWhenAvailable="video")

            self.addElement("h264parse", config_interval=1)

            self.h264source = self.addElement("tee")

            # self.addElement("decodebin", connectToOutput=rtsp, connectWhenAvailable="audio",async_handling=True)
            # self.addElement("audioconvert")
            # self.addElement("audiorate")
            # self.addElement("voaacenc")
            # self.addElement("aacparse")

            # self.mp3src = self.addElement("queue", max_size_time=10000000)

        elif s == "screen":
            self.addElement("ximagesrc")
            self.addElement("capsfilter", caps="video/x-raw,framerate=" +
                            (self.config.get('device.fps', '4') or '4') + "/1")
            self.addElement("videoconvert")
            self.addElement("queue", max_size_time=10000000)
            try:
                self.addElement("omxh264enc", interval_intraframes=int(
                    (self.config.get('device.fps', '4') or '4')))
            except Exception:
                self.addElement("x264enc", tune="zerolatency",
                                rc_lookahead=0, bitrate=2048, key_int_max=int((self.config.get('device.fps', '4') or '4')) * 2)
            self.addElement(
                "capsfilter", caps="video/x-h264, profile=main")
            self.addElement("h264parse")
            self.h264source = self.addElement("tee")

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
        if os.path.exists(self.rawFeedPipe):

            import select
            try:
                f = os.open(self.rawFeedPipe,
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
        while not os.path.exists(self.rawFeedPipe):
            time.sleep(1)

        f = open(self.rawFeedPipe, 'rb')
        initialValue = self.runWidgetThread
        lp = time.monotonic()

        while self.runWidgetThread and (self.runWidgetThread == initialValue):
            try:
                b += f.read(188 * 32)
            except OSError:
                time.sleep(0.2)
            except TypeError:
                time.sleep(1)
                try:
                    f = open(self.rawFeedPipe, 'rb')
                except:
                    print(traceback.format_exc())

            except Exception:
                time.sleep(0.5)
                print(traceback.format_exc())

            if self.runWidgetThread:
                if len(b) > (188 * 256) or (lp < (time.monotonic() - 0.2) and b):
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
            shutil.rmtree("/dev/shm/knvr_buffer/" + self.name)
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

    def connect(self, config):
        self.config = config
        if time.monotonic() - self.lastStart < 15:
            return

        self.lastStart = time.monotonic()

        try:
            shutil.rmtree("/dev/shm/knvr_buffer/" + self.name)
        except Exception:
            pass

        os.makedirs("/dev/shm/knvr_buffer/" + self.name)

        try:
            # Make it so nobody else can read the files
            os.chmod("/dev/shm/knvr_buffer/" + self.name, 0o700)
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
        self.process.getGstreamerSourceData(
            self.config.get('device.source', ''), self.config)

        x = self.process.addElement(
            "queue", connectToOutput=self.process.h264source, max_size_time=10000000)

        self.process.addElement("mpegtsmux", connectToOutput=(
            x, self.process.mp3src))

        self.mpegtssrc = self.process.addElement("tee")

        # Path to be created
        path = self.rawFeedPipe

        # Get rid of the old one, it could be clogged
        try:
            os.remove(path)
        except OSError:
            print("Failed to delete FIFO")
        try:
            os.mkfifo(path)
        except OSError:
            print("Failed to create FIFO")

        os.chmod(path, 0o700)

        self.process.addElement("queue", max_size_time=10000000)
        self.process.addElement("filesink", location=path,
                                buffer_mode=2, sync=self.process.syncFile)

        # # Motion detection part of the graph

        # # This flag discards every unit that cannot be handled individually
        self.process.addElement(
            "identity", drop_buffer_flags=8192, connectToOutput=self.process.h264source)
        self.process.addElement("queue", max_size_time=20000000,
                                 leaky=2)
        self.process.addElement("capsfilter", caps="video/x-h264")

        try:
            self.process.addElement("omxh264dec")
        except:
            self.process.addElement("avdec_h264")

        # self.process.addElement("videorate",drop_only=True)
        # self.process.addElement("capsfilter", caps="video/x-raw,framerate=1/1")
        self.process.addElement("videoanalyse")

        if self.config.get('device.barcodes', '').lower() in ("yes","true","detect","enable","on"):
            self.process.addElement("zbar")
            self.print("Barcode detection enabled")

        self.process.addElement("videoconvert", chroma_resampler=0)

        self.process.addElement(
            "motioncells", sensitivity=0.78, gap=2, display=False)

        self.process.addElement("fakesink")

        self.process.mcb = self.motion
        self.process.bcb = self.barcode
        self.process.acb = self.analysis

        self.process.addElement("hlssink", connectToOutput= self.mpegtssrc, async_handling=True,
        location=os.path.join("/dev/shm/knvr_buffer/", self.name, r"segment%08d.ts"),
        playlist_root=os.path.join("/dev/shm/knvr_buffer/", self.name),
        playlist_location=os.path.join("/dev/shm/knvr_buffer/", self.name, "playlist.m3u8"))

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
                self.connect(self.config)

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

    def motion(self, v):
        self.set_data_point("motion_detected", v)

    def analysis(self, v):
        self.set_data_point("luma_average", v['luma-average'])
        self.set_data_point("luma_variance", v['luma-variance'])

    def barcode(self, t, d, q):
        self.set_data_point("barcode", {
                            'barcode_type': t, "barcode_data": d, "wallclock": time.time(), "quality": q})

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        try:
            self.runWidgetThread = True
            self.threadExited = True

            self.tsQueue = b''

            self.rawFeedPipe = "/dev/shm/nvr_pipe." + \
                name.replace("/", '') + ".raw_feed.tspipe"

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
                                    subtype='bool',
                                    writable=False)

            self.numeric_data_point("motion_detected",
                                    min=0,
                                    max=1,
                                    subtype='bool',
                                    writable=False)

            self.numeric_data_point("luma_average",
                                    min=0,
                                    max=1,
                                    writable=False)

            self.numeric_data_point("luma_variance",
                                    min=0,
                                    max=1,
                                    writable=False)

            self.set_alarm("Camera dark", "luma_average",
                           "value < 0.095", trip_delay=3, auto_ack=True)
            self.set_alarm("Camera low varience", "luma_variance",
                           "value < 0.008", trip_delay=3, auto_ack=True)

            self.object_data_point("barcode",
                                   writable=False)

            self.set_config_default("device.source", '')
            self.set_config_default("device.fps", '4')
            self.set_config_default("device.barcodes", 'no')

            self.streamLock = threading.RLock()
            self.lastStart = 0

            mediaFolders[name] = self

            self.connect(self.config)
            self.check()
            from src import scheduling
            self.checker = scheduling.scheduler.every(self.check, 5)

        except Exception:
            self.handleException()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)
