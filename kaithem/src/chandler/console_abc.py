from typing import List, Dict, Any


class Console_ABC():
    "Abstract base class for console to make typing easier"

    def linkSend(self, *a: tuple[float | str | None | List[Any] | Dict[str | int, Any]], **k: Dict[str, Any]):
        pass
