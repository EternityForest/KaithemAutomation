#!/usr/bin/python3

import kaithem

# This object is the same as the "kaithem" object in pages and events
api = kaithem.initialize_app()

# Here we add some custom pages to a deployment,
# In code, rather than going through the Web UI.
# The advantage here is that you can use your editor and debugger of choice,
# Making things much easier if you are building something large and complex.

# It also allows you to keep your app logic separate from Kaithem itself.


kaithem.start_server()
