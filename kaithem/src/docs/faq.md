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

### How can I change the port in which kaithem serves?

Kaithem normally serves on two different ports, one for HTTP(plaintext)
and one for HTTPS(Secure) connections. use the http-port and https-port
configuration options to set each respectively. Use an integer value.

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