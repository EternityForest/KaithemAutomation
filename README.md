![Kaithem Automation](img/logo.jpg)
(Clipart credit: https://openclipart.org/detail/1337/large-barrel)

Kaithem is Linux home/commercial automation server written in pure python, HTML, Mako, and CSS. It's more low level than your average HA system. but the web IDE model means you can control anything python can.

It runs on python2 and python3, and will likely work on any platform, but it is not tested outside of Linux.

You automate things by directly writing python and HTML via a web IDE.

Create pages and secure them with SSL and a flexible user/group/permission system.

Create events that run when an expression becomes true. An internal message bus logs events.

Write HTML Pages with Mako templates. Automatically generate WebSocket powered widgets without writing any javascript. Built in performance profiling(requires yappi).

Play audio using one of several audio backends(mplayer suggested).

The entire server state is maintained in RAM, and any changes you make to your code never touches the disk unless you explicitly save or configure auto-save. This allows experimentation without wearing out SD cards.

Saving occurs transactionally, so a copy of the state of the server is made before changing the new one. The save format is a simple YAML format that can be hand edited if needed.

You can store small amounts of data in the registry which will be persisted to disk the next time the state is saved, or there are built in libraries for YAML or JSON based persistence with atomic file updates(The old file is renamed to file~ and only deleted after the new file is created)

Logs are maintained in ram and then dumped all at once at configurable intervals.

Pages and events are types of resources that can be grouped into "modules" and uploaded and downloaded as zip files. This makes it relatively easy to manage multiple servers that need to run similar code.


Kaithem includes a library for common automation tasks such as file IO, timing, executing functions in the background, formatting numbers, and more.

Kaithem is still beta, but has been used in production applications running for months at a time.

KAITHEM WAS NOT DESIGNED FOR MILITARY, AEROSPACE, IDUSTRIAL,
MEDICAL, NUCLEAR, SAFETY OF LIFE OR ANY OTHER CRITICAL APPLICATION
ESPECIALLY THE CURRENT STILL-IN-DEVELOPMENT VERSION. YOU PROBABLY SHOULDN'T TRUST IT FOR
A SECURITY SYSTEM FOR A BAG OF FUNYUNS(tm) AT THIS POINT!

Installation
============

All dependancies should already be included. Huge thanks to the developers of all the great libraries used!!!

git clone or download somewhere and run python3 kaithem/kaithem.py
You can also use python2 if you really want.

Command line options:
    "-c"
        Supply a specific configuration file. Otherwise uses default. Any option not found in supplied file
        Reverts to default the files are YAML, see kaithem/data/default_configuration.txt for info on options.

    "-p"
        Specify a port. Overrides all config stuff.


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


### 0.56

-   Eliminate the frame-based polling system, polled events are now scheduled using the scheduler, which should improve performance when there no events used that poll quickly.
-   -   Events with priority of realtime now run in their own threads
-   Kaithem.persist now assumes relative paths are relative to vardir/moduledata, which is a new folder defined for modules to store large amounts of variable data without cluttering the registry.
-   Add kaithem.web.goto(url) function
-   New Virtual Resource mechanism for updatable objects
-   Option not to have APIWidgets echo back messages sent to server
-   New state machines API
-   Fix the uptime function
-   No longer log every event run, it was causing a performance hit with realtime events and wasn't that useful
-   Logging is now based on python's builtin logging module, meaning log dumps are readable now.
-   Realtime scrolling log feeds powered by the new scrollbox widget.
-   Logging format defaults to null
-   Fix security error in viewing logs


### 0.55

-   Fix bug where SI formatted numbers were rounded down
-   Multiple message bus subscribers run simultaneously instead of sequentially
-   Events now have an enable option
-   Message events can now be ratelimited, additional messages are simply ignored
-   Slight theming improvements
-   Sound search path feature, added built in sounds
-   Modules now display MD5 sums(Calculated by dumping to UTF-8 JSON in the most compact way with sorted keys. Module and resource names are also hashed, but the locations of external modules are ignored)
-   Use of the print function in an event under python3 will print both to the console and to the event's editing page(only most recent 2500 bytes kept)
-   Change the way the scheduler works
-   Setup actions no longer run twice when saving! (However, setup actions may run and retry any number of times due to dependency resolution at bootup)
-   Fix bug where references in the locals of deleted or modified events sometimes still hung around and messed up APIs based on \_\_del\_\_
-   Stable initial event loading attempt order(Sorted by (module,resource) tuple.) Failed events will be retried up to the max attempts in the same order.
-   Kaithem now appears to shut down properly without the old workaround
-   Ship with the requests library included, but prefer the installed version if possible
-   Add ability to store individual modules outside of kaithem's directory, useful for development
-   Support for embedded file resources in modules
-   Eliminate polling from all builtin widgets. Switched to a pure push model. THIS IS A POSSIBLE BREAKING CHANGE FOR CUSTOM WIDGETS, although since those were never really properly documented it will likely be fine, and only minor changes will be required to accommodate this new behavior. All default widgets are exactly the same from a user perspective, only faster and more efficient.
-   Can now inspect event scopes just like module objects. Inspectors have been greatly improved.
-   Run a garbage collection sweep after deleting events or modules.
-   Fix bug where "don't add additional content" still added a footer.
-   kaithem.web.resource lookups
-   Add jslibs module
-   Can now manually run any event
-   Lots of stability improvements
-   No more widget callbacks running twice
-   Add six.py to thirdparty library(Cherrypy now depends on it)
-   Fix bug saving data with unicode in it on some versions
-   Fix error loading resources with DOS style line endings
-   Fix spelling error in quotes file

License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
