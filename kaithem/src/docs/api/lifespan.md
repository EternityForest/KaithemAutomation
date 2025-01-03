# Lifespan

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Lifespan

> Auto-generated documentation for [lifespan](../../../api/lifespan.py) module.

#### Attributes

- `shutdown`: `bool` - True if the system is shutting down: False


- [Lifespan](#lifespan)
  - [at_shutdown](#at_shutdown)
  - [shutdown_now](#shutdown_now)

## at_shutdown

[Show source in lifespan.py:16](../../../api/lifespan.py#L16)

Register a function to be called when the system shuts down,
before atexit would trigger

#### Signature

```python
def at_shutdown(f): ...
```



## shutdown_now

[Show source in lifespan.py:11](../../../api/lifespan.py#L11)

Shut down the system now

#### Signature

```python
def shutdown_now(): ...
```