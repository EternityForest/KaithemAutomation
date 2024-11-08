from typing import Any, Callable, Dict, Iterable, List, Optional, Set


class Console_ABC:
    "Abstract base class for console to make typing easier"

    def cl_setup(self, project: dict[str, Any]):
        pass

    def linkSend(self, data: List[Any]):
        pass

    def __init__(self) -> None:
        self.newDataFunctions: List[Callable[..., Any]] = []

    def pushCueMeta(self, cueid: str):
        "Push all metadata about the cue to the clients"

    def pushCueData(self, cueid: str):
        "Push lighting values for cue to clients"

    def pushMeta(
        self,
        groupid: str,
        statusOnly: bool = False,
        keys: Optional[
            List[Any] | Set[Any] | Dict[Any, Any] | Iterable[str]
        ] = None,
    ):
        "Push group metadata"

    def pushEv(self, event: str, target, time_unix=None, value=None, info=""):
        "Tell frontend about event"
