Change Log
----------

### 0.86.2

This release is all about ES modules. I've decided to pretty much completely
move on from non-module JS, and as kaithem is not yet 1.0, this will be a hard breaking change that affects most custom JS, requiring minor(a few lines) changes.

It does not affect anything not using custom HTML/JS

- :technologist: Dependabot and the general ecosystem have spoken. No more dev branch, we're not using Gitflow.
- :technologist: 80 line limit.
- :bug: Fix bug where the loop sound feature interacted badly with relative length
- :sparkles: Widget API will no longer send old failed messages on reconnected after 5 seconds
- :bug: Fix nuisance gitgub flavor not found error
- :sparkles: Chandler logic lets you use `=+ tv("TagName")` to trigger when a tag changes to a nonzero value.
- :sparkles: Improve chandler autocomplete suggestions
- :lipstick: Alerts more visible on devices pages
- :bug: Delete button on devices page works correctly
- :sparkles: Switch to https://reallyfreegeoip.org for the one time location lookup
- :sparkles: kaithem.api.web.render_html_file function for fully client side apps
- :sparkles: When setting a @time length, give a popup so you can tell if it was parsed correctly
- :sparkles: At boot, logs changes in the environment like installed system packages.
- :lipstick: Make cue notes more visible
- :lipstick: Less log clouter for notifications
- :sparkles: ArduinoCogs support improved.
- :bug: i/o error checker stalling bug

#### :boom: BREAKING

widget.mjs along with several other internals are now esm modules.
Normal non-esm JS is deprecated or legacy pretty much everywhere.

If you're doing custom JS/Python work with an APIWidget, you'll need to
give the APIWidget a widget ID, or fetch the generated one from widget.id,
and import it's special API script:

```html
<script type="module">
   import { kaithemapi, APIWidget} from "/static/js/widget.mjs"
    let api = new APIWidget("widget_id")
    api.upd = (val) => alert(val)
    api.send("MyValue")
</script>
```

Use:
```js
import { kaithemapi } from "/static/js/widget.mjs"
```
if you need to access the widget API directly.


### 0.86.1

- :bug: Minor UI stuff with displaying unsupported devices
- :sparkles:  Add experimental support for the ArduinoCogs web API, which is still pre-alpha.

### 0.86.0

This release took a while, because so many tests had to be rewritten for the Popover API based UI.
Chandler should be much nicer to use now, especially on Mobile!

#### Added
- :sparkles: Cue provider system lets you quickly create playists from folders of media
- :sparkles: Mount/Unmount disks from devices page
- :sparkles: Add the module_lock key to the module's \_\_metadata\_\_.yaml to protect from changes via GUI.
- :sparkles: Popover-based UI overhaul for Chandler.

### 0.85.0


#### Removed

- :coffin: control and \_\_variables\_\_ chandler universes
- :coffin: Tab to space option: Spaces are always used
- :coffin: Screen rotate setting that didn't work on Wayland
- :coffin: The alert sounds system has been removed. It is suggested to use an automation rule on /sys/alerts.level.
- :coffin: The setting for universe channel count. Ther're just always max size now.
- :coffin: Most of the integrated self tests removed. Hardware related tests are staying.
- :coffin: RTP features in the Mixing Board.  They will return at some point asa separate feature outside the FX chain.

#### Added

- :sparkles: Can now set a label image for a cue
- :sparkles: Presets named foo@fixture are only usable for that fixture or fixture type.
- :sparkles: Improved preset picker UI
- :sparkles: Can set images for presets
- :sparkles: Preset and cue images specified as 16/9
- :sparkles: File server resources are browsable
- :sparkles: File resource thumbnails
- :sparkles: File resource audio previews
- :sparkles: Excalidraw integration to draw labels and add documentation to modules
- :sparkles: Excalidraw labeling for presets, resources, fixtures, cues, and mixer channels
- :sparkles: Retire the original error.ogg file.  alert.ogg and error.ogg are now aliases for new files.
- :sparkles: All the core web UI sounds are available in chandler
- :sparkles: New "Enable Default Alerts" option to disable all the alerts a device sets.
- :sparkles: Compact view for chandler cues


#### Changed

- :boom: Chandler "Scenes" have been renamed to "Groups" to disambiguate from "Cues" and follow stage lighting practice.  This should not be a breaking change, anything user facing gets migrated automatically.

- :boom: Chandler GotoCue commands no longer stop execution of the current event.
- :boom: Chandler GotoCue, shortcut, and event happens in the next frame
- :boom: Tag points and the message bus use system time, not monotonic.
- :boom: Tag points under /jackmixer/ renamed to just mixer

#### Fixed

- :bug: Fix setting media folders
- :bug: Fix beholder media playback and other things using subfolders of user pages
- :bug: Fix OPZ DMX Definition import
- :bug: Fix incorrect fixture type mouseover display
- :bug: Fix deleting file resources
- :bug: Fix get file resource path API
- :bug: Fix coarse/fine channels
- :bug: Use a cache busting value in urls so the browser knows to refresh
- :bug: Fix countdown timers with unusual bpm values
- :bug: Fix digital signage permission issue
- :bug: Fix digital signage unable to start midway through media
- :bug: Fix delete button in file manager
- :bug: Fix Vary blend mode
- :bug: Fix Flicker blend mode performance
- :bug: Fix editing blend mode params
- :bug: Tag point universes always update on cue even if not changed
- :bug: Fix bug where a fade in the middle of another fade could be a sudden jump
- :bug: Fix cue and group autocomplete in script editor
- :bug: Mixer sends work
- :bug: Fix recurring time selectors being a few seconds off


### 0.84.0b2

#### Added

- :sparkles: More YoLink devices

#### Fixed

- :bug: Updated icemedia version fixes thread leak
- :bug: Fix import resource from yaml
- :bug: Sunrise and sunset times should be fixed
- :bug: Require confirm checkbox was showing incorrect value
- :bug: Missing file for lair.css theme
- :bug: Fixture values were not applied on boot until the first cue transition
- :bug: Fix issue where all black frames could get inserted in DMX output
- :bug: Improve the UI for the fxture assignments setup
- :bug: Fix fading from a cue that has a fixture to a non-tracking one that doesn't
- :bug: Fix inability to access manage page for subdevices

#### Changed

- :boom: Use pyephem instead of astral due to this [issue](https://github.com/sffjunkie/astral/issues/7)

#### Removed

- :coffin: Rahu calculations removed due to switching libraries


Internally, the separate "affect" variabl used in lighting rendering has been refactored away.


### 0.84.0b1

#### Added
- :coffin: Fileserver resource types allow you to serve a directory of files as if it were at /pages/module/resourcename.  This replaces the old individual file permissions.

- :sparkles: Lots of testing!
- :sparkles: Now available on pypi!

#### Removed

- :coffin: Web console removed due to lack of ASGI but may return later
- :coffin: BREAKING. The internal fileref system.  Instead, files in modules are just simple files under \_\_filedata\_\_


#### Changed

- :sparkles: Move to the quart framework instead of cherrypy. Everything is fully ASGI based.
- :boom: Logging out just logs out your client, not all clients on that user
- :sparkles: Most loggers moved to \_\_name\_\_ instead of system
- :boom: Tag point name normalization replaces x\[foo\] with x.foo for consistency.

#### Fixed

- :bug: Fix page XSS options
- :bug: Fix mixer level meters in new channels not immediately responding till you refresh the page
- :bug: Fix very old bug where widget messages could be one message behind if sent rapidly, and the newest wouldn't be sent till something else triggered send. Chandler sliders should be much smoother.
- :bug: Fix ancient race condition where widgets would subscribe before page load, and then the onpageload data happened before there was anything to recieve it.
- :bug: Fix MIDI integration

```
┏━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━━━━━┳━━━━━━┓
┃ Language      ┃ Files ┃     % ┃  Code ┃    % ┃ Comment ┃    % ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━━━━╇━━━━━━┩
│ Python        │   127 │  32.5 │ 21987 │ 62.7 │    3809 │ 10.9 │
│ HTML          │    53 │  13.6 │  4992 │ 75.0 │      89 │  1.3 │
│ RHTML         │    58 │  14.8 │  4910 │ 74.4 │      25 │  0.4 │
│ Markdown      │    33 │   8.4 │  4084 │ 68.1 │      19 │  0.3 │
│ CSS           │    14 │   3.6 │  2578 │ 57.0 │     222 │  4.9 │
│ JavaScript    │     6 │   1.5 │  1399 │ 51.8 │     141 │  5.2 │
│ YAML          │    11 │   2.8 │   822 │ 74.8 │      81 │  7.4 │
│ Text only     │     1 │   0.3 │   109 │ 90.1 │       0 │  0.0 │
│ Bash          │     1 │   0.3 │    72 │ 59.0 │      25 │ 20.5 │
│ JSON          │     1 │   0.3 │     4 │ 57.1 │       0 │  0.0 │
│ __unknown__   │    18 │   4.6 │     0 │  0.0 │       0 │  0.0 │
│ __empty__     │     1 │   0.3 │     0 │  0.0 │       0 │  0.0 │
│ __duplicate__ │    11 │   2.8 │     0 │  0.0 │       0 │  0.0 │
│ __binary__    │    56 │  14.3 │     0 │  0.0 │       0 │  0.0 │
├───────────────┼───────┼───────┼───────┼──────┼─────────┼──────┤
│ Sum           │   391 │ 100.0 │ 40957 │ 65.2 │    4411 │  7.0 │
└───────────────┴───────┴───────┴───────┴──────┴─────────┴──────┘
```

Tests

```
┏━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━━━━┳━━━━━━┓
┃ Language   ┃ Files ┃     % ┃ Code ┃    % ┃ Comment ┃    % ┃
┡━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━━━━╇━━━━━━┩
│ Python     │    10 │  38.5 │  689 │ 49.6 │     172 │ 12.4 │
│ TypeScript │    15 │  57.7 │  662 │ 63.3 │     118 │ 11.3 │
│ __empty__  │     1 │   3.8 │    0 │  0.0 │       0 │  0.0 │
├────────────┼───────┼───────┼──────┼──────┼─────────┼──────┤
│ Sum        │    26 │ 100.0 │ 1351 │ 55.5 │     290 │ 11.9 │
└────────────┴───────┴───────┴──────┴──────┴─────────┴──────┘
```

### 0.83.0

Barring unforseen events, this will be the last release using
CherryPy and Tornado.  Any APIs that reference them are deprecated.

Future versions will use Quart and will be fully ASGI-based.

#### Fixed

- :bug: Bring back displaying errors on page editing UI
- :bug: Fix moving a page resource
- :bug: Static .vue files served with bad MIME type breaking tests
- :bug: Guard against module or resource starting with /
- :bug: Fix hashing new modules
- :bug: :security: User page permissions were being removed on re-save.
- :bug: :security: Because of this, please update to the new version of the Beholder module


#### Changed

- :boom: Schema for tag history changed for daasette compatibility.
- :lipstick: LoC count excludes tests.

#### Removed

- :coffin: Experimental sqlite browser that didn't get much interest.
- :coffin: yt-dlp integration removed.
- :coffin: Monitor scenes removed

#### Added

- :sparkles: Usable RTP Opus listener to stream over network.
- :sparkles: kaithem.api.web.add_asgi_app
- :sparkles: e2e tests with [Playwright](https://playwright.dev/docs/intro)
- :sparkles: Colorful log output with structlog

#### Dev Info

New pytest tests: 1
New Playwright tests: 4

```
┏━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━━━━━┳━━━━━━┓
┃ Language      ┃ Files ┃     % ┃  Code ┃    % ┃ Comment ┃    % ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━━━━╇━━━━━━┩
│ Python        │   118 │  29.8 │ 21947 │ 62.6 │    3870 │ 11.0 │
│ HTML          │    54 │  13.6 │  5225 │ 74.4 │     141 │  2.0 │
│ RHTML         │    61 │  15.4 │  5036 │ 74.4 │      27 │  0.4 │
│ Markdown      │    33 │   8.3 │  4060 │ 69.0 │      19 │  0.3 │
│ CSS           │    14 │   3.5 │  2578 │ 57.0 │     222 │  4.9 │
│ JavaScript    │     6 │   1.5 │  1406 │ 51.8 │     143 │  5.3 │
│ YAML          │    11 │   2.8 │   822 │ 74.7 │      83 │  7.5 │
│ Bash          │    12 │   3.0 │   328 │ 29.2 │     147 │ 13.1 │
│ Text only     │     1 │   0.3 │   109 │ 90.1 │       0 │  0.0 │
│ JSON          │     1 │   0.3 │     4 │ 57.1 │       0 │  0.0 │
│ __unknown__   │    18 │   4.5 │     0 │  0.0 │       0 │  0.0 │
│ __empty__     │     1 │   0.3 │     0 │  0.0 │       0 │  0.0 │
│ __duplicate__ │    10 │   2.5 │     0 │  0.0 │       0 │  0.0 │
│ __binary__    │    56 │  14.1 │     0 │  0.0 │       0 │  0.0 │
├───────────────┼───────┼───────┼───────┼──────┼─────────┼──────┤
│ Sum           │   396 │ 100.0 │ 41515 │ 64.5 │    4652 │  7.2 │
└───────────────┴───────┴───────┴───────┴──────┴─────────┴──────┘
```

### 0.82.0

This release brings compatibility with Python 3.12 and Ubuntu 24.04

#### Fixed

- :sparkles: Jinja2 bytecode cache gives a very extreme speedup to certain page lodad
- :sparkles: Minor visual glitches
- :bug: Fix deleting motion detection regions
- :bug: Object tags didn't disply right
- :bug: Module search pages
- :bug: Certain custom resource types could not be created in folders.
- :bug: Page editor robustness against missing keys
- :bug: Dashboard correctly shows the default value even if it hasn't been set yet.
- :bug: Message log page

#### Changed

- :sparkles: -d now sets the kaithem data dir, -c removed.  config.yaml now always in root of dir.
- :sparkles: Module hashes use a different algorithm, the BIP0039 wordlist, and base32 instead of hex for display.
- :sparkles: Use Argon2id for user passwords.
- :sparkles: Use [niquests](https://pypi.org/project/niquests/) instead of requests.

- :sparkles: NVRChannel uses cv2.dnn for Py3.12 compatibility.

#### Added

- :sparkles: Chandler "shell" command lets you run stuff in the system shell. Use with care!
- :sparkles: `make dev-count-lines` command to roughly track codebase changes.
- :sparkles: Leaving the chandler editor page triggers autosave if there were changes.

#### Removed

- :coffin: Video filters removed from Beholder
- :coffin: The module[resource] APIs are removed. Use kaithem.api.modules instead.

#### Line Counts

(Note, pygount doesn't detect languages perfectly, the HTML is atually only Mako and Jinja2)
```
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━┳━━━━━━┓
┃ Language               ┃ Files ┃     % ┃  Code ┃     % ┃ Comment ┃    % ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━╇━━━━━━┩
│ Python                 │   122 │  29.4 │ 22517 │  62.1 │    3993 │ 11.0 │
│ RHTML                  │    62 │  14.9 │  5078 │  74.4 │      27 │  0.4 │
│ Markdown               │    33 │   8.0 │  4040 │  69.4 │      19 │  0.3 │
│ CSS+Lasso              │    17 │   4.1 │  3115 │  56.5 │     268 │  4.9 │
│ HTML+Django/Jinja      │    18 │   4.3 │  1997 │  77.3 │      24 │  0.9 │
│ HTML+Genshi            │    13 │   3.1 │  1843 │  69.1 │      62 │  2.3 │
│ HTML                   │    23 │   5.5 │  1387 │  77.9 │      55 │  3.1 │
│ JavaScript+Genshi Text │     3 │   0.7 │  1078 │  50.2 │     134 │  6.2 │
│ YAML                   │    11 │   2.7 │   822 │  74.7 │      83 │  7.5 │
│ Bash                   │    12 │   2.9 │   328 │  29.2 │     147 │ 13.1 │
│ JavaScript             │     2 │   0.5 │   300 │  56.3 │       8 │  1.5 │
│ Text only              │     1 │   0.2 │   109 │  90.1 │       0 │  0.0 │
│ JavaScript+Ruby        │     1 │   0.2 │     8 │ 100.0 │       0 │  0.0 │
│ JSON                   │     1 │   0.2 │     4 │  57.1 │       0 │  0.0 │
│ __unknown__            │    18 │   4.3 │     0 │   0.0 │       0 │  0.0 │
│ __empty__              │     1 │   0.2 │     0 │   0.0 │       0 │  0.0 │
│ __duplicate__          │    12 │   2.9 │     0 │   0.0 │       0 │  0.0 │
│ __binary__             │    65 │  15.7 │     0 │   0.0 │       0 │  0.0 │
├────────────────────────┼───────┼───────┼───────┼───────┼─────────┼──────┤
│ Sum                    │   415 │ 100.0 │ 42626 │  64.1 │    4820 │  7.3 │
└────────────────────────┴───────┴───────┴───────┴───────┴─────────┴──────┘
```

### 0.81.0

#### Changed

- :lock: New enumerate_endpoints permission required for things that could otherwise reveal the existance or nonexistance of an object without actually giving access to it.

#### Removed

- :coffin: Most widgets other than DataSource and APIWidget are finally gone.  That was decade old unmaintained code, one of the last remaining bits of antigue code.

#### Added

- :sparkles: The [picodash](https://github.com/EternityForest/picodash) system replaces widgets with a much easier to use set of custom HTML elements. Documentation coming soon!
- :sparkles: Nicer error pages
- :hammer: Unit testing for the YAML upload/download, which used to be buggy.

#### Fixed

- :bug: Certain commands in chandler like sending a ding to a web player.
- :bug: Up/Dowload modules.


### 0.80.1 (Apr 27)

#### Fixed

- :bug: Even more sneaky camelcase and tag name normalization bugs!

#### Added

- :sparkles: LED element for chandler tag display.

### 0.80.0 (Apr 24)

Another breaking change heavy beta release.  You can now have multiple Chandler boards
and JACK mixers.

The good news is that there are now no more major globally-configured objects,
which was the main issue with these breaking changes.

#### Removed

- :coffin: Remove ability to create new Mako user pages. Jinja2 all the way!
- :coffin: Tag point universes are gone
- :coffin: Remove non-chandler simple video signage
- :coffin: Special characters no longer allowed in resource names.

#### Fixed
- :bug: Fix loading event after external formatter messes with it.

#### Added
- :sparkles: Checkpoint cues. When a Chandler scene starts, it goes to the last cue it was in with the checkpoint flag.  The checkpoints are saved to disk as soon as you enter.

- :sparkles: \_\_setup\_\_ cues. Chandler scenes go to this cue if it exists at start before going to any checkpoint.

- :sparkles: Button to add time to a running cue
- :sparkles: Print more logs
- :sparkles: Now you can add tag points directly to a scene as a value.
- :sparkles: Any module in your ~/kaithem/plugins folder will be imported at early
            boot.  This is part of the ongoing effort to enable creating content
            outside the web UI.

- :sparkles: Configurable tag points are back! This time much simpler, as a resource plugin.
- :sparkles: Config files, resource top level keys, and tag points snake_case, enforced by auto conversion.


- :sparkles: :boom: Chandler boards and audio mixers are resources now. There's no global, and you can have multiple.  Universes are global so that boards can share DMX interfaces, but resources are not.

#### Dev
- :hammer: Pages and Events moved to core plugin(Code refactor, no change for end users)


### 0.79.0

Development is advanced enough on the new overhaul that it makes sense
to start using the [GitFlow](https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow) methodology.


- :coffin: Mako user pages are deprecated and will be removed
- :coffin: The `kaithem` object will likely be removed eventually. Replace with importable `kaithem.api` when in catches up on features.

- :coffin: :boom: Remove ALL web tag configurability.


Since this was a core feature, it will be back.  But it was one of the worst parts of the codebase AND had bad UX,  it was very much in need of a full rewrite.

For now it is not possible to set or override alerts.  I normally *hate* rewrites, but believe this is really needed.  You can create loggers already, they are their own separate resource type.

Tags, in newer editions, should have a single source of config, and the code for config should be separate from tag internals.

- :coffin: :boom: Remove freeboard.
  It was a good run, but I'd rather focus on core code quality than maintain the customized fork, which in itself had become bloated.  Similar functionality may come back, but really, Chandler handles those use cases.

- :sparkles: Switch from typeguard to Beartype.
- :sparkles: More unit testing
- :sparkles: Loggers are now a resource type that lives in modules, separate from tags.

- :coffin: Remove more old files
- :coffin: Remove all references to custom `recur` library, use more standard dateutil+recurrent
- :sparkles: \_\_schedule\_\_ special cue skips ahead through a chain of cues with @time lengths, to the one matching the current time best.
- :bug: fix broken shuffle:* special cue
- :coffin: Must explicity specify a type for all display tags

- :lipstick: Move help to inside the tools page
- :hammer: Many features moved to included core plugins, but still work exactly as before.

- :bug: Fix module import/export
- :bug: Fix back button taking user to old version of event

### 0.78.1

This is mostly just about the install scripts and a few leftover bugs.  A lot has changed on Pi OS with Wayland!

There was a huge amount of old stuff to clean up, but now that so much of the custom and unusual code is gone, I expect future versions to be much more reliable, compatible,
and easier to maintain.


 - :bug: Fix broken @time lengths in chandler
 - :bug: Fix short web media files endless looping
 - :hammer: unit testing
 - :sparkles: Don't run integrated selftest when running unit tests
 - :coffin: Remove the sdmon cache service from linux-tweaks.sh,   integrate that feature instead.
 - :coffin: Don't intercept sound for the chrome kiosk
 - :sparkles: Move linux package cleanup util to new uninstall-bloatware.sh script
 - :sparkles: Move installing utilities to new install-utilities.sh script

 - :bug: Fix various helper script compatibility issues.
 - :bug: Restore world maps and web console that the new linter accidentally broke...
 - :bug: Fix external modules being loaded with wrong name
 - :bug: Icemedia 0.1.12, works correctly in venv on pi
 - :bug: The tmpfs on /tmp was too small to run pipx reliably.
 - :bug: Fix some kind of dependency conflict with attr

#### Tested on
OS: Debian GNU/Linux 12 (bookworm) aarch64
Host: Raspberry Pi 4 Model B Rev 1.2

OS: Ubuntu 22.04.3 LTS x86_6


### 0.78.0

This is another pretty heavy breaking change release.  Nearly every file has been touched.


I was not going to release this so early. There may be bugs. YMMV.
Consider it early alpha.  However, it does seem to work just fine.

However I discovered that the old installer was unreliably due to
some kind of virtualenv behavior where it decides to randomly use
/venv/local/bin instead of /venv/bin.

To fix this, we are moving to pipx and Poetry, eliminating almost all the custom
installation related code.

To do so I had to get rid of --system-site-packages
completely.   This change broke gstreamer, but there is a fix!

Thanks :heart: to [happyleavesaoc](https://github.com/happyleavesaoc/gstreamer-player/) for discovering
a way to make gstreamer work in a virtualenv. All you need to do is symlink the gi package
into your site-packages!  Kaithem now does this automatically on Debian and probably most everything
else.

In an unrelated bit of news, I discovered that a huge number of things were not loading due to
https://github.com/python/cpython/issues/91216.  Kaithem now contains a workaround for it in tweaks.py.
and can load things affected by the bug.


- :bug: Fix unused subdevice nuisance method resolution error
- :coffin::boom: Remove old baresip code
- :coffin::boom: Remove kaithem.midi API
- :coffin::boom: Remove the image map creator util
- :coffin::boom: Remove kaithem.time.accuracy, lantime, hour, month, day, second, minute, dayofweek
- :coffin::boom: Remove kaithem.sys.shellex, shellexbg, which
- :coffin::boom: Remove kaithem.events.when and kaithem.events.after
- :coffin: Remove nixos config that was probably outdated. It's in the log if ya need it!
- :boom:  Default storage dir is now ~/kaithem no matter how you install it

- :hammer: Split off the sound stuff in a separate libary [IceMedia](https://github.com/EternityForest/icemedia) meant for easy standalone use.

- :hammer: Split off internal scheduling and state machines to [Scullery](https://github.com/EternityForest/scullery) meant for easy standalone use.
- :hammer: Move to pyproject.toml
- :hammer: Move to a pipx based install process
- :recycle: A very large amount of old code is gone
- :recycle: Start moving to a proper dialog generation class instead of ad-hoc templates.s
- :lipstick: Add badges(CC0 licensed)
- :lipstick: Slim down the readme


### 0.77.0

This release was going to be a simple polish and bugfix.... However, I discovered some
subtle bugs related to a legacy feature, and this turned into a pretty big cleanup effort in some older code, removing several old features.

While this release should be ready and usable,
and has been tested, you should use it with caution just due to the scope of changes involved.

Previously you could save device config both in
modules and a global devices list.  That and several other aspects of device config were
causing lots of user and implementation complexity.

Now you can only save them in modules. Keeping them in modules lets you use the import/export features and is much more powerful. You can still load legacy devices until the next version.  Please make a module and move your devices there, you can set where to save a device on the device page.


- :bug: Restore the broken optimization for events that don't need to poll
- :bug: Fix fixture types window being too small
- :bug: Fix nuisance error when deleting mixer channel
- :bug: Fix enttec open atapter showing as disconnected when it wasn't
- :bug: Fix unsupported device warnings feature
- :bug: Displayed value in UI correctly updates for refresh button
- :bug: Fix devices UI setting bad value when you specified 'false'
- :bug: Remove caching on modules listing that was casuing issues.
- :bug: Notification handler code was spawning tons of threads bogging everything down.

- :lipstick: Better combo box feel
- :lipstick: Icons switched to [MDI Icons](https://pictogrammers.com/library/mdi/) for harmony with other automation platforms.
- :lipstick: More compact strftime default


- :coffin: Remove the complicated and never-used system for creatig device types in events
- :coffin: Remove the legacy device type system and all the devices from before iot_devices.  All were unmaintained and some may have been broken by hardware vendors.
- :coffin: Remove the input and output binding feature of devices.  Chandler can do everything it could, and it was not a clean separation of device and logic.
- :coffin: Remove the bluetooth admin panel. Try [bluetuith](https://darkhz.github.io/bluetuith/)!
- :coffin: Remove some old junk files
- :coffin: kaithem.gpio is gone. Use the GPIO devices in the device manager for this purpose.
- :sparkles: BREAKING: The name of a device stored in a module is independet of module name or folder
- :sparkles: BREAKING: / now used to separate subdevice names
- :sparkles: BREAKING: Device config dirs now end with .config.d, automatic migration is impossible, however nothing except the DemoDevice uses conf dirs.
- :sparkles: BREAKING: It is no longer possible to save devices outside modules. Please migrate all devices to a module(Legacy devices still load, they just can only be saved into modules.)

- :hammer: Use pre-commit


Specific devices removed:

- BareSIP
- Kasa
- Sainsmart Relay boards
- RasPi Keypad
- JACK Fluidsynth
- Espruinio

Some may return in iot_devices later.

### 0.77.0 Beta

- :bug: Autosave did not save deletions, only changes
- :bug: Fix chandler slide overlay refreshing over and over
- :bug: Chandler missing fixtures info in UI until you modify something
- :bug: Fix some media files unable to be served to the web player
- :bug: Cues now reentrant by default again
- :bug: Fix fade in not displayed after loading
- :bug: Fix sound fade in for non-web audio
- :bug: Fix sound "windup"
- :bug: Chandler and mixer state could get out of sync if the websocket disconnected and reconnected
- :sparkles: Move universe and fixture setup to a separate chandler setup page
- :sparkles: Can now rename cues
- :bug: Fix web player not starting at the right time after needing manual click to start
- :sparkles: Can now customize the HTML for the scene web player
- :sparkles: Chandler cues can now have Markdown text content to show in the slideshow sidebar
- :sparkles: User settings are instant, no more manual save step
- :sparkles: Cues inherit rules from the special \_\_rules\_\_ cue if it exists.
- :sparkles: If sound_fade_in is 0, then use the cue lighting fade for the sound as well if it exists
- :coffin: nosecurity command line flag removed
- :sparkles: Permissions have been consolidated.
- :sparkles: Chandler has consoleNotification command to send a message to the dashboard
- :bug: Fix bug where scene timers would mess up and repeatedly fire


### 0.76.1

- :bug: Critical Bug: Fix chandler universes not being saved correctly


### 0.76.0

- :bug: Fix utility scene checkbox in chandler not showing correct value
- :bug: Fix Chandler relative length with web slides
- :bug: Fix iot_devices not setting the default
- :bug: Fix shortcut code normalization(10.0 is treated same as 10)
- :bug: Upload new chandler scene adds to rather than replaces the existing scenes
- :bug: Fix broken highlighting in some themes
- :bug: Fix support for midi devices with odd chars in the names
- :sparkles: Can hide a scene in runtime mode
- :sparkles: Chandler can now import and export audio cues in a scene as M3U playlists(With fuzzy search for broken paths!)
- :sparkles: Confirm before delete cues
- :sparkles: Add ability to move Chandler rules around
- :sparkles: Scene display tags can now be inputs
- :sparkles: Don't log thread start/stop if they have generic Thread-xx names
- :sparkles: Chandler updated to work with Vue3
- :sparkles: Chandler has autosave(10min)
- :sparkles: Chandler save setup and save scenes buttons now just one save button.
- :sparkles: Chandler has a proper loading animation
- :coffin: Raw cue data text view has been removed


### 0.75.1

- :bug: Fix chandler scenes sometimes sharing all data for the default cues
- :bug: Fix makefile install process
- :bug: More reliable max-volume-at-boot script
- :sparkles: Web console runs in ~/kaithem/venv if it exists(Change this if desired in kaithem's bashrc)
- :sparkles: Settings page link to set ALSA mixer volume to full

### 0.75.0

- :sparkles: Default page title is now the hostname
- :sparkles: Devices report feature lets you print out all the device settings
- :bug: Nuisance gstreamer output
- :bug: esphome api key correctly marked as secret
- :sparkles: Improve maps quality
- :sparkles: Chandler shows time at which each scene entered the current cue

### 0.74.0

- :sparkles: Use Terminado and xterm.js to finally provide a proper system console shell!!!
- :bug: Fix recursion issue in device.handle_error
- :bug: Fix chatty logs from aioesphomeapi
- :coffin: Deprecate kaithem.web.controllers
- :sparkles: kaithem.web.add_wsgi_app and add_tornado_app to allow for addon apps from other frameworks.
- :lipstick: Legacy /static/widget.mjs moved to /static/js/widget.mjs
- :lipstick: Third party JS moved to /static/js/thirdparty/
- :sparkles: Support AppRise notifications(Configure them in global settings)


### 0.73.2

- :bug: Fix crackling audio on some systems by using the system suggested PipeWire quantum

### 0.73.1

- :bug: Fix chandler not liking cues with empty strings for some settings
- :bug: Fix incredibly dumb bug where I forgot that isinstance doesn't consider int  subtype of float. :facepalm:
- :lipstick: Snake-casifying internals

### 0.73.0

- :bug: Fix chandler cue slide set button
- :bug: Fix mixer channel not changing after refresh button until changing the slider
- :lipstick: autoAck and tripDelay are snake_case now
- :lipstick: System status tag points are snake_case
- :sparkles: Add nicer system alerts in the chandler page
- :sparkles: The Scullery framework uses snake_case now
- :bug: Fix wifi status tagpoint
- :bug: Fix missing peewee
- :sparkles: The makefile has tools to test in a venv sans site packages, to prevent future missing stuff.


### 0.71.2

- :bug: Fix contextInfo > context_info snake case bug
- :bug: Pipewire stuttering in some cases
- :bug: Fix page editors


### 0.71.1

- :bug: Further minor CSS work
- :bug: Fix mixing board not working on Firefox


### 0.71.0

- :bug: Further minor CSS work
- :sparkles: iot_devices now comes from Pip. There is no longer any need for git-lfs
- :bug: manually disabling a default tag alert
- :bug: Fix mixer channels not immediately connecting
- :bug: Bump scullery version to fix bugwhere similarly named JACK ports got confused
- :bug: Fix missing snake_compat.py


### 0.70.0

This release has some big changes to the install process, but not many to the
functionality.  Expect a few bugs in the next few versions as we rewrite old code to be more in line with best practices.

- :bug: Fix bogus "sound did not report as playing" message
- :sparkles: "Make file publically acessible" option in the upload for file resources.
- :bug: Fix disabling resource serving
- :sparkles: Dmesg viewer
- :sparkles: Simple_light is now the default theme, as Chrome can on some devices be unhappy with complex themes
- :bug: Improve slow/hanging shutdown
- :bug: Fix Mixer processes hanging around when they should not be
- :sparkles: Let's try to stick to Semantic Versioning for future releases
- :sparkles: Mixer can now accept m3u and m3u8 URLs as sources(Looped, high latency)
- :sparkles: Chandler cues have a "Trigger Shortcut" option and will trigger cues in other scenes having that shortcut code.
- :coffin: None of that included thirdparty stuff!  Now we use Pip dependencies
- :bug: Disenhorriblize the install instructions
- :recycle: Refactor the Chandler Python
- :coffin: Remove non-MPV audio backends
- :coffin: Remove codemirror config options
- :coffin: Remove reap library
- :coffin: Remove old jackd2 stuff
- :coffin: Remove embedded python3 docs
- :sparkles: Simple_light is now the default theme, as Chrome can on some devices be unhappy with complex themes
- :sparkles: The buttonbar CSS class has been changed to tool-bar
- :coffin: Remove embedded python3 docs
- :sparkles: jackmixer now uses pipewire directly
- :coffin: The page header including in user pages is deprecated.  Use <%inherit file="/pagetemplate.html" /> in your code.
- :coffin: BREAKING: the styling on .sectionbox, section, and article is gone. Use .window and .card.
- :sparkles: Work on getting rid of inline styles. We are moving to a custom [CSS Framework](https://eternityforest.github.io/barrel.css/) See css.md in the docs folder.
- :coffin: MAJOR BREAKING user facing APIs are now snake_case. If you see anything not snake_case, it's deprecated.
- :sparkles: Jinja2 support in user-created pages. Mako user pages are deprecated and will eventually be removed.
- :coffin: Remove ancient example modules that had accumulated useless stuff.

### 0.69.20

- :sparkles: Py3.11 Sipport
- :sparkles: Map tile server now integrated, works out of the box, and autofetches missing tiles if you have the settings permission.
- :bug: Fix multilevel nested folders regression
- :sparkles: -1 in cue sound fade in disables crossfading.
- :bug: Fix sound fading out
- :bug: Fix sound speed not getting correctly set in some cases
- :sparkles: Chandler uses sine-in-out easing for lighting fades
- :sparkles: BETA if you have the settings permission, now you can browse edit SQLite databases(Powered by a customized sqlite-web)
- :sparkles: We now monitor dmesg hourly to detect IO Errors
- :coffin: HBMQTT removed, along with it the embedded MQTT broker
- :coffin: Kaithem.mqtt deprecated
- :bug: Fix module.timefunc issues in chandler.
- :bug: Fix deleting device that has subdevice
- :bug: Fix zombie devices messing up page width
- :sparkles: Chandler console icons now show which cues have any lighting commands
- :bug: Fix Chandler backtracking not happening if the cue you are going to is specified as the "next" cue for the current one
- :bug: Fix typo that caused exported Chandler setup files to not load teh fixture assignments.  Old files will still work on the new version.
- :coffin: Simplify locking in Chandler to only use one lock.

### 0.69.1

Moving to Tornado was a rather large change, this release is mostly cleanup.

- :sparkles: Alt top banner HTML option in user pages
- :bug: Can specify per-page theme name instead of full CSS url
- :bug: Fix raw websockets used in NVR streaming
- :bug: Fix tagpoint page fake buttons


### 0.69.0

- :sparkles: Use the Tornado server
- :sparkles: Per-connection Websocket handler threads eliminate global bogdown on blocking socket actions
- :coffin: enable-js, enable-websockets, drayer-port, and other useless config options removed.
- :coffin: config validation no longer rejects additional properties.
- :coffin: We no longer support starting as root and dropping permissions. Use systemd features for port 80.

### 0.68.48

- :coffin: Remove the Chandler tag permissions system, as it is too complex to properly assess the security model. It can now access any tag.
- :sparkles: JACK mixer has a noise gate now
- :sparkles: Link on settings page to take screenshot of server(Useful for checking on signage)
- :bug: Fix hang at shutdown
- :sparkles: New Banderole theme, probably the best example to learn theming
- :sparkles: Control RasPi and maybe others system power and activity LEDs via the tag points interface.
- :sparkles: auto_record datapoint on the NVRChannel for temporarily disabling recording
- :sparkles: Devices framework now has a WeatherClient, No API key needed thanks to wttr.in! :sunny: :cloud: :rainbow:
- :sparkles: Github based online assets library, seamlessly browse and download music and SFX right in Chandler
- :sparkles: Basic support for ESPHome devices(BinarySensor, Number, Sensor, TextSensor, Switch) including reconnect logic
- :bug: Fix zeroconf exceptions
- :sparkles: Chandler is no longer a module, it is now a built in, always-there tab.  Look forward to deeper integrations!
- :sparkles: Chandler audio cues play much faster than before
- :sparkles: Non-writable device data points can be "faked"
- :coffin: p class="help" deprecated, used details class="help"
- :sparkles: simple_light and simple_dark themes are official

### 0.68.47
- :bug: More robust responsive video
- :sparkles: Screen rotation setting in web UI
- :sparkles: Work on a proper theme chooser engine
-
### 0.68.46

- :bug: Video signage auto restart fixes
-
### 0.68.45

- :sparkles: Digital signage chrome error resillience
- :bug: New versions of NumPy needed a fix for the NVR labels file loading

### 0.68.44

- :bug: Faster and more reliable jackmixer startup
- :sparkles: Improve kioskify

### 0.68.43

- :bug: Remove notification for tripped->normal transition
- :sparkles: Show tripped alerts on main page
- :sparkles: Thread start/stop logging now shows thread ID
- :sparkles: Chandler cue media speed, windup, and winddown, to simulate the record player spinup/down or "evil dying robot" effect.
- :bug: Fix temperature alerts chattering on and off if near threshold
- :coffin: Remove code view for Chandler fixture types
- :sparkles: Can now import OP-Z fixture definitions from a file in Chandler(you can select which ones out of the file to import)
-  :coffin: BREAKING: You now run kaithem in the CLI by running dev_run.py.
-  :coffin: BREAKING: You must update Chandler to the new version in included the library, the old one will not work.
-  :coffin: EspruinoHub removed
-  :coffin: Icons other than icofont are gone
-  :sparkles: Should work on Python3.11
-  :sparkles: Can now configure / to redirect to some other page.  Use /index directly to get to the real home.
-  :bug: Fix editing file resources regression
-  :sparkles: /user_static/FN will now serve vardir/static/FN
-  :sparkles: Kaithem-kioskify script configures the whole OS as an embedded controller/signage device from a fresh Pi image

### 0.68.42

This release is all about making the custom HTML pages more maintainable.

- :lipstick: Chandler always shows all scenes, no separate "This board" and "All active"
- :sparkles: We now have a separate setup and handler code area for pages.  Inline code will continue to work as before.
- :sparkles: Special variables \_\_jsvars\_\_ and \_\_datalists\_\_ to directly add stuff to pages.
- :bug: Fix devices in modules
- :lipstick: Use accordion sections on device pages
- :sparkles: Devices now have a configurable description field, to make them more self-documenting.
- :coffin: Anything to do with managing the JACK server is gone. Pipewire needed for live mixing.
- :bug: Fix newly added modules imported from the library not being immediately saved
- :coffin: Remove chandler code view for fixtures.
- :bug: Remove some more nuisance alerts

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

- New .tool-bar and .multibar CSS classes majorly reduce visual clutter
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
- Modules can now add pages to the main bar with kaithem.web.nav_bar_plugins
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
-   **BREAKING CHANGE** Widget.doCallback,on_request, and on_update now
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
-   Fix bug that caused annoying widget.mjs error messages
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
-   One must have either system_admin, view_admin_info, or
    view_admin_info to view page or event errors.
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
-   kaithem.string.format_time_interval()
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
