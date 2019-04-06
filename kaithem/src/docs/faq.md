&lt;%include file="/pageheader.html"/&gt;

Kaithem Help

FAQ
===

### Where does Kaithem store data?

By default, kaithem stores all variable data in kaithem/var(inside it's
directory) It does not use the windows registry, APPDATA, a database, or
any other central means of storage. However, keeping your data in
kaithems "unzip and run" folder has a few problems. First and most
important, it makes it hard to update, since if you download a new
version it will not have your data.

To avoid this, we recommend that you copy kaithem/var someplace else,
and use the site-data-dir config option to point to the new location. If
you copy var to /home/juan/ then site-data-dir should equal
/home/juan/var

### How do I let users upload to a a page

Use kwargs\['myfileinputname'\].file.read()

### How do I use custom configuration files?

Create your file, then, when you start Kaithem, use the -c command line
argument to point to it. Example:

    python3 kaithem.py -c myconfigfile

Kaithem uses the YAML format for configuration files, which is a very
simple and easy to read format. YAML example:

    #this is a comment
    option-name: this is the option value

    another-option: 42

    a-long-string-as-an-option: |
    That pipe symbol after the colon lets us start
    a big multiline string on the next line


    an-option-with-a-list-as-a-value:
    -uno
    -dos
    -tres

NOTE: Kaithem will **only** load the configuration file on startup and
you must reload kaithem for the changes to take effect.

### My message bus data is not being saved to the log files! Help!

Kaithem only saves topics to the hard drive if they are in the list of
things to save. Go to the logging page and select the channels you are
interested in. This

### What is with these security certificate errors?

Kaithem comes with a default security certificate in the kaithem/var/ssl
directory. Becuase it is publicly known, it provides **ABSOLUTELY NO
SECURITY**. The intent is to let you test out Kaithem easily, but if you
want to actually deploy an instance, you **MUST** replace the security
key with a real one and keep it secret. There are plenty of TLS/SSL
Certificate tutorials, and equally important is that you ensure that the
permissions on the private key file are truly set to private.

### How do I make an event that triggers at a certain time?

To make an event that goes off at Noon, simply create a normal event and
set the trigger to "kaithem.time.hour() == 12"

### <span id="static"></span>How do I tell Kaithem to serve a static file?

Add something like this to your configuration file

    serve-static:
    images: /home/piper/My Pictures
    images2: /home/piper/My Other Pictures

Now the url /usr/static/images/page.jpg will point to the file
/home/piper/My Pictures/page.jpg  
All user-created static directories are mounted under /usr/static. Be
VERY careful what you choose to serve statically, because anyone will be
able to access them. If you need a secure way to serve a file, you are
better off creating a page with the appropriate permissions, and using
[kaithem.web.serveFile()](#servefile)

### I am getting "permission denied" errors on the web interface

You don't have permission to access that page. If you are admin, go to
the authorization page and give yourself that permission.

### I am not using flash memory, and would like to set up autosave

By default, Kaithem tries to avoid automatic disk writes. This is to
avoid wearing out low-cost flash storage on devices such as the RasPi.
However, if you would like to configure the server to save the state on
an interval, you can set the

    autosave-state

option in the configuration to an interval specified like "1 hour" or "1
day" or 1 day 3 minutes.

Valid units are second,minute,hour,day,week,month,year. Autosaving will
not happen more than onceper minute no matter the setting and if data is
unchanged disk will be untouched. A "month" when used as a length of
time, is a year/12.

**autosave-state does not touch log files. Use autosave-log for that.
It's semantics are the same.**

In addition to periodic saves, you might want to consider setting

    save-before-shutdown

to

    yes

This will tell the server to save everything including log dumps before
shutting down.

### I would like to back up the code that I wrote in Kaithem

At the moment, the easiest way to do this is just to make a copy of the
folder where your variable data is kept.

The modules directory within that dir uses a format designed to work
well with git.

### How exactly does logging work?

Logging is now disabled by default. To enable it, set log-format to
'normal' in the configuration. We now use python's standard logging
module. You can view all output of the root logger from the logging
page, but only log output from the logger named "system" at INFO and
above will be logged to file, to avoid issues with libraries that spam
large amounts to the log files.

A disadvantage of python's logging module is that you cannot really
delete a logger in an officially supported way. As loggers are
reasonably lightweight this should not be an issue, but don't create
huge amounts of loggers.

Until a better solution is implemented, Using one or two loggers per
module will likely not cause any problems.

In general, traffic to kaithem's system log should remain low. HTTP
acesses, normal things that happen more than once a minute, etc should
not be logged there. Even when errors are occuring, only the first few
in a minute should be logged.

Try not to create too much traffic on the root logger either in normal
use. Posting a debug message to root for every error is fine, because
normally there should not be dozens of errors a second. But don't just
spam it all the time, the root logger's debug output should be readable
and reasonably understandable in real time.

    keep-log-files

configuration option deterimines how much space log files will consume
before the oldest are deleted. The default is

    256m

or 256 Megabytes. You can use the suffixes k,m,and g, and if you don't
supply a suffix, the number will be interpreted as bytes(!)

Log files are kept in ram until manually dumped, automatically dumped by
the autosave-logs timer, or the total number of log entries exceeds the
log-buffer value in the config, at which point they are dumped to
logging/dumps in the kaithem vardir. It is 25000 by default. Set it to 1
to write all logs immediately to the file, but only if you are using a
hard disk or high endurance SSD.

log-dump-size determines how many entries to log to each file before
starting a new one. It is also 25000 by default.

Logs can also be compressed with the option

    log-compress

This option can take any of:

-   none
-   gzip
-   bz2

Compressed files will have the extension

    .json.gz or .json.bz2

The old JSON direct logging of message bus topics is no longer
supported.

### Can I customize Kaithem's appearance for my specific deployment?

Certainly! Kaithem was designed with theming and customization in mind
from the start. You will probably want to do some or all of the
following.

#### Change the Top Banner

Changing the top banner is pretty simple. All you need to do is add a
line in your configuration file like:

    top-banner-html: |
    &ltdiv id="topbanner">&lth1 align="center"&gtYOUR TEXT HERE</h1></div>

Of course, you can add whatever HTML you like, this is just an example.
You can even add images(see "[How do I tell Kaithem to serve a static
file?](#static)")

#### Changing the front page text

This is equally easy. The top box on the front page is fully
customizable. the front-page-banner attribute in your config file can
contain any HTML. The default is:

    front-page-banner: |
    &ltb&gtKaithem is free software licensed under the GPLv3.&ltbr>
    Kaithem was not designed for mission critical or safety of life systems and no warranty is expressed
    or implied.&ltbr> Use entirely at your own risk.</b>

#### Change the actual CSS theme

This is a bit harder. The default CSS file is called scrapbook.css,
found in /kaithem/data/static. What you will need to do is to create a
new theme file, serve it as a static file, and then use the "theme-url"
option in your config file to point to the new theme. You will likely
just want to modify the existing scrapbook.css because it is a 100+ line
file and there are some things that don't quite look right with the
browser defaults.

#### Rewrite the HTML

The HTML is pretty simple, and most pages include the header
src/html/pageheader.html. The only trouble with modifying things is
updatability, and the easiest way to fix that is probably using a
version control tool like Git. Modifying the HTML might be the best
option for more extensive customizations.

### What can I do to make Kaithem more reliable?

Watch out for things that have to be turned on,left on for a while, and
then turned off. Don't depend on high frame rates. Keep in mind that the
server may need to restart at some time for updates. Everything should
start with sane defaults immediately on loading. Keep in mind that the
order in which events and modules load is not currently defined(this
should be adressed soon), however an event will never run before it's
setup section, and almost all dependancy issues should be handled by the
automatic retry.

An error in a setup section will cause that event to be skipped, the
rest of the events to be loaded, then the failed ones will be retried up
to the max attempts(default 25)

On a related note, watch out for dependancies between events and
modules. The order in which modules or events load is currently not
defined. Dependancies are handled automatically in most cases.

Also, keep in mind what happens when Kaithem shuts down or restarts: any
events currently executing finish up, but no new events are run. (except
events triggered by the /system/shutdown message)

Put an emphasis on automatic management, detection, and recovery, and
keep in mind external services may undergo downtime. Example: If you
need a serial port, don't just set it up when kaithem loads. Create a
manager event that periodically checks to make sure all is well and if
not tries to reopen the port. Remember you may want to run Kaithem for
months without a reboot, and conversely you may want to handle rebooting
without manual intervention.

Blocks of code that must be atomic should not depend on things that
might be deleted or changed before the event is finished, such a
!function event or anything using a "weakref and proxy" based interface.

If you really do have something that must be atomic, such as a firmware
update via a serial port to some device, the best way to handle it is by
containing the critical part in a single event that does not depend on
!function events or plugins.

The kaithem.globals namespace contents are not subject to any kind of
automatic cleanup, and the module object is a real object and not a weak
reference. !function events may still go away and raise an error,
however, so declare anything you need to use in a block that must be
atomic as a plain old function and assign it to something that won't go
away.

### Can I run multiple instances of Kaithem?

Quite possibly. It has not been tested though. If you do, they should
probably have different directories for variable data.

### What happens if two people edit something at the same time?

Kaithem was not designed as a large-scale collaboration system. At the
moment,If two people edit something at the same time, the last person to
click save "wins", not unlike having two open text editors open to the
same file. There should, however, be no issue with two users editing
different resources at once. At present there are no plans to change
this behavior.

### How do unencrypted pages work?

Kaithem will allow unencrypted acess to any page that does not require
any permissions. Kaithem will also allow unencrypted acess to any page
that the special user "\_\_guest\_\_" could access, if such a user
exists. All other pages may only be acessed over HTTPS. use the
'http-port' and 'http-thread-pool' options to change the number of
threads assigned and the port used for unsecure access.

### How can I change the port in which kaithem serves?

Kaithem normally serves on two different ports, one for HTTP(plaintext)
and one for HTTPS(Secure) connections. use the http-port and https-port
configuration options to set each respectively. Use an integer value.

### How should I deploy Kaithem in a real application?

First, keep in mind that while Kaithem is fairly reliable, it was not
designed for anything like medical equipment or nuclear plants. With
that in mind, deploying Kaithem is pretty easy. You will most likely
want an always-on server, probably running linux(The Raspberry Pi is a
great server), and you will probably want to set up a static IP.

Since, at the moment, Kaithem lacks an installer, the recommended
installation procedure is to install git, create a new linux user just
for the server, and clone into the new user's home directory. Give the
user any permisions needed to acess your automation hardware.

Be sure to use real SSL keys, and to change the default passwords.

You will almost certainly want to automatically start on boot, and the
easiest way to do this is to make an entry in the Kaithem user's
crontab.

To update Kaithem, simply go into the Kaithem install folder in the
user's home dir, and do a git pull.

Be careful updating, 100% backwards compatibility is not guaranteed at
this stage of the project, and some config options might gte deprecated
and your settings may be ignored. That said, backwards compatibility is
an important goal, and release notes should include and known issues.

You should make a copy of kaithem/var, put it somewhere else, and change
the

    site-data-dir

In your config file to point to it. Also change ssl-dir to point to
whereever you put the certificate.cert and certificate.key files of your
private key. If you don't do this, it will write your
data(modules,pages,events,settings) directly into the cloned repo, which
may cause an error when you try to update via git.

If you are doing web kiosks or datalogging or anything else wherer you
need to reliably track changing data, the "keep everything in ram and
periodically save" model may not work. You might want to consider using
a spinnin drive or good SSD and SQLite. for rapidly changing data.

### Audio is not working on the RasPi

At least on the version of Raspbian used for testing, SoX will not work
unless you set the following environment variables

    AUDIODEV=hw:0
    AUDIODRIVER=alsa

Also,the user that kaithem is running under must be in the audio group,
use

    sudo usermod -a -G audio USERS_NAME

to fix that. The default user had this enables already but if you made a
new user you may need to use the command.

### How does the polling mechanism manage CPU time and prevent "hogging"?

The short answer is that Kaithem attempts to distribute CPU time fairly,
and make sure all events continue to run even when some are vastly
slower than others. In general, the programmer should be able to imagine
that each event has its on thread even though the thread pool model is
used. The long answer in more technical.

The current poll management system is based on the kaithem thread pool.
The thread pool is a set of threads fed by a threadsafe queue. Function
objects are placed in the queue and threads take them out and execute
them.

In kaithem, a polling cycle is called a frame. Every frame, kaithem puts
the poll function of every event that needs to be polled into the queue.
Should a thread get a poll function and find out that another thread is
already polling it, that event is simply skipped to prevent a slow event
clogging the pool by causing many threads to wait on the last thread to
be done ith it so they can poll it.

After the manager thread has inserted all the poll functions into the
queue, it inserts a special sentinel. The manager thread will not start
the next frame until this sentinel has run. The sentinel running lets us
know that everything we put in the queue has been taken out. If a slow
event is still running at this point, it will continue to run, and
another copy of it should never be queued up in any way until the
current one finished.

The one known case in which slow tasks can bog down the system is if
there are more slow tasks than there are threads in the pool. In this
case the system may be unresponsive for a time until the tasks finish.
This is unlikely as the odds of having dozens of tasks at the same time
that are very slow is low in most systems.

<span id="dependancies"></span>

### How does Kaithem handle dependancies between resources?

With pages, it's not much of an issue. Pages are compiled the first time
they get accessed, and if that fails due to a dependancy, the compiling
will be retried next time someone tries to access it. It is hard to
imagine pages depending on each other in any major way anyway, because
pages are usually not the place to write libraries.

Events are another story. Since kaithem implements "running some code at
startup", including user created functions, as an event, events may have
any amount of dependancy on each other.

The way that kaithem handles this, is that when an exception occurs in
an event's setup code(while loading the event), kaithem simply stops,
moves on with the rest of the list of events that need loading, and then
comes back to the event that failed, up to a number of times set in the
config.

This means that you should almost never need to deal with dependancy
resolution issues yourself, they are handled as a consequence of
kaithem's auto-retry mechanism. However, to imporove load time, you may
want to make dependancies more explicit by adding something like this:

    depends = kaithem.globals.ThingThisEventExpectsToBePresent
    depends = FunctionCallThatWillFailIfDependacyNotMet()

to the beginning of the setup function. These lines will raise errors if
there are unmet dependancies. causeing kaithem to exit immediatly,
instead of after having wasted more time. It's also valuable
documentation. But in general, don't worry about dependancies. Just keep
in mind that your setup functions might get retried.

### Help! My setup code executes twice!

Internally, the setup code is run once during the 'test compile', then
once when actually creating the event. The object created in the test
compile is deteted, so all deleters are honored. Your setup setions
should be retry tolerant anyway, but this issue may be fixed later

### I need better data reliability than simple autosave

Then you should probably use sqlite, which is built into python, or
another transactional database.

&lt;%include file="/pagefooter.html"/&gt;
