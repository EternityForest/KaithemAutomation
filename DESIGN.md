## Modules

Nearly all user content is stored in a "module", which is like a top level folder.  Modules contain "resources" of different types.

You automate things by using the features that exist as resource type plugins.


## Permissions

User accounts belong to one or more groups.  They have all permissions the groups have.  You can never assign a permission directly to a user, only through a group.

There's a special permission used almost everywhere, system_admin,
that is needed to create, edit, or delete most resources.  It is equivalent to full access to the underlying Linux user account.

In general, the permission model is binary rather than fine grained,
but there are some specific features that can be delegated to users with less authority.
