# kaithem.api.web

## Submodules

* [kaithem.api.web.dialogs](dialogs/index.md)

## Attributes

| [`quart_app`](#kaithem.api.web.quart_app)             |    |
|-------------------------------------------------------|----|
| [`theming`](#kaithem.api.web.theming)                 |    |
| [`nav_bar_plugins`](#kaithem.api.web.nav_bar_plugins) |    |

## Classes

| [`MyCache`](#kaithem.api.web.MyCache)   | To implement your own bytecode cache you have to subclass this class   |
|-----------------------------------------|------------------------------------------------------------------------|

## Functions

| [`render_jinja_template`](#kaithem.api.web.render_jinja_template)(template_filename, \*\*kw)      | Given the filename of a template, render it in a context where it has               |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|
| [`render_html_file`](#kaithem.api.web.render_html_file)(body_fn[, title])                         | Given a file raw html, render it in completed page, with header and footer          |
| [`render_html_string`](#kaithem.api.web.render_html_string)(body[, title])                        | Given a string raw html, render it in completed page, with header and footer        |
| [`add_asgi_app`](#kaithem.api.web.add_asgi_app)(prefix, app[, permission])                        | Mount an ASGI application to handle all URLs matching the prefix                    |
| [`add_wsgi_app`](#kaithem.api.web.add_wsgi_app)(prefix, app[, permission])                        | Mount a WSGI application to handle all URLs matching the prefix                     |
| [`add_module_plugin_link`](#kaithem.api.web.add_module_plugin_link)(link, destination)            | Add a link to module pages. Destination must be an absolute URL with no params      |
| [`add_file_resource_link`](#kaithem.api.web.add_file_resource_link)([filter])                     | Add a link to every file resource if filter matches                                 |
| [`add_file_resource_preview_plugin`](#kaithem.api.web.add_file_resource_preview_plugin)([filter]) | Add a preview box to every file resource if filter matches                          |
| [`user`](#kaithem.api.web.user)(→ str)                                                            | asgi: The ASGI scope object that is currently active, required if                   |
| [`has_permission`](#kaithem.api.web.has_permission)(→ bool)                                       | Return True if the user accessing the current web request                           |
| [`require`](#kaithem.api.web.require)(permission)                                                 | Raise an exception if the user accessing the current web request in a Quart context |

## Package Contents

### kaithem.api.web.quart_app

### kaithem.api.web.theming

### kaithem.api.web.nav_bar_plugins

### *class* kaithem.api.web.MyCache

Bases: `jinja2.BytecodeCache`

To implement your own bytecode cache you have to subclass this class
and override [`load_bytecode()`](#kaithem.api.web.MyCache.load_bytecode) and [`dump_bytecode()`](#kaithem.api.web.MyCache.dump_bytecode).  Both of
these methods are passed a `Bucket`.

A very basic bytecode cache that saves the bytecode on the file system:

```default
from os import path

class MyCache(BytecodeCache):

    def __init__(self, directory):
        self.directory = directory

    def load_bytecode(self, bucket):
        filename = path.join(self.directory, bucket.key)
        if path.exists(filename):
            with open(filename, 'rb') as f:
                bucket.load_bytecode(f)

    def dump_bytecode(self, bucket):
        filename = path.join(self.directory, bucket.key)
        with open(filename, 'wb') as f:
            bucket.write_bytecode(f)
```

A more advanced version of a filesystem based bytecode cache is part of
Jinja.

#### cache

#### load_bytecode(bucket)

Subclasses have to override this method to load bytecode into a
bucket.  If they are not able to find code in the cache for the
bucket, it must not do anything.

#### dump_bytecode(bucket)

Subclasses have to override this method to write the bytecode
from a bucket back to the cache.  If it unable to do so it must not
fail silently but raise an exception.

### kaithem.api.web.render_jinja_template(template_filename: str, \*\*kw)

Given the filename of a template, render it in a context where it has
access to certain Kaithem standard templates

Example template that uses the standard kaithem template everything else does.

{% extends "pagetemplate.j2.html" %}

{% block title %}Title Here{% endblock %}

{% block body %}
<main>
Content here
</main>
{% endblock %}

### kaithem.api.web.render_html_file(body_fn: str, title: str = 'Kaithem')

Given a file raw html, render it in completed page, with header and footer

### kaithem.api.web.render_html_string(body: str, title: str = 'Kaithem')

Given a string raw html, render it in completed page, with header and footer

### kaithem.api.web.add_asgi_app(prefix: str, app, permission='system_admin')

Mount an ASGI application to handle all URLs matching the prefix

### kaithem.api.web.add_wsgi_app(prefix: str, app, permission='system_admin')

Mount a WSGI application to handle all URLs matching the prefix

### kaithem.api.web.add_module_plugin_link(link: str, destination: str)

Add a link to module pages. Destination must be an absolute URL with no params
It will get the module and dir params added to it.

Link must be HTML content of the link.

### kaithem.api.web.add_file_resource_link(filter: None | collections.abc.Callable[[str, str], tuple[str, str] | None] = None)

Add a link to every file resource if filter matches
Return value is link html, destination tuple or None.

Input is module, resource

### kaithem.api.web.add_file_resource_preview_plugin(filter: None | collections.abc.Callable[[dict[str, Any]], str | None] = None)

Add a preview box to every file resource if filter matches
Return value is embedded html or None.

Input is a dict that may have none to any of the following keys:
: module, resource, size, timestamp, path
  access_url, thumbnail_url

You should use the access_url rather than getting it yourself,
if it exists, because it may give you a url with specific permissions

### kaithem.api.web.user(asgi=None) → str

asgi: The ASGI scope object that is currently active, required if
: this is called from outside a Quart context.

Returns:
: str: Username of this active web request, or empty string if unknown

### kaithem.api.web.has_permission(permission: str, asgi=None, user: str | None = None) → bool

Return True if the user accessing the current web request
has the permssion specified.

If not running in a Quart context, you must use the asgi parameter
and specify a scope, or specify a user directly.

### kaithem.api.web.require(permission: str)

Raise an exception if the user accessing the current web request in a Quart context
does not have the permssion specified
