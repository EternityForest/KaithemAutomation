Change Log
----------

### 0.64
- Option to open port with UPnP
- Built in UPnP scanner to detect security issues
- Full copy of the python3.8 documentation available locally in the help section
- Sound Mixer built in(if using JACK)
- Lightboard better suited for media
- Dynamic Fixture Mapping in Lightboard
- If the server is restarted but the system itself remains running, all module and registry changes persist in RAM
    on linux.
- Many bugfixes
- Boot time is several times faster
- No limit to event traceback stack depth
- Remove posting to /system/threads/start, it created a refactoring nightmare and wasn't useful
- Remove system/errors/workers for the same reason, traditional logging makes it obsolete.
- Hopefully resolved the SSL segfault
- Auto-adopt stuff to the default kaithem user if started as root(Useful if things are modified by sudo)
- Minor breaking: Resources all have file extensions, old loaded modules may have odd names but will load
- Events are now stored as standard python files with data in variables, for easy viewing in external editors
- New kaithem.web.controllers: Easily create pages directly in python code using cherrypy directly without losing the flexibility of Kaithem.


### 0.63.1
-  Fix JS dependancy error in lighting module

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

### 0.61

-   Detect unclean shutdown
-   Lightboard improvements
-   New alarms feature
-   Experimental Kaithem for Devices
-   Improvements to the Pavillion protocol(Possibly breaking)
-   Better support for multiple soundcards

### 0.60

-   Can now view event history
-   Lighting module cue matrix view, and many other lighting
    improvements.
-   Add breakpoint function
-   UTF-8 encoding in page responses
-   kaithem.time.lantime() for a time value automatically synced across
    the LAN (py3.3 only, netifaces required)
-   **BREAKING CHANGE** Widget.doCallback,onRequest, and onUpdate now
    expect a connection ID parameter.
-   New Widget.attach2(f) function for 3 parameter callbacks,
    username,value, and connection ID
-   New widget.sendTo(val,target) function to send to a specific
    connection ID
-   apiwidget.now() function added on javascript side to get the current
    server time.
-   Correctly attribute "And ninety-nine are with dreams content..." to
    a Ted Olson poem, not to Poe as the internet claims.
-   FontAwesome and Fugue icon packs included
-   Misc bugfixes

### 0.59

-   Object inspector now handles weak references, weakvaluedicts, and
    objects with \_\_slots\_\_
-   Lighting module has changed to a new cue based system(Not compatible
    with the old one)
-   Fix python2 bug that prevented booting
-   Tweak mako autoformat options and log formatting

### 0.58

-   Safer handling of tokens to resist timing attacks
-   Get rid of excessively tiny stack size that caused ocassional
    segfaults
-   Fix bug that caused annoying widget.js error messages
-   Switch to microsoft's monaco editor instead of CodeMirror
-   (SOMEWHAT BREAKING CHANGE) Users are now limited by default to 64k
    request HTTP bodies. You can allow users a larger limit on a
    per-group basis. Users with \_\_all\_permissions\_\_ have no such
    limit, and the limit is 4Gb in certain contexts for users with the
    permissions to edit pages or settings.
-   Increase maxrambytes in cherrypy. It should work slightly better on
    embedded systems now.
-   Add command line option --nosecurity 1 to disable all security(For
    testing and localhost only use)
-   Better template when creating new pages
-   (SOMEWHAT BREAKING CHANGE)Use Recur instead of recurrent to handle
    !times, greatly improving performance.
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
-   Host config option to bind to a specific IP(overrides
    local-access-only if specified)
-   Scheduler error handling no longer spams the logs

### 0.56.1

-   Fix bug when deleting realtime events
-   Format log records immediately instead of keeping record objects
    around

### 0.56

-   Eliminate the frame-based polling system, polled events are now
    scheduled using the scheduler, which should improve performance when
    there no events used that poll quickly.
-   -   Events with priority of realtime now run in their own threads
-   Kaithem.persist now assumes relative paths are relative to
    vardir/moduledata, which is a new folder defined for modules to
    store large amounts of variable data without cluttering the
    registry.
-   Add kaithem.web.goto(url) function
-   New Virtual Resource mechanism for updatable objects
-   Option not to have APIWidgets echo back messages sent to server
-   New state machines API
-   Fix the uptime function
-   No longer log every event run, it was causing a performance hit with
    realtime events and wasn't that useful
-   Logging is now based on python's builtin logging module, meaning log
    dumps are readable now.
-   Realtime scrolling log feeds powered by the new scrollbox widget.
-   Logging format defaults to null
-   Fix security error in viewing logs

### 0.55

-   Fix bug where si formatted numbers were rounded down
-   Multiple message bus subscribers run simultaneously instead of
    sequentially
-   Events now have an enable option
-   Message events can now be ratelimited, additional messages are
    simply ignored
-   Slight theming improvements
-   Sound search path feature, added built in sounds
-   Modules now display MD5 sums(Calculated by dumping to UTF-8 JSON in
    the most compact way with sorted keys. Module and resource names are
    also hashed, but the locations of external modules are ignored)
-   Use of the print function in an event under python3 will print both
    to the console and to the event's editing page(only most recent 2500
    bytes kept)
-   Change the way the scheduler works
-   Setup actions no longer run twice when saving! (However, setup
    actions may run and retry any number of times due to dependancy
    resolution at bootup)
-   Fix bug where references in the locals of deleted or modified events
    sometimes still hung around and messed up APIs based on \_\_del\_\_
-   Stable initial event loading attempt order(Sorted by
    (module,resource) tuple.) Failed events will be retried up to the
    max attempts in the same order.
-   Kaithem now appears to shut down properly without the old workaround
-   Ship with the requests library included, but prefer the installed
    version if possible
-   Add ability to store individual modules outside of kaithem's
    directory, useful for develpoment
-   Support for embedded file resources in modules
-   Eliminate polling from all builtin widgets. Switched to a pure push
    model. THIS IS A POSSIBLE BREAKING CHANGE FOR CUSTOM WIDGETS,
    although since those were never really properly documented it will
    likely be fine, and only minor changes will be required to
    accomodate this new behavior. All default widgets are exactly the
    same from a user perspective, only faster and more efficient.
-   Can now inspect event scopes just like module objects. Inspectors
    have been greatly improved.
-   Run a garbage collection sweep after deleting events or modules.
-   Fix bug where "don't add aditional content" still added a footer.
-   kaithem.web.resource lookups
-   Add jslibs module
-   Can now manually run any event
-   Lots of stability improvements
-   No more widget callbacks running twice
-   Add six.py to thirdparty library(Cherrypy now depends on it)
-   Fix bug saving data with unicode in it on some versions
-   Fix error loading resources with DOS style line endings
-   Fix spelling error in quotes file

### 0.54

-   New file browser like module view
-   New resource type: folder
-   Support for \_\_index\_\_ pages
-   Raise exception if port not free instead of exiting silently.
-   New config option: log-format: null discards logs instead of saving
    them.
-   Slider widgets only show a few decimal places now
-   Fix pagename not defined issue that interfered with proper error
    logging in pages
-   Add more complete logging info to page error logs. The user's IP,
    and the exact URL they tried will be logged.
-   Flag errors in red in log page
-   Fix bug where message events were not stopping when deleted
-   Page Error logs now show IP address of requester and any
    cookies(requires permission "users/logs.view")
-   Retrying logging in no longer redirects to same error page even if
    sucessful
-   Fix weird file not found linux error in file manager that made
    dangling symlinks screw everything up
-   Fix bug where text selection and links sometimes don't work in text
    display widgets
-   Errors in zip uploads show up on the event pages themselves
-   Add JS to sliders to try to stop unintentional page slipping around
    on mobile
-   Errors in widget callback functions now post to
    /system/errors/widget s
-   Can now inspect module objects
-   Page acesses can be logged
-   Adding a \_\_doc\_\_ string to the code in the setup portion of an
    event will now add a description on the module index.
-   You can also add doc string descriptions to pages with a module
    level block comment and \_\_doc\_\_="str"
-   One must have either /admin/modules.edit, /users/logs.view, or
    /admin/errors.view to view page or event errors.
-   Better default new page contents
-   Mouse over the unsaved change asterix to view specifically what has
    unsaved changes.
-   Unsaved registry changes now have the asterix
-   Paginated logs, fix major bug with logging
-   /system/notifications/important notifications are highlighted
-   Switch to CodeMirror instead of ace for better theming and mobile
    support(You may need to anable it in your user settings)
-   Improve normalization of messagebus topics, which had caused some
    problems with missed messages in the log.
-   Basic Debian packaging tools
-   Private option for kaithem.persist.save
-   Errors occurring in widget callbacks are now reported on the front
    page errors log.
-   Threads page tells you what the thread class is
-   New(Fully compatible with old saves) save format that is much easier
    to work with manually and with git
-   kaithem.misc.version and kaithem.misc.version\_info values
-   Usability Improvements
-   !function event triggers let you trigger an event by calling a
    function
-   Remove unsafe GET requests
-   Fix security hole in loading library module that allowed any user to
    do so.
-   Increase stack size to 256K per thread, preventing segfaults
-   Fix bug where all accesses to user pages had to use the same lock
    which meant that accessing a page could actually cause a deadlock if
    accessing that page caused an HTTP to another page
-   Lots of misc changes

### 0.53

This version differs by only a single line from 0.52 and fixes a
critical security flaw. All users of the previous version should upgrade
immediately.

-   Fix bug that let anyone, even an unregistered user change the
    settings for any user.

### 0.52(Minor Bugfix Release)

-   Fix about box error on windows
-   Fix non-cross platform default strftime
-   Should the user enter a bad strftime, revert to the default.
-   Fix error saving uncompressed logs
-   Add mplayer and lm-sensors to acknowledgements

### 0.51(Security Patch Release)

-   Fix very old and very important security bug where kaithem's folders
    in it's var directory were readable by other users.

### 0.5

-   kaithem.time.accuracy() returns an estimate of the max error in the
    current system time in seconds using NTP.
-   Slight performance boost for low-priority events
-   kaithem.misc.errors(f) calls f with no args and returns any
    exceptions that might result.
-   Automatic daily check of mail settings in case someone changed
    things.
-   kaithem.string.formatTimeInterval()
-   When a user logs in, his \[username,ip\] is posted to
    /system/auth/login, or to /auth/user/logout when he logs out.
-   Ability to set default vaules for lattitude and longitude in astro
    functions.
-   When a user logs in, logs out, or fails to log in, his username and
    IP address are posted to /auth/user/loginfail
-   Lots of misc logging
-   (very) Basic versioning support for events, will save your draft in
    case of error, and allows reverting.
-   Auto fall back to tilde version if kaithem.persist.load
    fails(autorecover=false to disable this)
-   One page with syntax errors can no longer crash kaithem at loadtime
-   Support for !time trigger expressions
-   About Page now shows module versions
-   Defaults for precision parameter of kaithem.string methods
-   Default strftime string now only uses portable characters
-   Revert cherrypy to 3.2.3 for users running python 2.
-   Fix error pages on python2
-   Fix python2 inability to create new events
-   Default FPS is 60 instead of 24
-   Fix intermittent error that sliders sometimes raised because write()
    was converting to string
-   Fix documentation on the widget system
-   (partial)Ability to reload the configuration files
-   File manager now sorted
-   New APIWidget allows you to easily interact with the server in
    custom javascript.
-   Onrelease slider widget lets you see what you are doing before you
    let go
-   mplayer backend works even without pulseaudio
-   Document kaithem.registry functions
-   Pause, unpause, and set volume now work correctly in python2
-   JookBawkse module now has better interface, shows now playing in
    realtime, allows rescanning the media library
-   Fix bug where the registry entries were the same object as what you
    set instead of a copy.
-   Fix Bug where some pages were not showing up in the pagelisting even
    if the user had permissions
-   Fix bug where trying to render a widget with write permissions
    crashed if a \_\_guest\_\_ tried

### 0.45 Hotfix 001

-   Fix "changed size during iteration" event bug, Replace outdated
    event scoping documentation.

### 0.45

-   Built in profiling(with yappi)
-   View processes on the server(on linux)
-   Bash Console
-   Upgrade cherrypy version to 3.3.0(Only for python 3)
-   Cleaner toolbar layout
-   Support for MPlayer as an audio backend
-   File Browser
-   Kaithem.persist API for working with files on disk
-   Pause/Unpause/change volume while playing(mplayer only)
-   Fixed lack of HTML escaping on the non-ace event editor
-   Change autoreload interval to 5 seconds for a slight performance
    boost on raspi
-   kaithem.misc.uptime()
-   Modules Library
-   Horizontal Slider Widgets
-   Stop sounds from settings page
-   \_\_default\_\_ pages catch nonexistant pages
-   Fix bash console
-   /system/modules/loaded and /system/modules/unloaded messages
-   New \_\_all\_permissions\_\_ permission that grants every permission
    on the system.
-   kaithem.string.userstrftime and kaithem.string.SIFormat
-   User Settings Page shows a list of what permissions you have

### Version 0.4

-   New AJAX widgets(!)
-   Critical dependancy resolution/initialization bugfix
-   Critical ependancy resolution bugfix
-   Critical bugfix for the error that prevented editing things that
    errored during initialization
-   Minor bugfix: event rate limit displays properly
-   Status bar notifications work with chrome now
-   Ability to disable JS code highlighting per user(for mobile
    browsers)
-   Kaithem Registry
-   Theming Improvements
-   kaithem.time.moonAge() renamed to kaithem.time.moonPhase()