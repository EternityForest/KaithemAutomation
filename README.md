![Logo](kaithem/data/static/img/klogoapr22.jpg)


![Create a nice dashboard](screenshots/FreeboardDash.jpg)

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

There are many optional dependancies in the .deb recommended section that enable extra features. All are available in the debian repos and do not need to be compiled, except for Cython, which is installed automatically by the postinstall script of the debian package, or can easily be manually installed with "sudo pip3 install Cython".

At the moment, Cython is only used to give audio mixer gstreamer threads realtime priority.

In particular, everything to do with sound is handled by dependancies, and python3-libnacl and python3-netifaces are recommended as several networking features require them.

Several other audio file players may still work, but the only one supported and suggested is libmpv, on Debian provided by libmpv-dev.


### Systemd service

Ajdust as needed  to point to your paths and users.  Or just use emberos.
```ini
[Unit]
Description=KaithemAutomation python based automation server
After=basic.target time-sync.target sysinit.service zigbee2mqtt.service
Type=simple


[Service]
TimeoutStartSec=0
ExecStart=/opt/kaithem/kaithem/kaithem.py -c /sketch/kaithem/config.yaml
Restart=on-failure
RestartSec=15
OOMScoreAdjust=-800
Nice=-15
#Make it try to act like a GUI program if it can because some user-added python modules might
#make use of that.
Environment="DISPLAY=:0"

#This may cause some issues but I think it's a better way to go purely because of
#The fact that we can use PipeWire instead of managing jack, without any conflicts.

#Also, node red runs as pi, lets stay standard.
User=pi
#Bluetooth scannning and many other things will need this
#Setting the system time is used for integration with GPS stuff.
AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_ADMIN CAP_NET_RAW CAP_SYS_TIME



[Install]
WantedBy=multi-user.target

```

# To download all optional dependancies

See helpers/debianpackaging/CONTROL for the list

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

### 0.68.7

- Admin can see battery status of all connected devices if said device supports it
- Admin can remotely refresh any client page
- Enabling telemetry alerts for an account will raise an alarm when an associated kiosk device browser hs low battery(Chrome/Chromium only, FF killed the API on others)

### 0.68.6

- Poll every hour to find any disks that may be above 90% full and raise an alarm automatically about this.
- Disk usage status on about page

### 0.68.5

- Compatibility with newer Linux Mint
- Midi last note tags fixed
- Compatibility with yet another RTMidi variant


### 0.68.4

- Chandler tagpoint universes now correctly map the fader to the full range of the tagpoint, if it has a min and max set.
- Work on getting PWM working with GPIO.

### 0.68.3

This update focuses on securing against some unusual but not too difficult to exploit edge cases,
especially when using plain HTTP.

- All builtin permissions are inaccessible for cross-site use
- Patch a few things that accepted GET requests that should not have
- The websocket widget API is no longer usable cross-site.

### 0.68.2

- Remove excessively buggy RTP reciever mixer element.
- More UI stuff

### 0.68.1

- Fix support for HTTP logins on :ffff:192. addresses that are apparently a thing now.


### 0.68.0
This release is primarily all about theming.

- New .buttonbar and .multibar CSS classes majorly reduce visual clutter
- New default theme aims to be somewhere between material, mid 2000s forums, and early iOS
- No more ugly default inset/outset borders, we use gradients and box shadows
- Link underlines are gone


### 0.67.6

This release focuses on getting rid of functionality that is almost certainly used by nobody, was not well tested,
And was causing maintainence nightmares.

- Semi-breaking: Tag point alarms will not trigger if the tag point has never actually had a value set.
- Support for searching all modules for cross-framework devices, and importing on demand.
- Fix devices in modules bugs
- Freeboard edit controls now disabled if you don't have permissions, so you don't waste time making local changes you can't save.
- BREAKING: Remove the ability to subclass devices via UI.
- BREAKING: Remove onChange handlers directly set on tag points via UI
- BREAKING: Remove the web resources lookup mechanism
- BREAKING: Remove the Gstreamer and the Mplayer backends. Use MPV.
- BREAKING: Remove functionevents
- BREAKING: Remove the Chandler scene pages functionality
- BREAKING: Remove textual scripting in Chandler
- BREAKING: Remove the Smartbulb universes. They are replaced by feature-based auto detection of smart bulbs.

### 0.67.5
- Scheduler is now just based on the normal sched module
- Various performance improvments(Seems like 50% les CPU usage!)
- LAN Consenseus time removed
- Showing HTTPS MDNS services in the settings page removed
- Allow HTTP login from any LAN address, not just localhost
- Lots of code cleanup
- Fix orphan processes at exit
- Clean up the Examples module
- BREAKING: Change /bt/ tagpoints in the BluetoothBeacon to /device/ to match the usual convention
- Purely experimental NVRPlugin can stream live video to a page with HLS, but recording isn't there





License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
