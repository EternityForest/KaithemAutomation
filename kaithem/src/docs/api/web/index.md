# Web

[Kaithemautomation Index](../README.md#kaithemautomation-index) / Web

> Auto-generated documentation for [web](../../../../api/web/__init__.py) module.

- [Web](#web)
  - [MyCache](#mycache)
    - [MyCache().dump_bytecode](#mycache()dump_bytecode)
    - [MyCache().load_bytecode](#mycache()load_bytecode)
  - [add_asgi_app](#add_asgi_app)
  - [add_file_resource_link](#add_file_resource_link)
  - [add_module_plugin_link](#add_module_plugin_link)
  - [add_wsgi_app](#add_wsgi_app)
  - [has_permission](#has_permission)
  - [render_html_file](#render_html_file)
  - [render_jinja_template](#render_jinja_template)
  - [require](#require)
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

[Show source in __init__.py:81](../../../../api/web/__init__.py#L81)

Mount an ASGI application to handle all URLs matching the prefix

#### Signature

```python
def add_asgi_app(prefix: str, app, permission="system_admin"): ...
```



## add_file_resource_link

[Show source in __init__.py:104](../../../../api/web/__init__.py#L104)

Add a link to every file resource if filter matches
Return value is link html, destination tuple or None.

Input is module, resource

#### Signature

```python
def add_file_resource_link(
    filter: None | Callable[[str, str], tuple[str, str] | None] = None,
): ...
```



## add_module_plugin_link

[Show source in __init__.py:95](../../../../api/web/__init__.py#L95)

Add a link to module pages. Destination must be an absolute URL with no params
It will get the module and dir params added to it.

Link must be HTML content of the link.

#### Signature

```python
def add_module_plugin_link(link: str, destination: str): ...
```



## add_wsgi_app

[Show source in __init__.py:88](../../../../api/web/__init__.py#L88)

Mount a WSGI application to handle all URLs matching the prefix

#### Signature

```python
def add_wsgi_app(prefix: str, app, permission="system_admin"): ...
```



## has_permission

[Show source in __init__.py:135](../../../../api/web/__init__.py#L135)

Return True if the user accessing the current web request
has the permssion specified

#### Signature

```python
def has_permission(permission: str, asgi=None) -> bool: ...
```



## render_html_file

[Show source in __init__.py:73](../../../../api/web/__init__.py#L73)

#### Signature

```python
def render_html_file(body: str, title: str = "Kaithem"): ...
```



## render_jinja_template

[Show source in __init__.py:52](../../../../api/web/__init__.py#L52)

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

#### Signature

```python
def render_jinja_template(template_filename: str, **kw): ...
```



## require

[Show source in __init__.py:141](../../../../api/web/__init__.py#L141)

Raise an exception if the user accessing the current web request in a Quart context
does not have the permssion specified

#### Signature

```python
def require(permission: str): ...
```



## serve_file

[Show source in __init__.py:115](../../../../api/web/__init__.py#L115)

Call from within a Quart handler to server a file.

#### Signature

```python
def serve_file(path, contenttype="", name=None): ...
```



## user

[Show source in __init__.py:120](../../../../api/web/__init__.py#L120)

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