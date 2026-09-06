from typing import Any, Callable, Dict, Iterable, List, Optional, Set


class Console_ABC:
    "Abstract base class for console to make typing easier"

    def cl_setup(self, project: dict[str, Any]):
        pass

    def linkSend(self, data: List[Any]):
        pass

    def linkSendTo(self, data: list[Any], target: str):
        pass

    def __init__(self) -> None:
        self.newDataFunctions: List[Callable[..., Any]] = []

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

    def pushEv(self, event: str, target, time_unix=None, value=None, info=""):
        "Tell frontend about event"
