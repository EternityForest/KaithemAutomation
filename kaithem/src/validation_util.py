from collections.abc import Callable
from typing import Any, TypeVar

import pydantic

T = TypeVar("T", bound=Callable[..., Any])


def validate_args(func: T) -> T:
    return pydantic.validate_call(
        config=pydantic.ConfigDict(arbitrary_types_allowed=True)
    )(func)
