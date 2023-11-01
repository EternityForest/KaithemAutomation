FAQ
===


### How do I use version control? How do I edit pages with an external editor?

Kaithem was designed to make this easy. Look in /var/lib/kaithem (Or the var directory in unzip-and-run mode).

Inside you will find a modules folder, and within that a data folder containing the latest state of the modules.

There are other folders with numbers in the names too, these are backed up old versions.

Inside the data folder, every module gets a subfolder.

Events are represented as python files with a __data__ string, the setup section under if __name__=='__setup__':, etc.  It's fairlt obvious.

Pages are stored as HTML files, with a script at the top in a special script type.

Kaithem won't mess with your .git folder should you choose to use git.



### Kaithem can't do something!

Have you checked if it's a permission problem? If it's installed as a
package, it runs under it's own user.

Try one of these as appropriate

```
#For serial ports
usermod -a -G serial kaithem
usermod -a -G dialout kaithem

#For Audio, especially realtime issues
usermod -a -G audio kaithem

# RPi GPIO, and general low level interfacing
usermod -a -G gpio kaithem
usermod -a -G i2c kaithem
usermod -a -G spi kaithem

#Changing WiFi settings
usermod -a -G netdev kaithem

#Misc
usermod -a -G video kaithem
usermod -a -G uucp kaithem
```


### Where does Kaithem store data?

By default, kaithem stores all variable data in kaithem/var(inside it's
directory) It does not use the windows registry, APPDATA, a database, or
any other central means of storage.

If installed as a Debian package, Kaithem will store it's data in /var/lib/kaithem unless configures otherwise.

However, keeping your data in
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


### I am getting "permission denied" errors on the web interface

You don't have permission to access that page. If you are admin, go to
the authorization page and give yourself that permission.


### I would like to back up the code that I wrote in Kaithem

At the moment, the easiest way to do this is just to make a copy of the
folder where your variable data is kept. See "How do I use version control"
for more info.

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

We also assume anything on localhost is a secure connection equivalent to HTTPS.
Don't build some bizzare proxy setup that breaks that assumption.

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

### What CSS Classes are used?


#### theme-item-animation-enter-active and others 

theme-item-animation-leave-active, theme-item-animation-leave-to, and theme-item-animation-enter-from
are used to allow you to animate the entrance and leaving of an item in a theme-specific way.

theme-item-animation-leave-active can work as a CSS class by itself, to animate page loads, or you can just use <Template name="theme-item-animation">

#### Buttonbar

A div with class tool-bar filled with buttons, inputs, p, labels, headings, and links, produces the bars frequently seen

  

