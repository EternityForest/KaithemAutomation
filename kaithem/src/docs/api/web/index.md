# Web

[Kaithemautomation Index](../README.md#kaithemautomation-index) / Web

> Auto-generated documentation for [web](../../../../api/web/__init__.py) module.

- [Web](#web)
  - [MyCache](#mycache)
    - [MyCache().dump_bytecode](#mycache()dump_bytecode)
    - [MyCache().load_bytecode](#mycache()load_bytecode)
  - [add_asgi_app](#add_asgi_app)
  - [add_simple_cherrypy_handler](#add_simple_cherrypy_handler)
  - [add_tornado_app](#add_tornado_app)
  - [add_wsgi_app](#add_wsgi_app)
  - [has_permission](#has_permission)
  - [render_jinja_template](#render_jinja_template)
  - [serve_file](#serve_file)
  - [user](#user)
  - [Modules](#modules)

## MyCache

[Show source in __init__.py:33](../../../../api/web/__init__.py#L33)

#### Signature

```python
class MyCache(_jinja2.BytecodeCache):
    def __init__(self): ...
```

### MyCache().dump_bytecode

[Show source in __init__.py:42](../../../../api/web/__init__.py#L42)

#### Signature

```python
def dump_bytecode(self, bucket): ...
```

### MyCache().load_bytecode

[Show source in __init__.py:37](../../../../api/web/__init__.py#L37)

#### Signature

```python
def load_bytecode(self, bucket): ...
```



## add_asgi_app

[Show source in __init__.py:69](../../../../api/web/__init__.py#L69)

Mount an ASGI application to handle all URLs matching the prefix

#### Signature

```python
def add_asgi_app(prefix: str, app, permission="system_admin"): ...
```



## add_simple_cherrypy_handler

[Show source in __init__.py:88](../../../../api/web/__init__.py#L88)

#### Signature

```python
@_beartype.beartype
def add_simple_cherrypy_handler(
    prefix: str, permission: str, handler: Callable[..., str]
): ...
```



## add_tornado_app

[Show source in __init__.py:83](../../../../api/web/__init__.py#L83)

Mount a Tornado application to handle all URLs matching the pattern regex

#### Signature

```python
def add_tornado_app(pattern: str, app, args, permission="system_admin"): ...
```



## add_wsgi_app

[Show source in __init__.py:76](../../../../api/web/__init__.py#L76)

Mount a WSGI application to handle all URLs matching the prefix

#### Signature

```python
def add_wsgi_app(prefix: str, app, permission="system_admin"): ...
```



## has_permission

[Show source in __init__.py:113](../../../../api/web/__init__.py#L113)

Return True if the user accessing the current web request
has the permssion specified

#### Signature

```python
def has_permission(permission: str, asgi=None) -> bool: ...
```



## render_jinja_template

[Show source in __init__.py:50](../../../../api/web/__init__.py#L50)

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

[Show source in __init__.py:93](../../../../api/web/__init__.py#L93)

Call from within a Quart handler to server a file.

#### Signature

```python
def serve_file(path, contenttype="", name=None): ...
```



## user

[Show source in __init__.py:98](../../../../api/web/__init__.py#L98)

asgi: The ASGI scope object that is currently active, required if
      this is called from outside a Quart context.

#### Returns

- `str` - Username of this active web request, or empty string if unknown

#### Signature

```python
def user(asgi=None) -> str: ...
```



## Modules

- [Dialogs](./dialogs.md)