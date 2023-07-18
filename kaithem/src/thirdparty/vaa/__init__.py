
"""
Validators Adapter. The common interface for all validators.
"""


from ._aliases import (
    cerberus,
    django,
    marshmallow,
    pyschemes,
    simple,
    restframework,
    wtforms,
)
from ._auto import validators
from ._error import Error
from ._internal import ValidationError


__version__ = '0.2.1'

__all__ = [
    'cerberus',
    'django',
    'marshmallow',
    'pyschemes',
    'restframework',
    'simple',
    'wtforms',

    'Error',
    'ValidationError',
    'wrap',
]


wrap = validators.wrap
