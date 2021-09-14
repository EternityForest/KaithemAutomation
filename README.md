![Logo](kaithem/data/static/img/klogoapr22.jpg)

Kaithem is Linux home/commercial automation server written in pure python, HTML, Mako, and CSS. It's more low level than your average HA system, but it allows you to control anything python can.

It runs on python3, but it is not tested outside of Linux. Resource usage is low enough to run well on the Raspberry Pi.

You automate things by directly writing python and HTML via a web IDE. "Events" are sections of code that run when a trigger condition happens. Trigger conditions can be polled expressions, internal message bus
events, or time-based triggers using a custom semi-natural language parser.

![Editing an event](screenshots/edit-event.jpg)


Almost the entire server state is maintained in RAM, and any changes you make to your code never touches the disk unless you explicitly save or configure auto-save.

![Lighting control](screenshots/basictheme_lightboard.png)

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

There are many optional dependancies in the .deb recommended section that enable extra features. All are available in the debian repos and do not need to be compiled, except for Cython, which is installed automatically by the postinstall script of the debian package, or can easily be manually installed with "sudo pip3 install Cython".

At the moment, Cython is only used to give audio mixer gstreamer threads realtime priority.

In particular, everything to do with sound is handled by dependancies, and python3-libnacl and python3-netifaces are recommended as several networking features require them.

Several other audio file players may still work, but the only one supported and suggested is libmpv, on Debian provided by libmpv-dev.


# To download all optional dependancies

sudo apt install pulseaudio python3-pyserial python3-pytz python3-dateutil lm-sensors python3-netifaces python3-jack-client python3-gst-1.0 python3-libnacl jack-tools jackd2 gstreamer1.0-plugins-good gstreamer1.0-plugins-bad swh-plugins sudo apt install tap-plugins caps  gstreamer1.0-plugins-ugly python3-psutil fluidsynth libfluidsynth2 network-manager python3-paho-mqtt python3-dbus python3-lxml gstreamer1.0-pocketsphinx x42-plugins baresip autotalent libmpv-dev


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

### 0.65.64
- Now we support those cheap SainSmart relay boards with a tagpoint based interface.  Use the Relayft245r device type.
- Freeboard default values don't clobber existing stuff if it is there, for the slider and switch widgets.
- Broadcast Center sends snackbar text alerts to most/all devices accessing the server
- kaithemobj.widgets.sendGlobalAlert(message, duration) to programmatically send HTML in a snackbar to all devices.
- New tag.control: expose API gives write only control, for when you want to both claim the tag and separately see it's current real value
- New /pages/chandler/sendevent?event=NAME&value=VALUE API
- User pages now show telemetry on what WS connections are open from what IP addresses on what pages. Use
- BREAKING CHANGE: the default topics used by the MQTT Tag sync no longer use a slash.
- Correctly handle MQTT passsive connections that are created after the real connection

### 0.65.63
- Avoid slow cue transition performace when there is a cue loop
- New compatibility/dummy mode for managing jack(Gives better performance on some systems, can work on new raspbian)
- Freeboard now supports both click and release actions for buttons
- Fix nuisiance error logging in chandler console inspect window

### 0.65.62
- Corerctly autocreate the log dir
- Storing devices in modules

### 0.65.61
- Fix tag point subscriber not firing immediately in some edge cases
- Bigger text boxes on tag point pages, for longer expressions


### 0.65.60
- "Length relative to sound" copied over when cloning cues in Chandler
- USB audio devices default to 2048 samples and 3 periods if Kaithem is managing JACK.
- Tag point getter functions now correctly update when given falsy values
- Add alert for ethernet loss
- Tagpoint claim.setExpiration(time,expiredPriority) specifies an alternate priority for a claim if it has not been updated in a certain time.
-- This feature cah be used to detect when a data source is old.
- No longer automatically set a shortcut code for Changler cues, provide a button to set to the number instead
- Other chandler shortcuts still fire if one of them has an error
- Clean up the chandler interface even more
- 4x speedup setting tag point values
- Breaking change: mixer tagpoints use .property instead of /property format

### 0.65.59
- Eliminate the cherrypy autoreloader, it was being more trouble than it is worth.
- Fix ZigBee light tag
- Fix support for multiple ZigBee devices at the same time
- Fix CSS on object inspector

### 0.65.58
- DrayerDB integration can now log system notifications
- DrayerDB configurable autoclean for old notifications.
- Update drayerDB, properly support compressed records.
- Breaking change: Zigbee device property tagpoints use .property instead of /property format


### 0.65.57
- Tag point timestamp correctly starts at 0 when not yet set by anything
- Zigbee2MQTT Alarm Bugfixing
- Use prompt instead of text input to prevent browser caching sensitive info in DrayerDB sharing codes


### 0.65.56
- Update HardlineP2P


### 0.65.55
- Tag history DB file now includes the name of the node that wrote it.
- Semi breaking change, not really, the log directory is now compartmented by which hostname-user actually wrote the logs, in case the vardir is synced between machines.
- File manager now includes a youtube-dl frontend, for legal purposes only.
- Ability to ship device drivers inside a module, with proper dependency resolution on boot.
- Include pure python fallback for messagepack
- New BinaryTag tagpoint type
- Fix error when re-saving event with exposed tag
- Zigbee2MQTT is now supported.  Add the Zigbee daemon as a device type and most supported devices should show up as tag points.
- DrayerDB is now supported. Kaithem is now the preferred way to manage DrayerDB servers.


License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
