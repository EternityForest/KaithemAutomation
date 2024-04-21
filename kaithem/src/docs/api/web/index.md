# Web

[Kaithemautomation Index](../README.md#kaithemautomation-index) / Web

> Auto-generated documentation for [web](../../../../api/web/__init__.py) module.

- [Web](#web)
  - [add_simple_cherrypy_handler](#add_simple_cherrypy_handler)
  - [add_tornado_app](#add_tornado_app)
  - [add_wsgi_app](#add_wsgi_app)
  - [goto](#goto)
  - [has_permission](#has_permission)
  - [render_jinja_template](#render_jinja_template)
  - [serve_file](#serve_file)
  - [user](#user)
  - [Modules](#modules)

## add_simple_cherrypy_handler

[Show source in __init__.py:64](../../../../api/web/__init__.py#L64)

Register handler for all requests that look like /prefix.
handler must look like:
f(*path, **kwargs)

It will by in a cherrypy context.

This function is alpha.

#### Signature

```python
@_beartype.beartype
def add_simple_cherrypy_handler(
    prefix: str, permission: str, handler: Callable[..., str]
): ...
```



## add_tornado_app

[Show source in __init__.py:59](../../../../api/web/__init__.py#L59)

Mount a Tornado application to handle all URLs matching the pattern regex

#### Signature

```python
def add_tornado_app(pattern: str, app, args, permission="system_admin"): ...
```



## add_wsgi_app

[Show source in __init__.py:54](../../../../api/web/__init__.py#L54)

Mount a WSGI application to handle all URLs matching the pattern regex

#### Signature

```python
def add_wsgi_app(pattern: str, app, permission="system_admin"): ...
```



## goto

[Show source in __init__.py:80](../../../../api/web/__init__.py#L80)

Call from within a CherryPy handler to raise an exception to go to another URL

#### Signature

```python
def goto(url): ...
```



## has_permission

[Show source in __init__.py:103](../../../../api/web/__init__.py#L103)

Return True if the user accessing the current web request
has the permssion specified

#### Signature

```python
def has_permission(permission: str): ...
```



## render_jinja_template

[Show source in __init__.py:35](../../../../api/web/__init__.py#L35)

Given the filename of a template, render it in a context where it has
access to certain Kaithm standard templates

Example template that uses the standard kaithem template everything else does.

{% extends "pagetemplate.j2.html" %}

{% block title %}Title Here{% endblock %}

{% block body %}
<main>
    Content here
</main>
{% endblock %}

#### Signature

```python
def render_jinja_template(template_filename: str, **kw): ...
```



## serve_file

[Show source in __init__.py:85](../../../../api/web/__init__.py#L85)

Call from within a CherryPy handler to server a file.

#### Signature

```python
def serve_file(path, contenttype="", name=None): ...
```



## user

[Show source in __init__.py:90](../../../../api/web/__init__.py#L90)

#### Returns

- `str` - Username of this active web request, or empty string if unknown

#### Signature

```python
def user() -> str: ...
```



## Modules

- [Dialogs](./dialogs.md)