# Kaithem Plugins System

The way this works is that every directory in the "startup" folder will be imported, inside a try/catch block. This happens once Kaithem has fully loaded.

The ondemand folder is part of kaithem's path, but nothing there is imported
unless an import statement is used.

Every plugin folder must be removable without affecting Kaithem itself.  This
adds modularity, but also lets us use GPL things in the core distribution
while preserving the possibility of a version under a permissive license.

The exception is that plugins may depend on other plugins(Otherwise).
