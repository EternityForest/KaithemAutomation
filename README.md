![Logo (Credit: https://openclipart.org/detail/1337/large-barrel)](img/logo.jpg)

Kaithem is Linux home/commercial automation server written in pure python, HTML, Mako, and CSS. It's more low level than your average HA system, but it allows you to control anything python can.

Kaithem uses a user/group/permission system with SSL support, and is designed to be fairly secured.
I'm not a security researcher, but it should at the very least keep casual snoopers on the LAN out.
![Login page](screenshots/login.png)


It runs on python2 and python3, and will likely work on any platform(Windows/mac/etc), but it is not tested outside of Linux. Resource usage is low enough to run well on the raspberry pi.

You automate things by directly writing python and HTML via a web IDE.
![Editing an event](screenshots/edit-event.jpg)

Almost the entire server state is maintained in RAM, and any changes you make to your code never touches the disk unless you explicitly save or configure auto-save. Even log files get buffered in RAM for a configurable duration before being saved. This allows experimentation without wearing out SD cards.

Saving occurs transactionally, so a copy of the state of the server is made before changing the new one. The save formats for most things are simple text file with a YAML that can be hand edited if needed, and can be version controlled.

You can store small amounts of data in the registry which will be persisted to disk the next time the state is saved, or there are built in libraries for YAML or JSON based persistence with atomic file updates(The old file is renamed to file~ and only deleted after the new file is created)

Pages and events are types of resources that can be grouped into "modules" and uploaded and downloaded as zip files. This makes it relatively easy to manage multiple servers that need to run similar code.

There's a built in realtime websocket-based log viewer to assist with debugging, and several features to
make detecting intrusions and errors easier.
![Settings](screenshots/settings.jpg)

Kaithem includes a library for common automation tasks such as file IO, timing, executing functions in the background, formatting numbers, and more. It also includes a library of basic example modules, including a
web-based lighting console.

![Lighting control](screenshots/lighting.jpg)

Kaithem is still beta, but I've used it in production applications running for months at a time. It wasn't
designed for any kind of safety-critical application, but it is meant to be reliable enough for most home and commercial applications.

Installation
============

All dependancies should already be included. Huge thanks to the developers of all the great libraries used!!!

git clone or download somewhere and run `python3 kaithem/kaithem.py`
You can also use python2 if you really want.

If you want to build a debian package, install fakeroot, go to helpers/debianpackaging and do
`fakeroot sh build.sh`

The resulting package will be in helpers/debianpackaging/build and should run on any architecture.
The package will create a new user kaithem that belongs to i2c, spi, video, serial, audio, and a few other
groups. The reason for those permissions is to access hardware on the raspberry pi, but you can
modify helpers/debianpackaging/package/postinst to change this pretty easily.

It will also generate a self signed certificate at /var/lib/kaithem/ssl. You can either follow the trust-on-first-use principle and add an exception, or replace /var/lib/kaithem/ssl/certificate.cert and
certificate.key with your own trusted certificate.

You will be prompted to create an admin password when installing.

If installing, you might want to look through kaithem/data/default-configuration.yaml, it contains
comments explaining the various config options.

Command line options:
    "-c"
        Supply a specific configuration file. Otherwise uses default. Any option not found in supplied file
        Reverts to default the files are YAML, see kaithem/data/default_configuration.txt for info on options.

    "-p"
        Specify a port. Overrides all config stuff.

    "--nosecurity 1"
        Disables all security.Any user can do anything even over plain HTTP. 
        Since 0.58.1, Also causes the server process to bind to 127.0.0.1, 
        preventing access from other machines.

        Because kaithem lets admin users run arbitrary python code,
        processes running as other users on the same machine
        essentially have full ability to impersonate you. This is really
        only useful for development on fully trusted machines, or for lost
        password recovery in secure environments.

    "--nosecurity 2"
        Similar, except allows access from other machines on the network. Not
        recommended outside of a virtual machine.

Then point your browser to https://localhost:<yourport> (default port is 8001)
and log in with Username:admin Password:password

It will give you a security warning, that the SSL certificate name is wrong,
ignore if you are just playing around, use real SSL keys otherwise.

Look at the help section and the examples module, there is a lot more documentation built into the system.

If you are really going to use this you must change the ssl keys in /ssl to something actually secret.

If you stop the process with ctrl-C, it might take a few seconds to stop normally.
If you force stop it it might leave behind a lingering process that you have to kill-9 because it holds onto the port so you can't restart kaithem.


If you install using the debian package helper, you will be prompted for an admin password.

Recent Changes(See changes.md for full change info)
=============
### 0.58

-   Safer handling of tokens to resist timing attacks
-   Get rid of excessively tiny stack size that caused ocassional segfaults
-   Fix bug that caused annoying widget.js error messages
-   Switch to microsoft's monaco editor instead of CodeMirror
-   (SOMEWHAT BREAKING CHANGE) Users are now limited by default to 64k request HTTP bodies. You can allow users a larger limit on a per-group basis. Users with \_\_all\_permissions\_\_ have no such limit, and the limit is 4Gb in certain contexts for users with the permissions to edit pages or settings.
-   Increase maxrambytes in cherrypy. It should work slightly better on embedded systems now.
-   Add command line option --nosecurity 1 to disable all security(For testing and localhost only use)
-   Better template when creating new pages
-   (SOMEWHAT BREAKING CHANGE)Use Recur instead of recurrent to handle !times, greatly improving performance.
-   Add lighting control features in the modules library.

### 0.57

-   Dump traceback in the event of a segfault.
-   Raise error if you try to send non-serializable widget value
-   Add raw pages that aren't processed through Mako's templating
-   Live logs now properly escaped
-   Rate limit login attempts with passwords under 32 chars to 1 per 3s
-   Auth tokens don't expire for 3 years
-   New page to view login failures
-   Support for IPv4/IPv6 dual stack
-   Host config option to bind to a specific IP(overrides local-access-only if specified)
-   Scheduler error handling no longer spams the logs

### 0.56.1

-   Fix bug when deleting realtime events
-   Format log records immediately instead of keeping record objects around

License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
