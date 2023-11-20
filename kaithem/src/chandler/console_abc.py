from typing import List, Dict, Any, Callable


class Console_ABC():
    "Abstract base class for console to make typing easier"

    def linkSend(self, data: List[Any]):
        pass

    def __init__(self) -> None:
        self.newDataFunctions: List[Callable[..., Any]] = []

