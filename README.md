KaithemAutomation
=================

Flexible Linux home/commercial automation server written in python, HTML, Mako, and CSS. More low level than your average HA system. May work on non-linux, but it is not tested.

You automate things by directly writing python and HTML via a web IDE. Create pages and secure them with a flexible user/group/permission system! Create events that run when an expression becomes true! An internal message bus logs events. Write HTML Pages with mako templates. Automatically generate websocket powered widgets without writing any javascript. Built in performance profiling(requires yappi). Play audio using one of several audio backends(mplayer suggested).

The entire server state is maintained in RAM, and any changes you make to your code never touches the disk unless you explicitly save or configure
auto-save. This allows experimentation without wearing out flash drives. Logs are also maintained in ram and then dumped all at once at configurable intervals. The save format is a simple JSON format that can be hand edited if needed. Most save files are never overwritten, instead a new file is created and then the old one deleted only after the new one is complete, preventing certain file corruption issues.

Kaithem includes a lbrary for common automation tasks such as file IO, timing, executing functions in the background, formatting numbers, and more.

Scheduling an event to run at 3pm is as simple as "!time 3pm" with the new special trigger expressions.

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

Change Log
=============

###0.52(Minor Bugfix Release)

* Fix about box error on windows 
* Fix non-cross platform default strftime 
* Should the user enter a bad strftime, revert to the default
* Fix error saving uncompressed logs 
* Add mplayer and lm-sensors to acknowledgements 



###0.51 IMPORTANT SECURITY UPDATE VERSION!!!!!!!!!!!!!!!!!!!!!!!!
* Fix bug where kaithem would set it's var folders to publically readable if the wrong umask settings were used(Which is basically always)

###0.5

* kaithem.time.accuracy() returns an estimate of the max error in the current system time in seconds using NTP.
* Slight performance boost for low-priority events
* kaithem.misc.errors(f) calls f with no args and returns any exceptions that might result.
* Automatic daily check of mail settings in case someone changed things.
* kaithem.string.formatTimeInterval()
* When a user logs in, his [username,ip] is posted to /system/auth/login, or to /auth/user/logout when he logs out.
* Ability to set default vaules for lattitude and longitude in astro functions.
* When a user logs in, logs out, or fails to log in, his username and IP address are posted to /auth/user/loginfail
* Lots of misc logging
* (very) Basic versioning support for events, will save your draft in case of error, and allows reverting.
* Auto fall back to tilde version if kaithem.persist.load fails(autorecover=false to disable this)
* One page with syntax errors can no longer crash kaithem at loadtime
* Support for !time trigger expressions
* About Page now shows module versions
* Defaults for precision parameter of kaithem.string methods
* Default strftime string now only uses portable characters
* Revert cherrypy to 3.2.3 for users running python 2.
* Fix error pages on python2
* Fix python2 inability to create new events
* Default FPS is 60 instead of 24
* Fix intermittent error that sliders sometimes raised because write() was converting to string
* Fix documentation on the widget system
* (partial)Ability to reload the configuration files
* File manager now sorted
* New APIWidget allows you to easily interact with the server in custom javascript.
* Onrelease slider widget lets you see what you are doing before you let go
* mplayer backend works even without pulseaudio
* Document kaithem.registry functions
* Pause, unpause, and set volume now work correctly in python2
* JookBawkse module now has better interface, shows now playing in realtime, allows rescanning the media library
* Fix bug where the registry entries were the same object as what you set instead of a copy.
* Fix Bug where some pages were not showing up in the pagelisting even if the user had permissions
* Fix bug where trying to render a widget with write permissions crashed if a __guest__ tried

###0.45 Hotfix 001
* Fix "changed size during iteration" event bug, Replace outdated event scoping documentation.

###0.45
* Built in profiling(with yappi)
* View processes on the server(on linux)
* Bash Console
* Upgrade cherrypy version to 3.3.0(Only for python 3)
* Cleaner toolbar layout
* Support for MPlayer as an audio backend
* File Browser
* Kaithem.persist API for working with files on disk
* Pause/Unpause/change volume while playing(mplayer only)
* Fixed lack of HTML escaping on the non-ace event editor
* Change autoreload interval to 5 seconds for a slight performance boost on raspi
* kaithem.misc.uptime()
* Modules Library
* Horizontal Slider Widgets
* Stop sounds from settings page
* __default__ pages catch nonexistant pages
* Fix bash console
* /system/modules/loaded and /system/modules/unloaded messages
* New __all_permissions__ permission that grants every permission on the system.
* kaithem.string.userstrftime and kaithem.string.SIFormat
* User Settings Page shows a list of what permissions you have

###Version 0.4

* New AJAX widgets(!)
* Critical dependancy resolution/initialization bugfix
* Critical ependancy resolution bugfix
* Critical bugfix for the error that prevented editing things that errored during initialization
* Minor bugfix: event rate limit displays properly
* Status bar notifications work with chrome now
* Ability to disable JS code highlighting per user(for mobile browsers)
* Kaithem Registry
* Theming Improvements
* kaithem.time.moonAge() renamed to kaithem.time.moonPhase()

License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmmodifed from Mako and Cherrypy, two excellent open source projects.
Those projects remain under their respective licenses.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

