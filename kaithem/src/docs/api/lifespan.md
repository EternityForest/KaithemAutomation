# Lifespan

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Lifespan

> Auto-generated documentation for [lifespan](../../../api/lifespan.py) module.

#### Attributes

- `shutdown` - True if the system is shutting down: False


- [Lifespan](#lifespan)
  - [at_shutdown](#at_shutdown)

## at_shutdown

[Show source in lifespan.py:9](../../../api/lifespan.py#L9)

Register a function to be called when the system shuts down,
before atexit would trigger

#### Signature

```python
def at_shutdown(f): ...
```