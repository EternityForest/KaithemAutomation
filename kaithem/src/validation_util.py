from collections.abc import Callable
from typing import Any

import pydantic


def validate_args(func: Callable[..., Any]) -> Callable:
    return pydantic.validate_call(
        config=pydantic.ConfigDict(arbitrary_types_allowed=True)
    )(func)
