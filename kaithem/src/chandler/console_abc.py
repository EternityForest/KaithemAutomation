from collections.abc import Callable, Iterable
from typing import Any


class Console_ABC:
    "Abstract base class for console to make typing easier"

    def cl_setup(self, project: dict[str, Any]):
        pass

    def linkSend(self, data: list[Any]):
        pass

    def linkSendTo(self, data: list[Any], target: str):
        pass

    def __init__(self) -> None:
        self.newDataFunctions: list[Callable[..., Any]] = []

    def pushCueMeta(
        self,
        cueid: str,
        keys: list[str] | None = None,
        target: str | None = None,
    ):
        "Push all metadata about the cue to the clients"

    def pushCueData(self, cueid: str, target: str | None = None):
        "Push lighting values for cue to clients"

    def push_group_meta(
        self,
        groupid: str,
        statusOnly: bool = False,
        keys: list[Any]
        | set[Any]
        | dict[Any, Any]
        | Iterable[str]
        | None = None,
        target: str | None = None,
    ):
        "Push group metadata"

    def pushEv(
        self,
        event: str,
        target_group: str,
        time_unix: float | None = None,
        value: Any = None,
        info: str = "",
    ):
        "Tell frontend about event"
