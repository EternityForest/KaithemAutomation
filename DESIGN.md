## Architecture

### Modules

Nearly all user content is stored in a "module", which is like a top level folder.  Modules contain "resources" of different types. These are not the same as Python modules.

You automate things by using the features that exist as resource type plugins.

These modules can be downloaded as a .zip and uploaded to another device.

With very few exceptions, we avoid storing anything dynamic outside of a module.



### Tag Points

A tag point is an object that holds a number, a string, JSON data, or binary data.

They are the primary way that different parts of the system connect to each other.

A light bulb device might expose a number tag representing the brightness, and a Chandler board might set that brightness in response to different conditions.

### Chandler

One of the star features of the system, and modeled after theater lighting control systems.
You have a board, which exists as a resource, and within that board you have groups.

Every group has a set of cues, only one of which can be active at a time.  A cue can have a sound, set lighting values, execute simple automation rules, or even display things on any web capable device for signage.

The automation rules work by triggering a row of commands whenever an event happens.  The pipeline runs in order until one of the commands tells it to stop, allowing for simple conditional logic.

### Users

By default, kaithem lets you log in with the username and password of the underlying linux user running the service, but also lets you create local users separate from the linux base system.


### Permissions

User accounts belong to one or more groups.  They have all permissions the groups have.  You can never assign a permission directly to a user, only through a group.

There's a special permission used almost everywhere, system_admin,
that is needed to create, edit, or delete most resources.  It is equivalent to full access to the underlying Linux user account that the server runs as.


In general, the permission model is binary rather than fine grained, making most changes requires system_adminbut there are some specific features that can be delegated to users with less authority.




## Devops concerns


When running inside a Docker container, the kaithem-host-services daemon must be running natively to enable login using host system credentials.  It runs as the same user the app does.

The standard way to run this in a real deployment is with the Docker instructions in the kaithem-scripts repo.



## Internals


### Language

Most everything is done in Python.  The frontend uses Typescript in Vue and Lit, and there are some modules(called "kegs") that are done in Rust.

The rust modules compile to WebAssembly and as such are cross platform, a separate rust build is not needed for every platform.  The python wheel is entirely cross platform.

Most frontend pieces compile with vite.  This is a multi page app, the difference pieces get put in various places.


### The public API

There is the kaithem.api module that defines the stable public interface.

Everything that can, should use this API.


### Core Plugins

These are always there. They load like plugins, but may access private internal APIs, and other plugins or even the main system itself can depend on them.



## Dev Workflow

Docker is used here for almost everything.


### Running directly in uv

Running directly in a UV on bare metal is currently fully supported for development, because it makes debugging using VS Code tools much easier.

See https://github.com/EternityForest/KaithemAutomation/blob/master/kaithem/data/debian_runtime_dependencies.sh for what to install at the host level.


### The kaithem-host-services service

This a tiny python script living in the kaithem-scripts repo that installs with uv and provides authentication using the system auth mechanism.

### The Docker Compose images

kaithem-builder: Builds the python wheel. Build on amd64 only, wheel runs anywhere

kaithem: the production image

kiosk: Chromium configured for kiosk use.

### Build for production

 * Install docker compose with buildx support.
 * Set up a local docker registry on port 5000


Create the builder: `make dev-create-producton-buildx-context`
Run the build command: `dev-build-docker-production`

Now you can pull them on a Pi after configuring an unsecured repo:
`docker pull --platform linux/arm64 192.168.1.XX:5000/cooperskeep/kaithem:0.96.0`

Then test, then push to the public repo.

All published stuff must be manually tested!