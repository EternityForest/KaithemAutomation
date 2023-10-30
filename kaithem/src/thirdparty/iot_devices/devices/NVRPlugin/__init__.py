from multiprocessing import RLock
from mako.lookup import TemplateLookup
from kaithem.src.scullery import iceflow, workers
import os
import time
import threading
import logging
import weakref
import traceback
import shutil
import re
import io
import random

logger = logging.Logger("plugins.nvr")

templateGetter = TemplateLookup(os.path.dirname(__file__))
from datetime import datetime
from datetime import timezone


path = os.path.dirname( os.path.abspath(__file__))


def getRTSPFromOnvif(c):
    c.create_devicemgmt_service()
    c.create_media_service()

    selection = None
    cw = 0
    for p in c.media.GetProfiles():

        # We want to find a profile that has H264/AAC
        if not 'VideoEncoderConfiguration' in p:
            continue
        if not 'Encoding' in p['VideoEncoderConfiguration']:
            continue
        
        if not p['VideoEncoderConfiguration']['Encoding']=='H264':
            continue

        if 'AudioEncoderConfiguration' in p:
            if not p['AudioEncoderConfiguration']['Encoding']=="AAC":
                continue


        # We want the best available quality so we are going to look for the widest.
        if 'Resolution' in p['VideoEncoderConfiguration']:
            if p['VideoEncoderConfiguration']['Resolution']['Width']< cw:
                continue

            cw = p['VideoEncoderConfiguration']['Resolution']['Width']
        selection = p

    # Only do the net request after we know what we want to connect with.
    resp = c.media.GetStreamUri({
        'StreamSetup': {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}},
        'ProfileToken': selection.token,
    })

    return resp.Uri



objectDetector = [None, None]

# Only one of these should happpen at a time. Because we need to limit how much CPU it can burn.
object_detection_lock = threading.RLock()

import numpy


def get_output_layers(net):
    layer_names = net.getLayerNames()
    output_layers = [layer_names[i[0] - 1]
                     for i in net.getUnconnectedOutLayers()]
    return output_layers


def toImgOpenCV(imgPIL):  # Conver imgPIL to imgOpenCV
    i = numpy.array(imgPIL)  # After mapping from PIL to numpy : [R,G,B,A]
    # numpy Image Channel system: [B,G,R,A]
    red = i[:, :, 0].copy()
    i[:, :, 0] = i[:, :, 2].copy()
    i[:, :, 2] = red
    return i


def letterbox_image(image, size):
    '''resize image with unchanged aspect ratio using padding'''
    import cv2
    import numpy as np
    iw, ih = image.shape[0:2][::-1]
    w, h = size
    scale = min(w / iw, h / ih)
    nw = int(iw * scale)
    nh = int(ih * scale)
    image = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_CUBIC)
    new_image = np.zeros((size[1], size[0], 3), np.uint8)
    new_image.fill(0)
    dx = (w - nw) // 2
    dy = (h - nh) // 2
    new_image[dy:dy + nh, dx:dx + nw, :] = image
    return new_image


# We get the model from here and export it as tflite without any extra quantization:
# https://github.com/google/automl/blob/master/efficientdet/README.md

# Label map: https://github.com/joonb14/TFLiteDetection

def recognize_tflite(i, r):
    import tflite_runtime.interpreter as tflite
    import cv2
    import PIL.Image
    import PIL.ImageOps
    import PIL.ImageFilter
    invoke_time = time.time()

    
    i = PIL.Image.open(io.BytesIO(i))
    pilimg = i
    i = i.filter(PIL.ImageFilter.GaussianBlur(1))
    i = PIL.ImageOps.autocontrast(i, cutoff=0.05)

    if not objectDetector[0]:
        objectDetector[0] = tflite.Interpreter(num_threads=4, model_path=os.path.join(
            path, "efficientdet/efficientdet-lite0-f32.tflite"))
        objectDetector[0].allocate_tensors()

    # Sigh.  So many breaking changes to watch for!
    # https://stackoverflow.com/questions/74379966/typeerror-text-reading-control-character-must-be-a-single-unicode-character-or
    if objectDetector[1] is None:
        try:
            objectDetector[1] = numpy.loadtxt(os.path.join(
                path, "labelmap.txt"), dtype=str, delimiter="/n")
        except Exception:
            objectDetector[1] = numpy.genfromtxt(os.path.join(
                path, "labelmap.txt"), dtype=str, delimiter="/n")

    interpreter = objectDetector[0]
    labels = objectDetector[1]

    original_image = toImgOpenCV(i)
    # Get input and output tensors.
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    tensor_w = input_details[0]['shape'][1]
    tensor_h = input_details[0]['shape'][2]

    image = letterbox_image(original_image, (tensor_w, tensor_h))
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    input_image = numpy.expand_dims(image, 0)

    interpreter.set_tensor(input_details[0]['index'], input_image)
    original_image_h = original_image.shape[0]
    original_image_w = original_image.shape[1]

    interpreter.invoke()
    t = time.time() - invoke_time
    r.lastInferenceTime = t

    # The function `get_tensor()` returns a copy of the tensor data.
    # Use `tensor()` in order to get a pointer to the tensor.

    o = interpreter.get_tensor(output_details[0]['index'])[0]
    probability = numpy.array([i[5]for i in o])

    # Our dynamically chosen confidence threshhold meant to pick up things in dim light
    p = float(max(min(0.10, float(probability.max()) * 0.8), 0.01))

    retval = []

    # All this is reverse engineered from looging at the output.
    for i in o:
        if float(i[5]) < p:
            continue
        if int(i[6]) < 1:
            continue

        x, y, x2, y2 = (float((i[2] / tensor_w) * original_image_w), 
                        float((i[1] / tensor_h) * original_image_h), 
                        float((i[4] / tensor_w) * original_image_w),
                        float((i[3] / tensor_h) * original_image_h))

        x = min(x, x2)
        w = max(x, x2) - x
        y = min(y, y2)
        h = max(y, y2) - y

        confidence = float(i[5])
        label = labels[int(i[6]) - 1]

        v = {
            'x': float(x), 'y': float(y), "w": float(w), 'h': float(h),
            'class': label,
            'confidence': confidence,
        }

        if x2 > (original_image_w - 20) and confidence < 0.2:
            continue
        if y2 > (original_image_h - 10) and confidence < 0.15:
            continue
        # For some reason I am consistently getting false positive people detections
        #  with y values in the -6 to 15 range
        # Could just be my input data.  But, things are usually not that high up unless
        #  they are big and big means a clear view which means
        # you probably would have a higher confidence
        if (x > 1 and y > 24) or confidence > 0.33:

            # If something takes up a very large amount of the frame, we probably have a clear view of it.  
            # If we are still not confident the ANN
            # Is probably making stuff up.  Very large things are going to be uncommon since most cameras like 
            # this aren't doing extreme close ups
            # and the ones that are probably have good lighting
            if ((w < original_image_w / 4) or (confidence > 0.18)) and ((h < (original_image_h / 3)) or (confidence > 0.15)):
                if (w < (original_image_w / 2.5) or (confidence > 0.48)) and (h < (original_image_h / 1.8) or (confidence > 0.48)):

                    # If the width of this object is such that more than 2/3d is off of the frame, we had better be very confident
                    # because that seems to be a common pattern of false positives.
                    if (((original_image_w - x) > w / 3) or confidence > 0.4):
                        retval.append(v)
                    else:
                        pass  # print(v, "reject large offscreen")
                else:
                    pass  # print(v, "reject to large for confidence 2")
            else:
                pass  # print(v, "reject too large for confidence")
        else:
            pass  # print(v,"reject low xy")

    return {'objects': retval, 'x-inferencetime': t, 'x-imagesize': [original_image_w,original_image_h]}


automated_record_uuid = '76241b9c-5b08-4828-9358-37c6a25dd823'

from zeroconf import ServiceBrowser, ServiceStateChange


# very much not thread safe, doesn't matter, it's only for one UI page
httpservices = []
httplock = threading.Lock()

import socket


onvifCams = {}


def fixAddr(a):
    return a.split(".")[0]+".local"

def on_service_state_change(zeroconf, service_type, name, state_change):
    with httplock:
        info = zeroconf.get_service_info(service_type, name)
        if not info:
            return
        if state_change is ServiceStateChange.Added:
            httpservices.append((tuple(sorted(
                [socket.inet_ntoa(i) for i in info.addresses])), service_type, name, info.port))
            if len(httpservices) > 2048:
                httpservices.pop(0)

            try:
                if name.startswith("AMC"):
                    #No username/pw yet, we cannot actually fill this in.
                    onvifCams[fixAddr(name)]= None
            except Exception:
                pass
        elif state_change is ServiceStateChange.Removed:
            try:
                httpservices.remove((tuple(sorted(
                    [socket.inet_ntoa(i) for i in info.addresses])), service_type, name, info.port))
                
                if name.startswith("AMC"):
                    del onvifCams[fixAddr(name)]
            except Exception:
                logging.exception("???")


# Not common enough to waste CPU all the time on
#browser = ServiceBrowser(util.zeroconf, "_https._tcp.local.", handlers=[ on_service_state_change])
try:
    from kaithem.src.util import zeroconf as zcinstance
except Exception:
    import zeroconf
    zcinstance = zeroconf.Zeroconf()

browser2 = ServiceBrowser(zcinstance, "_http._tcp.local.", handlers=[
                          on_service_state_change])


mediaFolders = weakref.WeakValueDictionary()


class Pipeline(iceflow.GstreamerPipeline):

    def onMotionBegin(self, *a, **k):
        self.mcb(True)

    def onMotionEnd(self, *a, **k):
        self.mcb(False)

    def onPresenceValue(self, v):
        self.presenceval(v)

    def onVideoAnalyze(self, *a, **k):
        self.acb(*a)

    def onBarcode(self, *a, **k):
        self.bcb(*a, **k)

    def onAppsinkData(self, *a, **k):
        self.dev.onAppsinkData(*a, **k)

    def getGstreamerSourceData(self, s, cfg, un, pw, doJackAudio=False):
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
            # self.addElement('identity', sync=True)
            self.syncFile = True
            self.addElement('queue', max_size_time=10000000)

            self.h264source = self.addElement("tee")
            self.addElement("decodebin3", connectToOutput=dm,
                            connectWhenAvailable="audio")
            self.addElement("audioconvert", connectWhenAvailable="audio")

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
            self.addElement("x264enc", tune="zerolatency",
                                rc_lookahead=0, bitrate=int(self.dev.config['device.bitrate']), key_int_max=int((self.config.get('device.fps', '4') or '4')) * 2)
            self.addElement(
                "capsfilter", caps="video/x-h264, profile=main")
            self.addElement("h264parse", config_interval=1)
            self.h264source = self.addElement("tee")

            self.addElement("alsasrc", connectToOutput=False)
            self.addElement("queue")
            self.addElement("audioconvert")

            self.addElement("voaacenc")
            self.addElement("aacparse")

            self.mp3src = self.addElement("queue", max_size_time=10000000)

        elif s.startswith("rtsp://") or self.dev.onvif:

            if self.dev.onvif:
                s = getRTSPFromOnvif(self.dev.onvif)
                self.dev.metadata['device.discovered_rtsp_url'] = s

            rtsp = self.addElement(
                "rtspsrc", location=s, latency=100, async_handling=True, user_id=un or None, user_pw=pw or None)
            self.addElement("rtph264depay", connectWhenAvailable="video")

            self.addElement("h264parse", config_interval=1)

            self.h264source = self.addElement("tee")

            self.addElement("decodebin", connectToOutput=rtsp,
                            connectWhenAvailable="audio", async_handling=True)

            if doJackAudio:
                rawaudiotee = self.addElement('tee',connectWhenAvailable="audio")

            self.addElement("audioconvert")
            self.addElement("audiorate")
            self.addElement("voaacenc")
            self.addElement("aacparse")

            self.mp3src = self.addElement("queue", max_size_time=10000000)

            if doJackAudio:
                self.addElement("queue",max_size_time=100_000_000,leaky=2, connectWhenAvailable="audio", connectToOutput=rawaudiotee)
                self.sink = self.addElement("jackaudiosink", buffer_time=10, latency_time=10, sync=False, provide_clock=False,
                                            slave_method=0, port_pattern="ghjkcsrc", client_name=self.dev.name + "_out", connect=0, blocksize=512)


        elif s.startswith("srt://"):
            rtsp = self.addElement(
                "srtsrc", mode=1, uri=s, passphrase=pw or '')

            demux = self.addElement('tsdemux')
            self.addElement("h264parse", config_interval=2,
                            connectWhenAvailable="video")
            self.addElement("queue",max_size_time=100_000_000,leaky=2)

            self.h264source = self.addElement("tee")

            self.addElement("aacparse", connectToOutput=demux,
                            connectWhenAvailable="audio")
            self.mp3src = self.addElement("queue", max_size_time=100_000_000,leaky=2)

        elif s == "screen":
            self.addElement("ximagesrc")
            self.addElement("capsfilter", caps="video/x-raw,framerate=" +
                            (self.config.get('device.fps', '4') or '4') + "/1")
            self.addElement("videoconvert")
            self.addElement("queue", max_size_time=10000000)
            self.addElement("x264enc", tune="zerolatency",
                                rc_lookahead=0, bitrate=int(self.dev.config['device.bitrate']), 
                                key_int_max=int((self.config.get('device.fps', '4') or '4')) * 2)
            self.addElement(
                "capsfilter", caps="video/x-h264, profile=main")
            self.addElement("h264parse")
            self.h264source = self.addElement("tee")

        # Tested
        # rtspsrc location=rtsp://192.168.1.6:8080/h264_pcm.sdp latency=100 ! queue ! rtph264depay ! h264parse

        return s


import iot_devices.device as devices


class NVRChannelRegion(devices.Device):
    """
        Subdevice used to configure one sub-region of motion detection
    """
    device_type = "NVRChannelRegion"
    def __init__(self,name, data, **kw):
        devices.Device.__init__(self, name, data, **kw)
        self.numeric_data_point("motion_detected",
                        min=0,
                        max=1,
                        subtype='bool',
                        writable=False)

        self.numeric_data_point("raw_motion_value",
                                min=0,
                                max=10,
                                writable=False)

        self.object_data_point("contained_objects",
                                    writable=False)

        # self.object_data_point("overlapping_objects",
        #                             writable=False)


        self.set_config_default('device.motion_threshold', '0.08')


    def processImage(self, img):
        pass


    def onMotionValue(self, v):
        self.set_data_point("raw_motion_value", v)
        self.motion(v > float(self.config.get(
            'device.motion_threshold', 0.08)))

    def isRectangleContained(self, d, overallsize):
        x = d['x']/overallsize[0]
        y = d['y']/overallsize[1]
        w = d['w']/overallsize[0]
        h = d['h']/overallsize[1]


        # Opper right corner in rectangle
        if self.x <= x <= self.x + self.width:
            if self.y <= y <= self.y + self.height:
                # Lower right corner
                if self.x <= x+w <= self.x + self.width:
                    if self.y <= y+h <= self.y + self.height:
                        return True

    def isRectangleOverlapping(self, d):
        R1 = [d['x'], d['y'], d['x'] + d['width'], d['y']+d['width']]
        R2 = [self.x, self.y, self.x+ self.width, self.y+self.width]

        if (R1[0]>=R2[2]) or (R1[2]<=R2[0]) or (R1[3]<=R2[1]) or (R1[1]>=R2[3]):
            return False
        return True


    def onObjects(self, o):
        # Filter by the objects that are contained within the rectangle
        op = {'objects': []}
        #oop = {'objects': []}

        for i in o['objects']:
            if 'x' in i:
                if self.isRectangleContained(i, o['x-imagesize']):
                    op['objects'].append(i)
        self.set_data_point('contained_objects', op)


        # for i in o['objects']:
        #     if 'x' in i:
        #         if self.isRectangleOverlapping(i):
        #             oop['objects'].append(i)


        # self.set_data_point('overlapping_objects', oop)

        

    def motion(self, v):
        self.set_data_point("motion_detected", v)



class NVRChannel(devices.Device):
    device_type = 'NVRChannel'
    readme = os.path.join(os.path.dirname(__file__), "README.md")

    def putTrashInBuffer(self):
        "Force a wake up of a thread sitting around waiting for the pipe"
        if os.path.exists(self.rawFeedPipe):

            import select
            try:
                f = os.open(self.rawFeedPipe,
                            flags=os.O_NONBLOCK | os.O_APPEND)
                s = 0
                for i in range(188 * 42):
                    r, w, x = select.select([], [f], [], 0.2)
                    if w:
                        f.write(b'b')
                    else:
                        s += 1
                        if s > 15:
                            return

            except Exception:
                print(traceback.format_exc())

    def thread(self):
        #Has to be at top othherwise other threads wait and get same val.... and we have multiple...
        initialValue = self.runWidgetThread
        self.threadStarted = True
        self.threadExited = False

        b = b''
        while not os.path.exists(self.rawFeedPipe):
            time.sleep(1)

        f = open(self.rawFeedPipe, 'rb')
        lp = time.monotonic()

        while self.runWidgetThread and (self.runWidgetThread == initialValue):
            try:
                x =  f.read(188 * 32)
                if x is None:
                    return
                b+=x
            except OSError:
                time.sleep(0.2)
            except TypeError:
                time.sleep(1)
                try:
                    f = open(self.rawFeedPipe, 'rb')
                except Exception:
                    print(traceback.format_exc())

            except Exception:
                time.sleep(0.5)
                print(traceback.format_exc())

            if self.runWidgetThread:
                if len(b) > (188 * 256) or (lp < (time.monotonic() - 0.2) and b):
                    lp = time.monotonic()
                    self.push_bytes("raw_feed", b)
                    self.lastPushedWSData = time.monotonic()
                    b = b''
        self.threadExited = True


    def checkThread(self):
        #Has to be at top othherwise other threads wait and get same val.... and we have multiple...
        initialValue = self.runCheckThread

        while self.runCheckThread and (self.runCheckThread == initialValue):
            self.check()
            time.sleep(3)


    def close(self):
        self.closed = True
        try:
            self.process.stop()
        except Exception:
            print(traceback.format_exc())
        self.runCheckThread = False
        self.runWidgetThread = False
        try:
            self.putTrashInBuffer()
        except Exception:
            print(traceback.format_exc())

        try:
            os.remove(self.rawFeedPipe)
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

    def __del__(self):
        self.close()

    def onRawTSData(self, data):
        pass

    def getSnapshot(self):
        if hasattr(self, 'snapshotter'):
            with open("/dev/shm/knvr_buffer/" + self.name + ".bmp","w") as f:
                os.chmod("/dev/shm/knvr_buffer/" + self.name + ".bmp", 0o700)
            if self.datapoints['running']:
                try:

                    # Use a temp file to make it an atomic operation
                    fn = "/dev/shm/knvr_buffer/" + self.name + ".bmp"
                    tmpfn ="/dev/shm/knvr_buffer/" + self.name + str(time.time()) + ".bmp"

                    x = self.snapshotter.pullToFile(
                       tmpfn)

                    shutil.move(tmpfn, fn)
                    
                except Exception:
                    self.set_data_point('running', 0)
                    if self.process:
                        try:
                            self.process.stop()
                        except Exception:
                            print(traceback.format_exc())
                    raise

                if x:
                    with open("/dev/shm/knvr_buffer/" + self.name + ".bmp", 'rb') as f:
                        x = f.read()
                    os.remove("/dev/shm/knvr_buffer/" + self.name + ".bmp")

                return x

    def connect(self, config):
        if self.closed:
            return
        # Close the old thread
        self.runWidgetThread = time.monotonic()
        
        self.config = config
        if time.monotonic() - self.lastStart < 15:
            return

        # When we reconnect we stop the recording and motion
        self.set_data_point("record", False, None, automated_record_uuid)
        self.set_data_point("raw_motion_value", 0)
        self.set_data_point("motion_detected", 0)
        self.activeSegmentDir = self.segmentDir = None

        self.lastStart = time.monotonic()

        if self.process:
            try:
                self.process.stop()
            except Exception:
                print(traceback.format_exc())

        # Used to check that things are actually still working.
        # Set them to prevent a loop.
        self.lastSegment = time.monotonic()
        self.lastPushedWSData = time.monotonic()

        # Can't stop as soon as they push stop, still need to capture
        # the currently being recorded segment
        self.stoprecordingafternextsegment = 0

        if os.path.exists("/dev/shm/knvr_buffer/" + self.name):
            # Race condition retry
            try:
                shutil.rmtree("/dev/shm/knvr_buffer/" + self.name)
            except Exception:
                shutil.rmtree("/dev/shm/knvr_buffer/" + self.name)

        os.makedirs("/dev/shm/knvr_buffer/" + self.name)

        try:
            # Make it so nobody else can read the files
            os.chmod("/dev/shm/knvr_buffer/" + self.name, 0o700)
        except Exception:
            pass

        # Close the old thread
        self.runWidgetThread = time.monotonic()
        self.putTrashInBuffer()
        s = 100
        while s:
            s -= 1
            if self.threadExited:
                break
            time.sleep(0.1)
        else:
            self.print("COULD NOT STOP OLD THREAD")

 
        self.process = Pipeline()
        self.process.dev = self

        j = False#self.config['device.jack_output'].lower() in ('yes', 'true', 'enable', 'enabled')
        self.process.getGstreamerSourceData(
            self.config.get('device.source', ''), self.config, self.config.get('device.username', ''), self.config.get('device.password', ''), doJackAudio=j)

        x = self.process.addElement(
            "queue", connectToOutput=self.process.h264source, max_size_time=10000000)

        self.process.addElement("mpegtsmux", connectToOutput=(
            x, self.process.mp3src))

        self.process.addElement('tsparse', set_timestamps=True)

        self.mpegtssrc = self.process.addElement("tee")

        # Path to be created
        path = self.rawFeedPipe

        # Get rid of the old one, it could be clogged
        try:
            os.remove(path)
        except OSError:
            pass

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

        self.process.addElement("avdec_h264")
        # self.process.addElement("videorate",drop_only=True)
        # self.process.addElement("capsfilter", caps="video/x-raw,framerate=1/1")

        rawtee = self.process.addElement("tee")
        self.process.addElement("queue", max_size_buffers=1, leaky=2)

        self.snapshotter = self.process.addPILCapture()

        self.process.addElement("videoanalyse", connectToOutput=rawtee)

        if self.config.get('device.barcodes', '').lower() in ("yes", "true", "detect", "enable", "on"):
            self.process.addElement("zbar")
            self.print("Barcode detection enabled")


        # Not a real GST element. The iceflow backend hardcodes this motion/presense detection
        self.process.addPresenceDetector((640, 480), regions=self.regions)

        self.process.mcb = self.motion
        self.process.bcb = self.barcode
        self.process.acb = self.analysis

        self.process.presenceval = self.presencevalue

        self.process.addElement("hlssink", connectToOutput=self.mpegtssrc, message_forward=True, async_handling=True, max_files=0,
                                location=os.path.join(
                                    "/dev/shm/knvr_buffer/", self.name, r"segment%08d.ts"),
                                playlist_root=os.path.join(
                                    "/dev/shm/knvr_buffer/", self.name),
                                playlist_location=os.path.join(
                                    "/dev/shm/knvr_buffer/", self.name, "playlist.m3u8"),
                                target_duration=5)

        # We may want to have an SRT source.
        if int(self.config['device.srt_server_port']) > 0:
            self.process.addElement(
                "queue", leaky=2, max_size_time=200000000, connectToOutput=self.mpegtssrc)
            self.process.addElement("srtsink", mode=2, localaddress="0.0.0.0", localport=int(
                self.config['device.srt_server_port']), sync=False)

        self.threadStarted=False

        self.datapusher = threading.Thread(
            target=self.thread, daemon=True, name="NVR "+self.name)
        self.datapusher.start()

        s = 25000
        while not self.threadStarted:
            time.sleep(0.001)
            s -= 1
        else:
            if not self.threadStarted:
                self.print("Thread not started within 25 seconds")


        self.process.start()
        # Used to check that things are actually still working.
        # Set them to prevent a loop.
        self.lastSegment = time.monotonic()
        self.lastPushedWSData = time.monotonic()

    def onRecordingChange(self, v, t, a):
        with self.recordlock:

            d = os.path.join(self.storageDir, self.name, "recordings")
            if os.path.exists(d):
                for i in os.listdir(d):
                    i2 = os.path.join(d, i)
                    try:
                        dt = datetime.fromisoformat(i)
                    except Exception:
                        continue

                    now = datetime.utcnow().replace(tzinfo=timezone.utc)

                    if dt < now:
                        dt = now - dt
                        # Sanity check
                        if dt.days > self.retainDays and dt.days < 10000:
                            shutil.rmtree(i2)

            if a == automated_record_uuid:
                self.canAutoStopRecord = True
            else:
                self.canAutoStopRecord = False

            if v:
                self.stoprecordingafternextsegment = 0
                if not self.segmentDir:
                    self.setsegmentDir()
            else:
                self.stoprecordingafternextsegment = 1

    def setsegmentDir(self, manual=False):
        with self.recordlock:
            # Manually triggered recordings should go in a different folder

            my_date = datetime.utcnow()
            date = my_date.replace(
                hour=0, minute=0, second=0, microsecond=0).isoformat() + "+00:00"
            t = my_date.isoformat() + "+00:00"

            d = os.path.join(self.storageDir, self.name, "recordings", date, t)
            os.makedirs(d)
            self.segmentDir = d

            with open(os.path.join(self.segmentDir, "playlist.m3u8"), "w") as f:
                f.write("#EXTM3U\r\n")
                f.write("#EXT-X-START:	TIME-OFFSET=0\r\n")
                f.write("#EXT-X-PLAYLIST-TYPE: VOD\r\n")
                f.write("#EXT-X-VERSION:3\r\n")
                f.write("#EXT-X-ALLOW-CACHE:NO\r\n")
                f.write("#EXT-X-TARGETDURATION:5\r\n")

                s = []
                x = self.datapoints['detected_objects']
                if x and 'objects' in x:
                    for i in x['objects']:
                        if 'class' in i:
                            if not i['class'] in s:
                                s.append(i['class'])

                f.write("#EXTALB:" + ','.join(s) + "\r\n")

        # Capture a tiny preview snapshot
        import PIL
        x = PIL.Image.open(io.BytesIO(self.request_data_point("bmp_snapshot")))
        x.thumbnail((320, 240))
        x = PIL.ImageOps.autocontrast(x, cutoff=0.1)
        with open(os.path.join(self.segmentDir, "thumbnail.jpg"), 'wb') as f:
            x.save(f, 'jpeg')

    def onMultiFileSink(self, fn, *a, **k):
        with self.recordlock:
            self.moveSegments()
            d = os.path.join("/dev/shm/knvr_buffer/", self.name)
            ls = os.listdir(d)
            ls = list(sorted([i for i in ls if i.endswith(".ts")]))

            n = max(
                1, int((float(self.config.get('device.loop_record_length', 5)) + 2.5) / 5))

            s = 100
            while len(ls) > n:
                if s < 1:
                    break
                s -= 1
                os.remove(os.path.join(d, ls[0]))
                self.lastSegment = time.monotonic()
                self.set_data_point('running', 1)

                ls = os.listdir(d)
                ls = list(sorted([i for i in ls if i.endswith(".ts")]))
                n = max(
                    1, int((float(self.config.get('device.loop_record_length', 5)) + 2.5) / 5))

    def moveSegments(self):
        with self.recordlock:
            d = os.path.join("/dev/shm/knvr_buffer/", self.name)
            ls = os.listdir(d)
            ls = list(sorted([i for i in ls if i.endswith(".ts")]))

            if self.activeSegmentDir or self.segmentDir:
                # Ignore latest, that could still be recording
                for i in ls[:-1]:
                    self.lastSegment = time.monotonic()
                    self.set_data_point('running', 1)

                    # Someone could delete a segment dir while it is being written to.
                    # Prevent that from locking everything up.
                    if os.path.exists(self.activeSegmentDir or self.segmentDir):
                        # Find the duration of the segment from the hlssink playlist file
                        with open(os.path.join(d, "playlist.m3u8")) as f:
                            x = f.read()
                        if not i in x:
                            return

                        x = x.split(i)[0]
                        x = float(re.findall(r"EXTINF:\s*([\d\.]*)", x)[-1])

                        # Assume the start time is mod time minus length
                        my_date = datetime.utcfromtimestamp(
                            os.stat(os.path.join(d, i)).st_mtime - x)
                        t = my_date.isoformat() + "+00:00"

                        shutil.move(os.path.join(d, i),
                                    self.activeSegmentDir or self.segmentDir)
                        with open(os.path.join(self.activeSegmentDir or self.segmentDir, "playlist.m3u8"), "a+") as f:
                            f.write("\r\n")
                            f.write("#EXTINF:" + str(x) + ",\r\n")
                            f.write("#EXT-X-PROGRAM-DATE-TIME:" + t + "\r\n")
                            f.write(i + "\r\n")

                        self.directorySegments += 1

                    if self.stoprecordingafternextsegment:
                        x = self.segmentDir
                        self.segmentDir = None
                        self.activeSegmentDir = None

                        with open(os.path.join(x, "playlist.m3u8"), "a+") as f:
                            f.write("\r\n#EXT-X-ENDLIST\r\n")

                        break
                    else:
                        # Don't make single directories with more than an hour of video.
                        if self.directorySegments > (3600 / 5):
                            self.setsegmentDir()

                # Now we can transition to the new one!
                self.activeSegmentDir = self.segmentDir
                self.directorySegments = 0

    def check(self):
        "Pretty mush all periodic tasks go here"

        # Make sure we are actually getting video frames. Otherwise we reconnect.
        if not self.lastSegment > (time.monotonic() - 15):
            self.set_data_point('running', False)
            if self.datapoints.get('switch', 1):
                self.connect(self.config)
                return

        if not self.lastPushedWSData > (time.monotonic() - 15):
            self.set_data_point('running', False)
            if self.datapoints.get('switch', 1):
                self.connect(self.config)
                return

        d = os.path.join("/dev/shm/knvr_buffer/", self.name)
        ls = os.listdir(d)

        # If there is a ton of files run the poller anyway, if could have stalled because it ran out of memory
        # because something caused things to block long enough for it all to fill up.
        if (not ls == self.lastshm) or len(ls) > 16:
            self.onMultiFileSink('')
        self.lastshm = ls

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
        self.doMotionRecordControl(v)
        self.set_data_point("motion_detected", v)

    def doMotionRecordControl(self, v, forceMotionOnly=False):
        "forceMotionOnly records even if there is no object detection, for when the CPU can't keep up with how many motion requests there are"
        if self.config.get('device.motion_recording', 'no').lower() in ('true', 'yes', 'on', 'enable', 'enabled'):

            # If object recording is set up, and we have some object detection, only record if there is one of the objects
            # In frame
            lookfor = self.config.get('device.object_record', '').strip()
            if not self.config['device.object_detection'].lower() in ('yes', 'true', 'enable', 'enabled'):
                lookfor = None

            if v:

                # Do obj recognition. Accept recent object detection too in addition to current.
                #  We also rerun this after we successfully do the motion detection
                if lookfor and (self.lastObjectSet is not None) and (not forceMotionOnly):
                    for i in self.lastObjectSet['objects']:
                        if i['class'] in lookfor:
                            self.lastRecordTrigger = time.monotonic()
                            self.lastObjectDetectionHit = time.monotonic()
                            if not self.datapoints['record']:
                                self.print("Record started because of "+i['class'])

                            if self.datapoints['auto_record']>0.5:
                                self.set_data_point("record", True, None,
                                                    automated_record_uuid)

                else:
                    self.lastRecordTrigger = time.monotonic()
                    if self.datapoints['auto_record']>0.5:
                        self.set_data_point("record", True, None,
                                            automated_record_uuid)

            elif not v and self.canAutoStopRecord:
                if self.lastRecordTrigger < (time.monotonic() - 12):
                    # Even if there is still motion, if we have object detection data coming in but have not seen the object recently, stop if we are in objetc detecting
                    # mode

                    # But after a while we just have to stop, because maybe the object detector failed for some reason.

                    # Our window is 3 sucessive runs with no object hits.  Our window never goes past 30 seconds.
                    window = min(self.lastDidObjectRecognition -
                                 ((time.monotonic() - self.lastDidObjectRecognition) * 3), 30)
                    if (self.lastRecordTrigger < (time.monotonic() - 60)) or ((self.lastDidObjectRecognition > (time.monotonic() - 15)) and lookfor and (self.lastObjectDetectionHit < window)):
                        self.set_data_point("record", False, None,
                                            automated_record_uuid)

        self.lastDidMotionRecordControl = time.monotonic()

    def presencevalue(self, v):
        "Takes a raw presence value. Unfortunately it seems we need to do our own motion detection."

        if isinstance(v, dict):
            for i in v:
                # Empty string is entire image
                if i and i in self.subdevices:
                    self.subdevices[i].onMotionValue(v[i])

            # Get the overall motion number
            v = v['']

        self.set_data_point("raw_motion_value", v)

        self.motion(v > float(self.config.get(
            'device.motion_threshold', 0.08)))

        # We do object detection on one of two conditions. Either when there is motion or every N seconds no matter what.
        # Even when there is motion, however, we rate limit to once every 1 second.
        # On top of that we give up waiting for the one available slot to do the detection, after a random amount of time.
        # This ensures that under high CPU load we just gracefully fall back to not doing very much detection.

        # The value of N seconds should be very low if we detect that there is *really* nothing that could reasonably be seen as motion.
        detect_interval = 8 if v > 0.003 else 15

        objects = True
        if not self.config['device.object_detection'].lower() in ('yes', 'true', 'enable', 'enabled'):
            objects = False

        if objects and ((v > float(self.config.get('device.motion_threshold', 0.08))) or (self.lastDidObjectRecognition < time.monotonic() - detect_interval)):
            # Limit CPU usage. But don't limit so much we go more than 5s between detections
            if ((self.lastDidObjectRecognition - min(self.lastInferenceTime * 1.1, 5)) < time.monotonic() - min(self.lastInferenceTime * 1.1, 5)):
                self.obj_rec_wait_timestamp = time.monotonic()
                obj_rec_wait = self.obj_rec_wait_timestamp

                def f():

                    # Wait longer if not already recording so that things that don't need to detect as much give up faster.
                    # prioritize reliable start of record!

                    # Cannot wait too long thogh because we nee to quickly fail back to motion only.

                    # This calculates our length in terms of how much loop recorded footage we have
                    # We have to detect within this window or it will dissapear before we capture it.

                    # Note
                    n = max(
                        1, int((float(self.config.get('device.loop_record_length', 5)) + 2.5) / 5)) * 5

                    # If we have not seen any objects lately, better check more often because
                    # We might be about to stop the recording even if there is still motion, so it must be accurate.
                    if self.lastObjectDetectionHit > (time.monotonic() - 15):
                        t = 3 if self.datapoints['record'] else (n * 0.75)
                    else:
                        t = n * 0.75

                    if object_detection_lock.acquire(True, t + (random.random() * 0.1)):
                        try:
                            # We have to make sure an older detection does not wait on a newer detection.
                            # Only the latest should get through, or we would queue up a problem.
                            if self.obj_rec_wait_timestamp > obj_rec_wait:
                                return

                            x = self.request_data_point("bmp_snapshot")
                            if not x:
                                return
                            o = recognize_tflite(x, self)
                            self.lastDidObjectRecognition = time.monotonic()
                            self.lastObjectSet = o

                            lookfor = self.config.get(
                                'device.object_record', '').strip()
                            # For some high-certainty things we can trigger motion even when there is no motion detected by
                            # the standard algorithm.
                            relevantObjects = 0
                            if lookfor and (self.lastObjectSet is not None):
                                for i in self.lastObjectSet['objects']:
                                    if i['class'] in lookfor and i['confidence'] > 0.35:
                                        relevantObjects += 1

                            if self.oldRelevantObjectCount > -1 and not(self.oldRelevantObjectCount == relevantObjects):
                                self.motion(True)

                            self.oldRelevantObjectCount = relevantObjects

                            self.set_data_point("detected_objects", o)
                            for i in self.subdevices:
                                self.subdevices[i].onObjects(o)
                            # We are going to redo this.
                            # We do it in both places.
                            # Imagine you detect a person but no motion, but then later see motion, 
                            # but no person a few seconds later
                            # You probably want to catch that because a person was likely involved
                            self.doMotionRecordControl(
                                self.datapoints['motion_detected'])
                        finally:
                            object_detection_lock.release()

                    else:
                        self.doMotionRecordControl(
                            self.datapoints['motion_detected'], True)
                workers.do(f)

        else:
            # We arent't even using obj detct at all
            self.doMotionRecordControl(
                self.datapoints['motion_detected'], True)

    def analysis(self, v):
        self.set_data_point("luma_average", v['luma-average'])
        self.set_data_point("luma_variance", v['luma-variance'])

    def barcode(self, t, d, q):
        self.set_data_point("barcode", {
                            'barcode_type': t, "barcode_data": d, "wallclock": time.time(), "quality": q})

    def __init__(self, name, data, **kw):
        devices.Device.__init__(self, name, data, **kw)
        try:
            self.runWidgetThread = True
            self.runCheckThread = time.monotonic()

            self.threadExited = True
            self.closed = False
            self.set_config_default("device.storage_dir", '~/NVR')

            self.set_config_default("device.loop_record_length", '5')

            self.set_config_default("device.srt_server_port", '0')
            
            
            self.set_config_default("device.source", '')
            self.set_config_default("device.username", '')
            self.set_config_default("device.password", '')
            # If this is true, we send the camera audio to JACK if possible
            # self.set_config_default("device.jack_output", 'no')



            # Region data is in the format like regionName=0.3,0.3,0.4,0.2;
            # X, Y, W, H as fraction of image dimension
            self.set_config_default("device.regions", '')

            # Handle region data of the form foo=x,y,w,h; 
            regions = {}
            x = self.config['device.regions']
            if x:
                x = x.split(";")

                for i in x:
                    if not '=' in i:
                        continue

                    n, d = i.split("=")
                    n=n.strip()
                    regions[n] = [float(i.strip()) for i in d.split(',')]

                for i in regions:
                    x = self.create_subdevice(NVRChannelRegion, i, {})
                    i = regions[i]
                    x.x = i[0]
                    x.y = i[1]
                    x.width = i[2]
                    x.height = i[3]

                    x.region = i

            self.regions = regions


            # Support ONVIF URLs
            self.onvif=None
            if self.config['device.username'] and self.config['device.password']: 
                try:
                    from onvif import ONVIFCamera
                    if self.config['device.source'] and not self.config['device.source'].startswith('rtsp://') and not self.config['device.source']=='webcam':
                        if not self.config['device.source'].startswith('srt://'):
                            p = self.config['device.source'].split("://")[-1]
                            if ':' in p:
                                port = int(p.split(":")[1])
                                p=p.split(':')[0]
                            else:
                                port = 80

                            self.onvif = ONVIFCamera(p,port,self.config['device.username'], self.config['device.password'])
                except:
                    self.print(traceback.format_exc())
            
            self.process = None

            self.lastInferenceTime = 1

            self.lastDidObjectRecognition = 0

            # So we can tell if there is new object recogintion data since we last checked.
            self.lastDidMotionRecordControl = 0

            # Used to detect motion by looking at changes in the number of relevant objects.
            # Response time may be very low.
            self.oldRelevantObjectCount = -1

            # The most recent set of object detection results.
            self.lastObjectSet = None

            # We don't want to stop till a few seconds after an event that would cause motion
            self.lastRecordTrigger = 0

            # We also DO want to stop if we are in object record mode and have not seen the object in a long time

            self.lastObjectDetectionHit = 0

            # If this is true, record when there is motion
            self.set_config_default("device.motion_recording", 'no')

            self.storageDir = os.path.expanduser(
                self.config['device.storage_dir'] or '~/NVR')

            self.segmentDir = None

            # When changing segment dir, we can't do it instantly, we instead wait to be done with the current file.
            self.activeSegmentDir = None

            # How many segments in this dir. Must track so we can switch to a new directory if we need to.
            self.directorySegments = 0

            self.lastshm = None

            self.canAutoStopRecord = False

            if not os.path.exists(self.storageDir):
                os.makedirs(self.storageDir)
                # Secure it!
                os.chmod(self.storageDir, 0o700)

            self.tsQueue = b''

            self.recordlock = threading.RLock()

            self.rawFeedPipe = "/dev/shm/knvr_buffer/" + self.name + \
                "/" + str(time.monotonic()) + ".raw_feed.tspipe"

            self.bytestream_data_point("raw_feed",
                                       subtype='mpegts',
                                       writable=False)

            # Give this a little bit of caching
            self.bytestream_data_point("bmp_snapshot",
                                       subtype='bmp',
                                       writable=False,
                                       interval=0.3)

            self.set_data_point_getter('bmp_snapshot', self.getSnapshot)

            self.numeric_data_point("switch",
                                    min=0,
                                    max=1,
                                    subtype='bool',
                                    default=1,
                                    handler=self.commandState)
    
            self.numeric_data_point("auto_record",
                        min=0,
                        max=1,
                        subtype='bool',
                        default=1,
                        handler=self.onRecordingChange,
                        description="Set to 0 to disable automatic new recordings."
                        )

            self.numeric_data_point("record",
                                    min=0,
                                    max=1,
                                    subtype='bool',
                                    default=0,
                                    handler=self.onRecordingChange)

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

            self.numeric_data_point("raw_motion_value",
                                    min=0,
                                    max=10,
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
            self.set_alarm("Long_recording", "record",
                           "value > 0.5", trip_delay=800, auto_ack=True, priority='debug')

            self.set_alarm("Not Running", "running",
                           "value < 0.5", trip_delay=90, auto_ack=False, priority='warning')

           
            self.set_config_default("device.fps", '4')
            self.set_config_default("device.barcodes", 'no')
            self.set_config_default("device.object_detection", 'no')

            self.set_config_default(
                "device.object_record", 'person, dog, cat, horse, sheep, cow, handbag, frisbee, bird, backpack, suitcase, sports ball')

            self.set_config_default("device.motion_threshold", '0.08')
            self.set_config_default("device.bitrate", '386')

            self.set_config_default("device.retain_days", '90')

            self.config.pop("device.motion_sensitivity", 0)

            self.retainDays = int(self.config['device.retain_days'])

            if self.config['device.barcodes'].lower() in ('yes', 'true', 'enable', 'enabled'):
                self.object_data_point("barcode",
                                       writable=False)

            if self.config['device.object_detection'].lower() in ('yes', 'true', 'enable', 'enabled'):
                self.object_data_point("detected_objects",
                                       writable=False)

            self.config_properties['device.loop_record_length'] = {
                'description': 'How many seconds to buffer at all times to allow recording things before motion events actually happen.'
            }

            self.config_properties['device.barcodes'] = {
                'type': 'bool'
            }

            self.config_properties['device.object_detection'] = {
                'type': 'bool',
                'description': "Enable object detection.  See kaithem readme for where to put model files. "
            }

            self.config_properties['device.object_record'] = {
                'description': "Does nothing without object detection. Only record if there is both motion, and a recognized object on the list in the frame. If empty, always record. Can use any COCO item."
            }

            self.config_properties['device.source'] = {
                'secret': True
            }
            self.config_properties['device.password'] = {
                'secret': True
            }
            self.config_properties['device.motion_recording'] = {
                'type': 'bool'
            }

            self.config_properties['device.storage_dir'] = {
                'type': 'local_fs_dir'
            }

            self.config_properties['device.regions'] = {
                'type': 'region_list'
            }


            self.streamLock = threading.RLock()
            self.lastStart = 0

            mediaFolders[name] = self

            try:
                self.connect(self.config)
            except:
                self.handleException()
                self.set_data_point('running', 0)
                
            self.set_data_point('switch', 1)

            # Used to check that things are actually still working.
            self.lastSegment = time.monotonic()
            self.lastPushedWSData = time.monotonic()

            self.check()
            self.checkthreadobj = threading.Thread(
                target=self.checkThread, daemon=True, name="NVR checker"+self.name)
            self.checkthreadobj.start()

        except Exception:
            self.handleException()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


    @classmethod
    def discover_devices(cls, config= {},current_device=None, intent=None, **kw):
        # Discover based on the ONVIF cameras.  Let the user fill in username/password.
        l = {}
        for i in onvifCams:
            config2 = config.copy()

            config2.update(
                {
                    'type': cls.device_type,
                    'device.source': i
                }
            )

            config2['device.username'] = 'admin'
            config2['device.password'] = ''
            l[i] = config2

        
        for i in os.listdir("/dev/"):
            if i.startswith('video'):
                config2 = config.copy()

                config2.update(
                    {
                        'type': cls.device_type,
                        'device.source': '/dev/'+i
                    }
                )

                config2['device.username'] = ''
                config2['device.password'] = ''
                l["Webcam "+i] = config2


        config2 = config.copy()
        config2.update(
            {
                'type': cls.device_type,
                'device.source': 'screen'
            }
        )

        config2['device.username'] = ''
        config2['device.password'] = ''
        config2['device.fps'] = '4'
        l["Screen Recording"] = config2


        return l
