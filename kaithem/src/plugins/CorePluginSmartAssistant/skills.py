from typing import Any, Callable

from jsonschema import Draft7Validator

from . import embeddings


class SkillResponse:
    def __init__(self):
        self.need_confirmation = False

    def execute(self) -> str:
        return "Done"


class Skill:
    def __init__(
        self,
        command: str,
        examples: list[str],
        schema: dict[str, Any],
        handler: Callable[..., str] | None = None,
    ):
        """
        Examples must be a list of strings that show how the command is used, minus any wake
        word part.
        """
        self.examples: list[str] = examples
        self.name: str = command
        self.command: str = command.split(" ")[0]
        self.match_threshold: float = 0.95

        # A string like "foo param1 param2" explaining the command
        self.command_str = command
        self.handler = handler
        self.schema = schema

        self.lookup: embeddings.EmbeddingsLookup | None = None

        self.validator = Draft7Validator(self.schema)

    def do_embeddings(self, model: embeddings.EmbeddingsModel):
        self.lookup = model.get_lookup(list([(i, i) for i in self.examples]))

    def go(
        self,
        context: dict[str, Any],
        **kwargs: Any,
    ) -> SkillResponse:
        if self.handler is None:
            return SimpleSkillResponse(
                f"Sorry, I don't know how to do {self.name}"
            )
        return SimpleSkillResponse(self.handler(*args))


class OptionMatchSkill(Skill):
    """Just a very simple menu option matcher"""

    def __init__(
        self,
        examples: list[str],
        handler: Callable[..., str] | None = None,
        match_threshold: float = 0.95,
    ):
        super().__init__(
            command="", examples=examples, schema={}, handler=handler
        )
        self.name = "not-a-real-skill"
        self.command_str = ""
        self.command = ""
        self.match_threshold = match_threshold


available_skills: list[Skill] = []


class SimpleSkillResponse(SkillResponse):
    def __init__(self, response: str):
        super().__init__()
        self.response: str = response

    def execute(self):
        return self.response
