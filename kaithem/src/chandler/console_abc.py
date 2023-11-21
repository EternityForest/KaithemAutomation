from typing import List, Dict, Any, Callable, Optional, Set


class Console_ABC():
    "Abstract base class for console to make typing easier"

    def linkSend(self, data: List[Any]):
        pass

    def __init__(self) -> None:
        self.newDataFunctions: List[Callable[..., Any]] = []

    def pushCueMeta(self, cueid: str):
        "Push all metadata about the cue to the clients"
        pass

    def pushCueData(self, cueid: str):
        "Push lighting values for cue to clients"
        pass

    def pushMeta(self, sceneid: str, statusOnly: bool = False, keys: Optional[List[Any] | Set[Any] | Dict[Any, Any]] = None):
        "Push scene metadata"
        pass
