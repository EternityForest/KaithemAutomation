# Kaithem Plugins System

The way this works is that every directory in this folder will be imported, inside a try/catch block. This happens once Kaithem has fully loaded.

Every plugin folder must be removable without affecting Kaithem itself, but they are not loosely coupled and may access internal
APIs here.  This is basically still just internal components.