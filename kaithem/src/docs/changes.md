Change Log
----------

### 0.68.42
- :lipstick: Chandler always shows all scenes, no separate "This board" and "All active"
- :sparkles: We now have a separate setup and handler code area for pages.  Inline code will continue to work as before.


### 0.68.41

- :bug: Remove SG1 plugin, the last deployment is gone and there doesn't seem to be much interest in the protocol.
- :sparkles: If the SQLite tag history DB gets corrupted, archive it and start a new one.


### 0.68.40
- :bug: Don't spam notifications from inactive alerts
- :bug: Use nmcli for wifi status instead of outdated dbus
- :bug: Fix settings and theming page not loading



### 0.68.39 Fresh and Free! Closer to 1.0

- :bug: Make it so tag subscribers never fire at all if the timestamp is zero.
- :bug: Suppress unneccesary PIL.Image debug logs
- :sparkles: Support for YoLink devices via the(unencrypted) cloud API
- :lipstick: Devices page much simpler and cleaner
- :lipstick: Devices page has one-click control of smart plugs, bulbs, and YoLink sirens.
- :lipstick: More compact temperature meter widgets
- :coffin: Remove the SculleryMQTT plugin as it was very complex and confusing.  Shared MQTT connections are no longer recommended.
- :coffin: Nuisiance print statement removal
- :coffin: Remove fallback to legacy registry stuff
- :coffin: BREAKING: Completely remove the registry. You will need to update Chandler to the new included version.
- :sparkles: UPnP saved in a file, not the registry
- :coffin: BREAKING: You will need to re-set up UPnP if you were using it
- :coffin: MAJOR: Remove the RAM-based state.  From now on, changes you make to modules and devices are saved to disk immediately.
- :bug: Fix zombie devices staying around after deletion
- :coffin: Deprecate thin wrappers kaithem.time.year() kaithem.time.month() kaithem.time.dayofweek() kaithem.time.\[minute\|second\|hour\]() 
- :coffin: Deprecate thin wrappers kaithem.time.isdst() kaithem.time.day() kaithem.time.accuracy()
- :memo: Sound documentation
- :memo: Announce that kaithem.mqtt will no longer use shared connection optimization at some point in the future
- :sparkles: Ability to go back to the previous version of a page or an event. Only 1 level of history is saved, and only until the server  restarts
- :coffin: BREAKING: Completely remove hardlinep2p/drayer
- :bug: IPv6 localhost glitches


### 0.68.38
- :arrow_up: Update tinytag

### 0.68.37
- :coffin: Schema validation removed from registry as the registry is deprecated anyway
- :coffin: Remove the validictory module, it doesn't work in new python
- :coffin: Remove the DrayerDB plugin as per the Decustomization philosophy
- :sparkles: Use the jsonschema module for config validation


### 0.68.36
- :sparkles: Builtin video downloader does not use the largely incompatible webm
- :sparkles: Chandler supports gradient effects over multiple identical fixtures
- :sparkles: Chandler scenes list for the goto action block has a dropdown.
- :sparkles: Chandler sound file browser has a refresh button

### 0.68.35
- :sparkles: Mixer channels have a mute button
- :sparkles: Simple dark theme


### 0.68.34
- :bug: Fix alarms that reference other tagpoints
- :bug: Fix use of ~ in config file directories
- :bug: Chandler visual bugs
- :bug: Fix chandler shuffle
- :bug: Fix length randomize with sound-relative and wall clock lengths
- :bug: Prevent unscheduled event windup
- :sparkles: Chandler remote media web players
- :sparkles: Pages that are just JS code, ending in .js, are now properly syntax highlighted
- :sparkles: Chandler can respond to keyboards connected directly to the server, with serverkeyup.X events
- :memo: Document the \_\_del\_\_ event cleanup functions
- :sparkles: Chandler scenes menus now show any running cue logic timers for the scene
- :sparkles: Chandler ABCD event buttons gone, replapced by configurable event buttons.
- :sparkles: Chandler display tags: show tag value meters right in the scene overview.
- :sparkles: Chandler cue lengths can accept @5PM style time specifiers, no need to use events and rules
- :sparkles: Chandler no longer displays fractional seconds to reduce visual clutter
- :sparkles: Chandler Commander view 
- :sparkles: Get notified if a widget no longer exists that a page you are on is using.
- :sparkles: Chandler default alpha now 1 by default, goto cue buttons activate scene if not already active.
- :sparkles: Chandler utility scenes don't have buttons or a slider.  Use for embedding camera feeds in the console, and state machine logic.


### 0.68.33
- :bug: Compatibility with older sdmon versions that gave bad JSON
- :bug: Fix illegal character errors that were blocking showing low disk space alerts
- :sparkles: Notifications are now posted to the system notifications, if you have plyer
- :sparkles: NVRChannel autodiscover and list webcams


### 0.68.32
- :fire: Roku ECP device app improved. API breaking.
- :sparkles: Chandler scenes understand Roku commands like VolumeUp and Play
- :sparkles: Better display for readme attribute of devices
- :arrow_up: Update the Monaco editor


### 0.68.31
- :sparkles: Module descriptions on the index page.
- :sparkles: Module descriptions are now Markdown
- :coffin: Broken years-old JookBawkse module removed
- :bug: Un-break  creating new YeelightRGB devices

### 0.68.30
- :bug: Object tags could get in an invalit state and prevent page load
- :bug: Correctly detect NVR failure if snapshotting fails
- :sparkles: Chandler scenes now have a "Command Tag", that allows you to accept shortcut codes from any event tag(Like to Roku Launch button)
- Fewer memory usage and page load count logs
- :sparkles: Chandler scenes now let you view the recent history


### 0.68.29
- :bug: Print less log info and silently drop some records if we are running out of disk space, so as not to worsen the problem by logging it.


### 0.68.28
- :lock: :coffin: Default admin:password credentials have been eliminated. 
- :sparkles: If there are no users, one is created using the login credentials of the Linux user actually running the Kaithem service
- :sparkles: Any user can be set to use the system authentication.  Using Kaithem's weaker internal login is not suggested.
- :fire: The internal auth mechanism may be deprecated or modified eventually. Suggest to always use the Linux system auth instead.
- :bug: Fix bug with changing usernames at the same time as settings
- :bug: UI for setting Chandler scenes now looks better on mobile



### 0.68.27
- :bug: Avoid useless logging client side errors caused by Firefox not supporting idle status at all
- :bug: NVRChannel auto reconnect used to never retry again if the very first attempt was a failure.
- :bug: Avoid rare bug that killed the WS manager thread

### 0.68.26

- :wrench: Temperature warning at 76 degrees
- :wrench: NVRPlugin camera disconnect alarm delay is 90 seconds to reduce false trips
- :bug: :lock: Remove default read/write permissions for devices, they must now be manually added
- :lipstick: Read/write permissions for devices have auto-suggest now

### 0.68.25 "Just Use PipeWire"

This release is all about getting rid of the JACKD manager. Instead, you use an external jack server if you have fancy
mixing. See: https://askubuntu.com/questions/1339765/replacing-pulseaudio-with-pipewire-in-ubuntu-20-04 for info
on switching to PipeWire.  The next EmberOS will have Pipewire running by default already.

- :coffin: Remove ability for kaithem to manage PipeWire or JACK. That should be done by the system.
- :coffin: Remove PulseAudio sharing mode. Use Pipewire, manage it yourself, or just don't use Pulse
- :coffin: JACKD is considered legacy tech and support will be removed as soon as all common Debian platforms easily support PipeWire
- :coffin: Remove ability to manage USB soundcards. Pipewire does that for us!
- :bug: Fix object inferrence on versions of the imaging library
- :bug: Fix downloading modules as ZIP
- :bug: Fix a bug where an old airwire could get GCed and delete a newer wanted audio link
- :bug: Fix Select() not working on some systems in JSONRPYC


### 0.68.24
- :bug: Fix missing platformdirs.version
- :sparkles: NVRChannel discovery for Amcrest cameras, because that's what I've got lying around.
- :monocle_face: Please be aware: Many major CCTV manufactures are rebrands of just a few firms that may be supporting things you may find morally abhorrent.
  
### 0.68.23
- :zap: JSON RPC performance boost with select polling


### 0.68.22
- :sparkles: NVRChannels can now act as open SRT servers
- :sparkles: NVRChannels can play SRT URLs as long as they are h264/AAC in an MPEG-TS codec.
- Boost the no-motion detection interval for spotting sneaky people far away.
- :sparkles: Image frames by Kebinite of OGA
- :sparkles: New CSS class section class=fancy(BG Image by West of OGA)

### 0.68.21 Security Matters!
- :coffin: Remove a lot of dead code
- :coffin: :fire: BREAKING: Remove the entire VirtualResource mechanism. I think it was too complicated to use anyway.
- As a result, getting a Device object will give a Weak Proxy to the device instead of a VirtualResourceInterface.
- REMINDER: When accessing a Device, tagpoint, etc, don't keep a reference to somthing a user could update and replace! 
   access kaithem.devices['foo'] directly rather than making a local reference.
- Tag Points and the Message Bus are the official ways to do loose coupling, and are much simpler.
- :bug: Fix inability to create new device inside a module
- :coffin: Theming, alert tones, and server locations use files in core.settings. Registry data is auto migrated.
- :sparkles: New kaithem.persist.unsaved dict for user-created files to inform the UI of unsaved changes.
- :fire: Announce that the registry will be deprecated eventually.  Modules should attempt to move data to files instead.
- :coffin: Remove mailing list features, as they were very old, unmaintained, and email is a security critical feature.
- :coffin: Remove kaithem.serial.  It was unmaintained and never production-tested, and not used internally here in a very long time.
- :coffin: Remove the restart server option.  On newer systems it would sometimes just stop and not restart.


### 0.68.20
- :lock: SECURITY: Can no longer do certain things in a cross-origin iframe, as extra protection.
- :lock: SECURITY/BREAKING: Now you need a POST request for Chandler's sendevent API
- :lock: :sparkles:SECURITY: User pages show at a glance whether they accept GET
- :bug: Fix inability to assign new user-created permissions to users or pages.
- :sparkles: This file uses GitMoji now! Gitmoji chosen because it is the first Google result.

### 0.68.19
- SECURITY/SEMI-BREAKING: No CORS requests from any other domain allowed as a user, regardless of permissions needed, unless enabled in user settings.
- SECURITY: Fix bug where an attack from my.org could be accepted as matching your domain at my.org.fooo.com
- Fix old code that was looking for YOLOv3.txt

### 0.68.18
- kaithem.web.serveFile streaming response
- SECURITY: Beholder no longer allows unauthorized access to camera snapshots
- Correctly finalize M3U8 files with the end playlist tag
  
### 0.68.17
- Clean up a process leak with the IceFlow servers

### 0.68.16
- Correctly compute width and height of deteted objects

### 0.68.15
- kaithem.web.serveFile now can serve a bytesIO object if mime and filename are provided.
- Object Detection in NVRChannel!!! You just need opencv and tflite_runtime!! Future cleanup may not need opencv
- Fix bug where deleting a tag point logger would not save.
- We use git-lfs now.  If you are missing files it's probably because that isn't set up.

### 0.68.14
- Fix bug where NVRChannel would carry over record sessions and thereby crash and not be able to recover from connection failure
- Improve nvr time search

### 0.68.13
- NVRChannel can now use scipy for way better performance on erosion operations.
- 
### 0.68.12
- NVRChannel can now auto reconnect after a network problem.

### 0.68.11
- Minor tweak to the motion detection algorithm for enhanced resistance to  low level noise.
- Water ripple filter now uses alpha blending for better realism.

### 0.68.10
- BREAKING: NVRPlugin no longer uses a sensitivity value. We have a custom detector and we use a threshold value now
- NVRChannel now reports the raw "level" of motion
- NVRChannel uses a custom motion algorithm that requires Pillow, based on RMS and erosion.
- Retriggering recording in NVRChannel before recording is finished will just append to the active recording
- NVRChannel should no longer crash if you delete a segment dir while it is being written to

### 0.68.9
- Any module page can now be accessed via it's subfolder
- No more H1 header at the top of most pages, to save screen space
- Dropdown panel to keep an eye on notofications from any page
- Manual and motion-activated NVR recording
- Beholder frontend module for a simplified view of the NVR

### 0.68.8

- New Fugit SciFi inspired theme
- NVRPlugin has been rewritten to give low latency streaming over websockets.  It still doesn't have recording, but likely will.
- New unreliable mode for tag points to support this kind of media.
- User telemetry hidden on admin page unless you explicitly press "show"
- Unlogged realtime only telemetry now includes user idle state if permission has been granted, to check on digital signage and kiosks.
- Easier selection of the builtin themes
- Icons switched to the IcoFont for more standardization
- Improve mobile support



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
- There is an Easter Egg hidden somewhere(On it's own page which does not touch any automation features).

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

### 0.67.4
- Fix nuisance bad unit: dB error
- Much better object pool manager for sound players, avoids occasional dropouts
- Fix reused GStreamer proxy IDs that affected RasPi
- Improve performance of JSONRpyc proxies


### 0.67.3
- BluetoothBeacon replaced with EspruinoHub client device that does the same thing with enhanced features.
- Now the DrayerDBPlugin has a very basic browser

### 0.67.2
- Fix Chandler MQTT compatibility

### 0.67.1
- Fix very long sound loop counts
- Fix RTMidi compatibility with new py libs
- Faster boot time with some devices
- SoundFuse algorithm more aggressive

### 0.67.0

- BluetoothBeacon device type lets you watch for the RSSI of an eddystone beacon(python beacontools and permissions required)
- Now we properly support PipeWire(With the JACK use external mode).
- Bluetooth admin page can be used to control pairing from the web UI
- Support Python 3.9

### 0.66.1

- Fix creating new tags via the GUI
- Fix incorrect initial state shown in freeboard
- Fix fade in/out of sounds
- Fix Chandler race condition where stop commands could come before start commands

### 0.66.0

- JackMIDIListener has been removed.  Instead, all connected ALSA midi devices automatically generate tag points for last pressed note and all CC values.
- All connected midi devices now also report to the message bus
- JackFluidSynth plugin now only accepts MIDI on the internal message bus.  
- python-rtmidi is required to use these features.  This is all on account of some unreliable performance and excess complexity with jack midi.
- Chandler can now respond directly to MIDI, no code needed
- Chandler bugfix with smart bulb hue and saturation channels not blending the way you might expect.
- Using a caching strategy we avoid calling ALSA sound card listing functions when not needed to stop occasional bad noises(Much lower JACK latency is possible)
- Chandler Pavillion encrypted protocol sync removed(MQTT alternative coming soon)
- Chandler scene notes now just uses a plain HTTP textarea

- *Major breaking changes*

- The ALSA sound card aliases system has been removed. We no longer support multiple devices except with JACK
- Audio file playback is now done with libmpv.  All other backends are deprecated.   You should have python-mpv on your system!
- This greatly increases audio performance and stability.
- We no longer support a2jmidid or aliases for MIDIs.  Use ALSA midi directly, almost no use cases will need advanced routing.

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

### 0.65.54
- More nuisance errors removed
- Assume that YeeLight bulbs have a good connection until proven otherwise, to avoid alarms. In the future the whole YeeLight module should be refactored.


### 0.65.53
- Workaround for JACK bug on raspberry pi. We always set playback to 2 channels.  This is a minor regression, it will not support the full channel count for surround, and may crash if there is only 1 output channel.  However, the risk of adding more bugs with a more copmplex solution to the audio nightmare, is probably not worth it.
- Fix nuisance selftest error
- Fix nuisiance wifi signal alert
- Remove the WebRTC voice DSP which has not been stable and can segfault.
- Restore support for Python3.7


### 0.65.52
- Even MORE work to be compatible with the odd IPs chrome uses when you use HTTP localhost.

### 0.65.51
- Alarms on =expression tags work properly
- Widget IDs no longer (rarely) generate invalid characters
- Remove some more unused code
- Eliminate confusing content on file resource pages
- Fix some nuisance error messages

### 0.65.50
- /sky/civilTwilight tag fixed

### 0.65.49
- Fix HTTP localhost access when used with IPv6 ::1
- Fix auto-redirect that would sometimes take you to the wrong page after login
- Fix auth cookies not working on localhost(Note: We assume all localhost connections are secure. Don't build a some weird proxy that breaks that assumption.)
- Secure widgets now work correctly via localhost
- Configuring tag point intervals now takes effect immediately
- You can now use an =expression as a tag point fixed config overrride.
- General refactoring and reliability for Tagpoints

### 0.65.48
- Tag point logs sorted correctly

### 0.65.47
- /sky/night tag is 1 when it is currently nighttime at the configured server location.
- /sky/civilTwilight is 1 when it is currently dark at the configured server location
- /system/network/publicIP gets your IP from a public API, or is blank with no connection.  As with all getter-based tags, the request only happens on-demand or if there are tag subscribers.
- More graceful handling if JACK fails to start

### 0.65.46
- Better Mako error formatting
- Tag logging bugfixes
- Fix bugs in configuring exposed tags
- \_\_never\_\_ permission even blocks admins
- Wifi status viewer page is back
- /system/wifiStrength tag point gives the strongest access point connection, 0-100 or -1 for never connected.
cart - Help boxes(paragraph or div class 'help') now show up minimized until you mouse over.
- Clean up Chandler and the widget API to get rid of nuisiance errors
- Basic error telemetry in WidgetAPI enabled pages

### 0.65.45
- Many small improvements to the sounds engine, including true seamless looping
- FreeBoard has been greatly enhanced
- If gmediarender is installed, the DLNARenderAgent plugin accepts media streams from a phone and plays them through the JACK mixer
- YeeLight plugin now uses a StringTag to represent color as hex, because strings are an extremely common solution.

### 0.65.44
- Many small improvements to the sounds engine, including true seamless looping
- FreeBoaard has been greatly enhanced

### 0.65.43
- FreeBoard supports theme creation, uses simpler direct bvalues for widgets, not value,time pairs
- Realtime DRAM bit error detection(I expect one or two hits per year in the 1MB average window we use)

### 0.65.42
- FreeBoard can now autocomplete tag point names
- Fix FreeBoard bugs
- Can now bind native page handlers to subdomains
- Disallow logging in from any subdomain that contains `__nologin__`, sandboxing those pages down to only what a guest can do.

### 0.65.41
- Integrate FreeBoard for no-code dashboard and control interface creation

### 0.65.40
- File resources can now be directly served, using the same URL pattern of pages, with full permissions and XSS
- Unencrypted HTTP access is now allowed for secure pages, from localhost, or from the 200:: and 300:: IP ranges used by the Yggdrasil mesh. 
- Chandler now has separate shuffle and random options
- Chandler has a better combobox for the next cue
- Chandler now supports changing the probability for any random cue
- Fix bug preventing the changing events after an error occurs creating them
- Bring back the error log in addition to the realtime log, on event pages

### 0.65.39
- Fix instant response to Chandler tag point changes, no need to wait for 3s polling.
- Refreshing a tag page after changing something no longer resends the form
- Fix tag point logging with the min accumulator
- SIGUSR1 dumps the state of all threads to /dev/shm/
- Fix bug where continually repeating events could stop if there was a long delay followed by an exception
- SG1 now supports reading and writing the config data area of devices.
- Breaking change:  The MQTT interface between SG1 devies and gateways has changed.  The APIs have not.
- YeeLight RGB bulbs are now supported

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

### 0.65.35
- Fix Chandler tagpoint universe named channel support
- Setting a tagpoint claim now steals the active status from the current active claim, if the priorities are the same.
- Fix editing unreachable Kasa bulbs

### 0.65.34
- Allow creating cues from sound files with odd chars in the names
- Protect against loops in Chandler playing a bazillion sounds and crashing JACK
- Webm sound cues play properly


### 0.65.33
- Mixing board pitch correction/robot voice effect
- Fixes for RTP network audio streaming
- Use soft AND synchronous JACK options
- Segfault resilliance if user enters bad jack settings


### 0.65.32
- BREAKING CHANGE raw ALSA persistant device aliases are now the same as JACK names
- BREAKING CHANGE ALSA "analog" is special case shortened to "anlg" instead of the obvious.
- Allow selecting a specific primary JACK device
- Allow only using the primary JACK device.
- JackFluidSynth included plugin lets you create a synth through the UI without code, and connect to a MIDI keyboard
- Jack mixer RTP Opus send/recieve support
- Jack mixer now suppots recording
- Many more mixer FX, ring mod, amp sim, metronome, noise generator
- Button to play test ding sound through any mixer channel

### 0.65.31
- Pi keypad matrix working on real hardware
- Tag point preconfiguation bugfix
- Better logging for devices

### 0.65.30
- Fix problem going from mock to real GPIO pins
- Examples file no longer messes with GPIO
- Tag point monitoring and alarms for system temperature and battery status
- C and F temperatures shown by default for tagpoint meter widgets.

### 0.65.29
- Fix bad lock ordering in Chandler
- Fix bad param that prevented display of Raspberry Pi undervoltage during boot

### 0.65.28
- Thread pool workers automatic spawning and stopping no longer clogs up the logs(for real)
- Improve devices display page
- Fix MQTT support

### 0.65.27
- Thread pool workers automatic spawning and stopping no longer clogs up the logs
- Improve tag alarm configuration
- Improve front page alert display

### 0.65.26
- Fix JSON MQTT support

### 0.65.25
- Sound volumes above 1 work correctly
- Per-cue fades
- Device print output boxes now have realtime scrolling


### 0.65.24
- Voice recognition moved to a Device
- Fix first alert beep going out default device no matter what
- BareSip virtual softphone device type, support P2P LAN calling.
- SG1 noise floor analysis
- Fix "zombie" devices


### 0.65.23
- Misc fixes
- Beta voice recognition effect in the Mixer(gstreamer1.0-pocketsphinx based)
- Chandler no longer hangs if you accidentally create an infinite loop with rule inheritance
- konva.min.js is now part of the standard JS libs(/static/js/konva4.min.js)
- pixi.min.js is now part of the standard JS libs(/static/js/pixi5.min.js)
- kaithem.gpio inputs now use `pull` not the badly named `pull_up`, but the old version still works
- Now you use CustomDeviceType, not DeviceType, to subclass a device from the web UI
- Eliminate refusal to save if on-disk version is newer, it broke things on RTCless systems
- Fix incorrect splitting of .md resource file header sections
- fix chandler cue delete bug
- Fix message bus logging page stopped working as soon as you went to an invalid topic page
- Beta SG1Gateway device support


### 0.65.22
- Device drivers definable through var/devicedrivers
- Unspecified ports default to jack

### 0.65.21
- Configurable alerts and parameters for tagpoints.
- Much better tagpoint, worker loop, and scheduling performance
- ChandlerScript compatibility with newer versions
- Fix included YAML lib in wrong folder
- Fix kaithem.sound.isPlaying on gstreamer backend
- Fix fluidsynth 2.0 compatibilty.
- Improve sound fading algorithm

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

### 0.65.12
- No longer using system time sync for audio files
- Object inspector can now find referrers for an object

### 0.65.11
- Better sound quality, especially when playing videos

### 0.65.10
- Fix bug that caused it to not boot up on new installs
- Chandler logic editor defaults autofilled

### 0.65.9
- Chandler cues sound fadeout and crossfade
- Minor refactoring

### 0.65.8
- Chandler UX improvements
- Synchronous messages
- Chandler edge triggered poll events

### 0.65.7
- Fix not waiting long enough to see if events have errors
- Tagpoint Filter/Soft Tags API
- Tagpoint.poll() function
- Save Jack mixer data as YAML, one file per preset


### 0.65.6
- Fix widgets on unencrypted connections

### 0.65.5
- Move some core functionality to the unit testable scullery library
- Add missing msgpack js file

### 0.65.4
- Enttec open DMX support(Any cheap FTDI DMX adapter)
- Properly show changed alpha vals on server
- Reduce lagginess with fast changing chandler cues
- Better error reporting for functions that run in the background
- A few builtin Chandler fixtures
- Versionable saving for chandler fixtures, universes, and assignments
- Uploadable chandler setup and fixture library files

### 0.65.3
- Gstreamer audio backend resource leak and segfault fix
- Restore lost chandler MQTT features
- Chandler lighting value rendering buxfixes

### 0.65.2
- Chandler soundfile listing bugfix
- Chandler sound prefetch
- Various merge-related fixes

### 0.65.1
- Prevent tagpoint widget send from blocking up the process
- New StringTag objects, like tagpoints but for strings
- Chandler Scene alpha and current cue are now exposed as read/writable tagpoints
- Properly handle resource-timestamps
- BREAKING: Message topics now work more like MQTT topics. They have to end with # if you want all subtopics(+ is not supported)
- Gstreamer based audio playback is now the default
- =expression based polled ChandlerScript events(Dynamically eveluated when needed)
- Chandler tagValue(tagName) function
- Chandler setTag(name,value, priority) command to set tags and stringtags 
- Semi-breaking: File resources are stored in __filedata__ and managed immediately, not on system state save. They are no longer atomic.
- Messagebus timestamp and annotation
- MQTT support via eclipse paho
- Jack mixer fader tagpoints
- Fix gpio output ignoring pre-existing tagpoints

### 0.65.0
- Fix the emedded file resources
- Warning on missing file resources
- Nicer formatting for zip downloads(Backwards compatible but new zips don't work in old kaithem)

### 0.64.9
- Add automationhat to the included libraries(In lowpriority)
- Fix the link to the tagpoint documentation

### 0.64.8
- Fix "Bad record mac" nuisiance errors by making widgets properly threadsafe
- Autoscroll in Chandler event log
- Fix bug where persist module could create folder with same name as file you wanted to save
- Chandler sends events in background thread to avoind blocking rendering
- Send only the necessary chandler metadata on every cue change

### 0.64.7
- Chandler proper traceback support in cue logic
- Chandler scenes don't auto-stop at zero alpha anymore
- Stopping chandler scenes clears all variables and returns to the default cue on restart
- Event value accessible in cue logic as event.value, event.millis,event.time, and event.name
- Disable JACK dbus audio reservation

### 0.64.6
- Full tracebacks in thread status page
- Set time from web UI
- Fix lockup bug with chandler enttec backend

### 0.64.5
- Fix display of timers in the chandler UI
- Option to inherit chandler rules from another cue

### 0.64.4
- Fix bugs in the WiFi manager page(Required changing NetworkManager python bindings)

### 0.64.3
- Fix bugs in the GPIO mocking functions


### 0.64.2
- Misc fixes
- Fix environment variable bug when launching JACK
- Fix possible schedule pileup bug with repeatingevents
- New theme
- Chandler accepts sound files from config


### 0.64.1
- Misc fixes
- Chandler logic editor, visual language for creating vue logic
- Chandler Page editor, every scene can have an associated page
- Chandler tracking and backtracking cues now function correctly
- Devices page a little more polished

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
- WiFi Manager, on Linux with NetworkManager you can set up connections to access points via
  the web UI.
- `__del__` support in events, just define it in the setup.
- kaithem.midi.FluidSynth lets you play MIDI notes with soundfonts
- One-param and zero-param messagebus subscriptions that don't get the topic(Two param stil works)
- gpiozero integration
- Util page for viewing environment variables
- Lightboard scenes are now saved to VARDIR/chandler/scenes/SCENENAME.yaml
- Functions can now be used as StateMachine rules, they are polled and followed when true
- Use Ace code editor as fallback on mobile
- Lightboard has been renamed to Chandler
- Add a bit of runtime type checking

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
