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
See [This page](kaithem/src/docs/setup.md). Or, to just try things out, git clone and run kaithem/kaithem.py, then visit port 8001(for https) or port 8002(for not-https) on localhost. That's really all you need to do.

There are many optional dependancies in the .deb recommended section that enable extra features. All are available in the debian repos and do not need to be compiled, except for Cython, which is installed automatically by the postinstall script of the debian package, or can easily be manually installed with "sudo pip3 install Cython".

At the moment, Cython is only used to give audio mixer gstreamer threads realtime priority.

In particular, everything to do with sound is handled by dependancies, and python3-libnacl and python3-netifaces are recommended as several networking features require them.

### Security
At some point, you should probably set up a proper SSL certificate in kaithem/var/ssl. The debian installer will generate one at
/var/lib/kaithem/ssl/certificate.key that you can replace with a real one if you don't want to go self-signed.



Recent Changes(See [Full Changelog](kaithem/src/docs/changes.md))
=============

### 0.65.20
- Startup speed improvements with JACK
- Immediately update jack settings when changing via UI
- Eliminate more useless print output
- Add better logging for JACK status


### 0.65.19
- Fix the script bindings tagpoint support

### 0.65.18
- Mixer mono channels properly connect to stereo destinations

### 0.65.17
- Fix jack mixer send elements
- Faster startup for jack

### 0.65.16
- Overhaul scullery's JACK handling for more reliability in unusual raspberry pi setups
- Avoid unnecccessariliy setting the process UID to the same value, which seems to have affected JACK
- Remove some nuisance print output

### 0.65.15
- MINOR BREAKING: The USB latency param is interpreted correctly now
- Can directly set USB period size
- Can use default alsa_out parameters
- JACK settings are stored in system.mixer/jacksettings.yaml, not the registry
- Chandler properly creates it's save folder if missing
- Fix deadlock with pylogginghandler by changing to an RLock
- GStreamer jackaudiosink tweaks fix slight glightes with multiple soundcards

### 0.65.14
- Fix bug preventing deleting Changler scenes that used MQTT or pages
- Device-side fading for flicker and vary blending modes
- Up/Download individuial scenes

### 0.65.13
- BREAKING: Devices stored as files, not in registry
- Add support for Kasa Color smart bulbs
- To support that, the render engine of Chandler has but upgraded to use on-bulb fades
- Sound has more protection against invalid interfaces


License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
