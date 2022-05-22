![Logo](kaithem/data/static/img/klogoapr22.jpg)


![Create a nice dashboard](screenshots/FreeboardDash.jpg)

![Visitors](https://api.visitorbadge.io/api/combined?path=https%3A%2F%2Fgithub.com%2FEternityForest%2FKaithemAutomation&countColor=%23263759&style=plastic)


Kaithem is Linux home/commercial automation server written in pure python, HTML, Mako, and CSS. It's more low level than your average HA system, but it allows you to control anything python can.

It runs on python3, but it is not tested outside of Linux. Resource usage is low enough to run well on the Raspberry Pi.

You automate things by directly writing python and HTML via a web IDE. "Events" are sections of code that run when a trigger condition happens. Trigger conditions can be polled expressions, internal message bus
events, or time-based triggers using a custom semi-natural language parser.

![Editing an event](screenshots/edit-event.webp)


Almost the entire server state is maintained in RAM, and any changes you make to your code never touches the disk unless you explicitly save or configure auto-save.

![Lighting control](screenshots/lightboard.webp)
![Sound Mixer](screenshots/mixer.webp)


Kaithem also includes a module called Chandler, which is a full web-based lighting control board with a visual
programming language for advanced interactive control.

Kaithem is still beta, but I've used it in production applications running for months at a time. 

It wasn't designed for any kind of safety-critical application, but it is meant to be reliable enough for most home and commercial applications.

Installation
============

## Documentation
Kaithem's help files are being migrated to markdown. You can browse right on github,
or access the full help via the web interface!
*  [help](kaithem/src/docs/help.md)
*  [FAQ(old)](kaithem/src/docs/faq.md)


## Setup
See [This page](kaithem/src/docs/setup.md). Or, *to just try things out, git clone and run kaithem/kaithem.py, then visit port 8001(for https) or port 8002(for not-https) on localhost. That's really all you need to do.*

Since there are initially no users, one is created using the name and password of the Linux user actually running the app.
This means you must run kaithem as a user that supports logins.

Note that to clone everything properly you must have git-lfs installed and set up, otherwise you won't get the tflite
data file needed for video recognition.

To set this up globally, do `sudo apt install git-lfs` then `git lfs install --skip-repo`. No I don't know why
Git doesn't have this in the core by default.

There are many optional dependancies in the .deb recommended section that enable extra features. All are available in the debian repos and do not need to be compiled, except for Cython, which is installed automatically by the postinstall script of the debian package, or can easily be manually installed with "sudo pip3 install Cython".

At the moment, Cython is only used to give audio mixer gstreamer threads realtime priority.

In particular, everything to do with sound is handled by dependancies, and python3-libnacl and python3-netifaces are recommended as several networking features require them.

Several other audio file players may still work, but the only one supported and suggested is libmpv, on Debian provided by libmpv-dev.


## To install all required and optional dependencies 

```bash
sudo apt install python3 cython3 build-essential python3-msgpack python3-future apt install python3-serial  python3-tz  python3-dateutil  lm-sensors  python3-netifaces python3-jack-client  python3-gst-1.0  python3-libnacl  jack-tools  jackd2  gstreamer1.0-plugins-good  gstreamer1.0-plugins-bad  swh-plugins  tap-plugins  caps   gstreamer1.0-plugins-ugly  python3-psutil  fluidsynth libfluidsynth2  network-manager python3-paho-mqtt python3-dbus python3-lxml gstreamer1.0-pocketsphinx x42-plugins baresip autotalent libmpv-dev python3-dev  libbluetooth-dev libcap2-bin rtl-433  python3-toml  python3-rtmidi python3-pycryptodome  gstreamer1.0-opencv  gstreamer1.0-vaapi python3-pillow python3-scipy ffmpeg python3-skimage python3-evdev python3-xlib
```

You will also need Python's tflite_runtime for deep learning image recognition in the NVR.  
python3 -m pip install tflite-runtime  will do it on linux.

You don't need a model! A version of efficientdet-lite0 is included.  Accuracy should be better than the bare
model itself as we use heuristics to reduce false positives.

### Systemd service

Ajdust as needed  to point to your paths and users.  Or just use emberos.

Leave of the pw-jack in the front of ExecStart if you do not have PipeWire(If not on a Red Hat system or EmberOS, you likely don't yet as of now)

```ini
[Unit]
Description=KaithemAutomation python based automation server
After=basic.target time-sync.target sysinit.service zigbee2mqtt.service pipewire.service
Type=simple


[Service]
TimeoutStartSec=0
ExecStart=pw-jack /opt/kaithem/kaithem/kaithem.py -c /home/pi/kaithem/config.yaml
Restart=on-failure
RestartSec=15
OOMScoreAdjust=-800
Nice=-15
#Make it try to act like a GUI program if it can because some modules might
#make use of that.  Note that this is a bad hack hardcoding the UID.
#Pipewire breaks without it though.
Environment="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus"
Environment="XDG_RUNTIME_DIR=/run/user/1000"

#This may cause some issues but I think it's a better way to go purely because of
#The fact that we can use PipeWire instead of managing jack, without any conflicts.

#On desktop-like systems, 1000 is typically the first user(In this case pi)
#You can also just specify a username directly.
User=1000
#Bluetooth scannning and many other things will need this
#Setting the system time is used for integration with GPS stuff.
AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_ADMIN CAP_NET_RAW CAP_SYS_TIME CAP_SYS_NICE
SecureBits=keep-caps

LimitRTPRIO= 95
LimitNICE= -20
LimitMEMLOCK= infinity


StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target

```

# To download all optional dependancies

See helpers/debianpackaging/CONTROL for the list

## Installing Object Detection

The NVRChannel plugin uses the full YOLOv3 model, until such a time as I can get a lighter model to work.  It needs these two files:
https://pjreddie.com/media/files/yolov3.weights
and 
https://github.com/arunponnusamy/object-detection-opencv/raw/master/yolov3.cfg

To be in one of several locations.

'/home/USER/.cvlib/object_detection/yolo/yolov3'
'/usr/share/pjreddie_darknet/yolov3_coco'

Note that if you have ever used the cvlib library it auto downloads in /home/USER/.cvlib/object_detection/yolo/yolov3
And also, the files are already included in EmberOS.

### Security
At some point, you should probably set up a proper SSL certificate in kaithem/var/ssl. The debian installer will generate one at
/var/lib/kaithem/ssl/certificate.key that you can replace with a real one if you don't want to go self-signed.


### Debugging

It shouldn't happen, but if things get real messed up, use SIGUSR1 to dump hte state of all threads to /dev/shm/
"killall -s USR1 kaithem" works if you have setproctitle.

#### with GDB
If using GDB python, you may need to use "handle SIG32 nostop" to suppress abboying notifications:

gdb python3
$handle SIG32 nostop
$run YOUR_KAITHEM_PY_FILE





Recent Changes(See [Full Changelog](kaithem/src/docs/changes.md))
=============

### 0.68.32
- :fire: Roku ECP device app improved. API breaking.
- :sparkles: Chandler scenes understand Roku commands like VolumeUp and Play
- :sparkles: Better display for readme attribute of devices
- :arrow_up: Update the Monaco editor



### 0.68.31
- :sparkles: Module descriptions on the index page.
- :sparkles: Module descriptions are now Markdown
- :coffin: Broken years-old JookBawkse module removed
- :bug: Un-break  creating new YeelightRGB devices

### 0.68.30
- :bug: Object tags could get in an invalit state and prevent page load
- :bug: Correctly detect NVR failure if snapshotting fails
- :sparkles: Chandler scenes now have a "Command Tag", that allows you to accept shortcut codes from any event tag(Like to Roku Launch button)
- Fewer memory usage and page load count logs
- :sparkles: Chandler scenes now let you view the recent history


### 0.68.29
- :bug: Print less log info and silently drop some records if we are running out of disk space, so as not to worsen the problem by logging it.


### 0.68.28
- :lock: :coffin: Default admin:password credentials have been eliminated. 
- :sparkles: If there are no users, one is created using the login credentials of the Linux user actually running the Kaithem service
- :sparkles: Any user can be set to use the system authentication.  Using Kaithem's weaker internal login is not suggested.
- :fire: The internal auth mechanism may be deprecated or modified eventually. Suggest to always use the Linux system auth instead.
- :bug: Fix bug with changing usernames at the same time as settings
- :bug: UI for setting Chandler scenes now looks better on mobile
  
### 0.68.27
- :bug: Avoid useless logging client side errors caused by Firefox not supporting idle status at all
- :bug: NVRChannel auto reconnect used to never retry again if the very first attempt was a failure.
- :bug: Avoid rare bug that killed the WS manager thread
- :bug: Fix plaintest HTTP support for video streams

### 0.68.26

- :wrench: Temperature warning at 76 degrees
- :wrench: NVRPlugin camera disconnect alarm delay is 90 seconds to reduce false trips
- :bug: :lock: Remove default read/write permissions for devices, they must now be manually added
- :lipstick: Read/write permissions for devices have auto-suggest now

### 0.68.25 "Just Use PipeWire"

This release is all about getting rid of the JACKD manager. Instead, you use an external jack server if you have fancy
mixing. See: https://askubuntu.com/questions/1339765/replacing-pulseaudio-with-pipewire-in-ubuntu-20-04 for info
on switching to PipeWire.  The next EmberOS will have Pipewire running by default already.

- :coffin: Remove ability for kaithem to manage PipeWire or JACK. That should be done by the system.
- :coffin: Remove PulseAudio sharing mode. Use Pipewire, manage it yourself, or just don't use Pulse
- :coffin: JACKD is considered legacy tech and support will be removed as soon as all common Debian platforms easily support PipeWire
- :coffin: Remove ability to manage USB soundcards. Pipewire does that for us!
- :bug: Fix object inferrence on versions of the imaging library
- :bug: Fix downloading modules as ZIP
- :bug: Fix a bug where an old airwire could get GCed and delete a newer wanted audio link
- :bug: Fix Select() not working on some systems in JSONRPYC


### 0.68.24
- :bug: Fix missing platformdirs.version
- :sparkles: NVRChannel discovery for Amcrest cameras, because that's what I've got lying around.
- :monocle_face: Please be aware: Many major CCTV manufactures are rebrands of just a few firms that may be supporting things you may find morally abhorrent.


License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
