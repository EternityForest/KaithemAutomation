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



Recent Changes(See [Full Changelog](kaithem/src/docs/changes.md))
=============

### 0.63

-   New tagpoints(Like SCADA tagpoints) with Pavillion sync to Arduino
-   Kasa smartplug support
-   Migrate docs to markdown
-   Message bus can handle any python object type
-   Workarouds for the "Too many open file descriptors" issues.
-   Major MDNS and NTP improvements
-   MDNS browsing page
-   QR Code display in about page
-   Proper cache support for favicon
-   Notifications use websockets, not polling
-   Lighting subsystem improvements
-   Logging bugfixes

### 0.62

-   Major performance bugfixes


License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
