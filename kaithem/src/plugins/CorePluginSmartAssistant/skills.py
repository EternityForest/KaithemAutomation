import shlex
from typing import Any, Callable


def parse_command(command: str):
    """Parses a command string with quoted parameters and escape sequences.

    Args:
      command: The command string to parse.

    Returns:
      A list of strings representing the parsed command and its arguments.
    """
    lexer = shlex.shlex(command)
    lexer.whitespace_split = True
    # lexer.escape = True
    return list(lexer)


class SkillResponse:
    def __init__(self):
        self.need_confirmation = False

    def execute(self) -> str:
        return "Done"


class Skill:
    def __init__(
        self,
        examples: list[str],
        params: list[str],
        command: str,
        name: str,
        handler: Callable[..., str] | None = None,
    ):
        """
        Examples must be a list of strings that show how the command is used, minus any wake
        word part.
        """
        self.examples: list[str] = examples
        self.name: str = name
        self.command: str = command

        # A string like "foo param1 param2" explaining the command
        self.command_str = command
        self.handler = handler

        for i in params:
            self.command_str += f' "{i}"'

    def go(self, query: str, context: dict[str, Any]) -> SkillResponse:
        if self.handler is None:
            return SimpleSkillResponse(
                f"Sorry, I don't know how to do {self.name}"
            )
        return SimpleSkillResponse(self.handler(query))


skills: list[Skill] = []


class SimpleSkillResponse(SkillResponse):
    def __init__(self, response: str):
        super().__init__()
        self.response: str = response

    def execute(self):
        return self.response
