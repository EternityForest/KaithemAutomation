

from contextlib import suppress
from importlib import import_module
from inspect import isfunction
from logging import getLogger
from typing import Dict

from . import _aliases
from ._cached_property import cached_property
from ._external import BaseWrapper
from ._internal import Simple


WRAPPERS = {
    'cerberus.Validator': _aliases.cerberus,
    'django.forms.Form': _aliases.django,
    'marshmallow.Schema': _aliases.marshmallow,
    'pyschemes.Scheme': _aliases.pyschemes,
    'rest_framework.serializers.Serializer': _aliases.restframework,
    'wtforms.Form': _aliases.wtforms,
}


class Validators:
    logger = getLogger('vaa')

    def __init__(self, wrappers: Dict[str, type]):
        self._wrappers = wrappers

    def wrap(self, validator, simple: bool = True):
        # if already wrapped, do nothing
        if isinstance(validator, (BaseWrapper, Simple)):
            return validator

        # wrap external validator
        for import_path, validator_class in self._validators.items():
            if isinstance(validator, validator_class):
                wrapper = self._wrappers[import_path]
                return wrapper(validator)
            if isinstance(validator, type) and issubclass(validator, validator_class):
                wrapper = self._wrappers[import_path]
                return wrapper(validator)

        # wrap simple validator
        if simple and isfunction(validator):
            return _aliases.simple(validator)

        raise TypeError('no wrapper found')

    @cached_property
    def _validators(self):
        validators = dict()
        for import_path in self._wrappers:
            with suppress(ImportError):
                module_name, class_name = import_path.rsplit('.', 1)
                module = import_module(module_name)
                validators[import_path] = getattr(module, class_name)
        self.logger.debug('validators found', extra=dict(validators=list(validators)))
        return validators


validators = Validators(wrappers=WRAPPERS)
