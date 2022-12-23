

from typing import List


class Error:
    def __init__(self, *, message: str, field: str = None):
        self.message = message
        self.field = field

    def __str__(self):
        return self.message

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return NotImplemented
        if self.message != other.message:
            return False
        if self.field != other.field:
            return False
        return True

    def __repr__(self):
        return '{name}(message={message!r}, field={field!r})'.format(
            name=type(self).__name__,
            message=self.message,
            field=self.field,
        )

    @classmethod
    def parse(cls, errors, prefix: str = None) -> List['Error']:
        if not errors:
            return []

        if isinstance(errors, str):
            return [cls(message=errors, field=prefix)]

        if isinstance(errors, cls):
            return [errors]

        if isinstance(errors, (list, tuple, set)):
            if isinstance(errors[0], cls):
                return errors
            if isinstance(errors[0], str):
                return [cls(message=err, field=prefix) for err in errors]
            raise TypeError('cannot parse errors')

        if isinstance(errors, dict):
            result = []
            for field, message in errors.items():
                if prefix:
                    field = prefix + '.' + field
                result.extend(cls.parse(errors=message, prefix=field))
            return result

        raise TypeError('cannot parse errors')
