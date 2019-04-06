![Logo](kaithem/data/static/img/klogoapr22.jpg)

Kaithem is Linux home/commercial automation server written in pure python, HTML, Mako, and CSS. It's more low level than your average HA system, but it allows you to control anything python can.

Kaithem uses a user/group/permission system with SSL support, and is designed to be fairly secured.
I'm not a security researcher, but it should at the very least keep casual snoopers on the LAN out.
![Login page](screenshots/login.png)


It runs on python2 and python3, but it is not tested outside of Linux. Resource usage is low enough to run well on the Raspberry Pi.

You automate things by directly writing python and HTML via a web IDE. "Events" are sections of code that run when a trigger condition happens. Trigger conditions can be polled expressions, internal message bus
events, or time-based triggers using a custom semi-natural language parser.

![Editing an event](screenshots/edit-event.jpg)


Almost the entire server state is maintained in RAM, and any changes you make to your code never touches the disk unless you explicitly save or configure auto-save. This allows experimentation without wearing out SD cards.

Saving occurs transactionally, so a copy of the state of the server is made before changing the new one. The save formats for most things are simple text file with a YAML that can be hand edited if needed, and can be version controlled.

You can update systems by downloading and uploading events and pages as zip files(Grouped into "modules), making deployment easy.

There's a built in realtime websocket-based log viewer to assist with debugging, and several features to
make detecting intrusions and errors easier.
![Settings](screenshots/settings.jpg)

Kaithem includes a library for common automation tasks such as file IO, timing, executing functions in the background, formatting numbers, and more, including a graphical lighting console!

![Lighting control](screenshots/lighting.jpg)

Kaithem is still beta, but I've used it in production applications running for months at a time. It wasn't
designed for any kind of safety-critical application, but it is meant to be reliable enough for most home and commercial applications.


## Documentation
Kaithem's help files are being migrated to markdown. You can browse right on github,
or access the full help via the web interface!
*  [help](kaithem/src/docs/help.md)
*  [FAQ(old)](kaithem/src/docs/faq.md)


## Setup
See [This page](kaithem/src/docs/setup.md)



Recent Changes(See changes.md for full change info)
=============

### 0.62
- Performance and lighting bugfix release

### 0.61

-   Detect unclean shutdown
-   Lightboard improvements
-   New alarms feature
-   Experimental Kaithem for Devices
-   Improvements to the Pavillion protocol(Possibly breaking)
-   Better support for multiple soundcards

### 0.60

-   Can now view event history
-   Lighting module cue matrix view, and many other lighting improvements.
-   Add breakpoint function
-   UTF-8 encoding in page responses
-   kaithem.time.lantime() for a time value automatically synced across the LAN (py3.3 only, netifaces required)
-   **BREAKING CHANGE** Widget.doCallback,onRequest, and onUpdate now expect a connection ID parameter.
-   New Widget.attach2(f) function for 3 parameter callbacks, username,value, and connection ID
-   New widget.sendTo(val,target) function to send to a specific connection ID
-   apiwidget.now() function added on javascript side to get the current server time.
-   Correctly attribute "And ninety-nine are with dreams content..." to a Ted Olson poem, not to Poe as the internet claims.
-   FontAwesome and Fugue icon packs included
-   Misc bugfixes

License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
