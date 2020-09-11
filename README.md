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


### Debugging

It shouldn't happen, but if things get real messed up, use SIGUSR1 to dump hte state of all threads to /dev/shm/
"killall -s USR1 kaithem" works if you have setproctitle.

Recent Changes(See [Full Changelog](kaithem/src/docs/changes.md))
=============

### 0.65.38
- Tags will raise errors instead of deadlocking, if you manage to somehow create a deadlock
- Fix autoscroll in chandler
- Fix tag point page if an error causes the meter widget to be unavailable
- Ability to send SystemExit to threads from a settings page, to try to fix inifinite loops
- ChandlerScript/Logic editor events and tag changes are queued and ran in the background.

### 0.65.37
- Tag data historian configurable from web UI(Everything is saved to history.db if configured, CSV export is possible)
- Fix SG1 gateway tagpoint error from previous version
- Chandler Rules engine supports isLight and isDark functions.
- Fix bug that made some errors not get reported to the parent event
- Modules can now add pages to the main bar with kaithem.web.navBarPlugins
- No more link to the page index on the top
- Chandler now creates a toolbar entry
- The mixing board now has a top bar entry
- Main "Kaithem" banner is now a link to the main page by default
- Shorten "Settings and Tools" to just "tools"
- Message logging and notifications work way earlier in boot


### 0.65.36
- SculleryMQTTConnection devices let you configure MQTT through the webUI
- Chandler sound search working
- Fix enttec universes (Enttec open was already fine)
- Fix Gamma blend mode
- Fix chandler cue renumbering, nextCue is now correctly recalculated
- Chandler now refuses to allow you to change the sound for a cue created from a sound, to avoid confusion. Override by setting to silence, then the new sound.



License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
