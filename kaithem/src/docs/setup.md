
Installation
============

All required dependancies should already be included. Huge thanks to the developers of all the great libraries used!!!

There's a few optional dependancies though. Auto time synchronization and MDNS depends on netifaces, and sound requires mplayer, madplay, or sox, with all but mplayer not recommended. Pavillion-based net sync requires libnacl. Sound mixing needs jackd2, python3-gstreamer1.0, and all the gstreamer plugins.

git clone or download somewhere and run `python3 kaithem/kaithem.py`

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
        Similar, except allows access from other machines on the local network. Not
        recommended except on private LANs.

Then point your browser to https://localhost:<yourport> (default port is 8001)
and log in with Username:admin Password:password

It will give you a security warning, that the SSL certificate name is wrong,
ignore if you are just playing around, use real SSL keys otherwise.

Look at the help section and the examples module, there is a lot more documentation built into the system.

If you are really going to use this you must change the ssl keys in /ssl to something actually secret.

If you stop the process with ctrl-C, it might take a few seconds to stop normally.
If you force stop it it might leave behind a lingering process that you have to kill-9 because it holds onto the port so you can't restart kaithem.


If you install using the debian package helper, you will be prompted for an admin password.