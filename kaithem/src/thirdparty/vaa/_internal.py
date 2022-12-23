

import inspect

from ._django_utils import safe_model_to_dict
from ._error import Error


class ValidationError(ValueError):
    pass


class BorgDict(dict):
    def __getattr__(self, name: str):
        if name in self:
            return self[name]
        else:
            raise AttributeError(name)


class Simple:

    def __init__(self, validator, error: str = 'validation error', param: str = '_'):
        self.error = error

        params = inspect.signature(validator).parameters.keys()
        if tuple(params) == (param,):
            self.validator = validator
        else:
            self.validator = lambda data, **kwargs: validator(**data, **kwargs)

    def __call__(self, data, **kwargs):
        self.data = safe_model_to_dict(data)
        self.kwargs = kwargs
        return self

    def is_valid(self) -> bool:
        self.cleaned_data = None
        self.errors = None

        data = self.data
        if isinstance(data, dict):
            data = BorgDict(data)
        try:
            result = self.validator(data, **self.kwargs)
        except ValidationError as exc:
            result = exc.args[0]

        # ValidationError was returned instead of raising
        if type(result) is ValidationError:
            result = result.args[0]

        # returned something falsy
        if not result:
            self.errors = Error.parse(self.error)
            return False

        # returned errors
        if isinstance(result, (tuple, list, set, dict, str)):
            self.errors = Error.parse(result)
            return False

        # returned something truely
        self.cleaned_data = self.data
        return True
