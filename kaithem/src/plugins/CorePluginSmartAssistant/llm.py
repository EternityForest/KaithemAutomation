import json
import time
from typing import Any

import ollama


class LLMSession:
    def __init__(self, model: str = "Gemma3:1b"):
        self.model: str = model

    def find_command(
        self, q: str, commands: list[tuple[str, Any]]
    ) -> tuple[Any, list[str]] | None:
        """
        Commands must be a list of commands with params, like "check-time <place>"
        Tuples will be the object part of the input plus all the arguments
        parsed out.
        """
        messages = []
        print(f"{q}\n\n")
        q = f"""The available commands are:
{'\n'.join([i[0] for i in commands])}

Using JSON format, and converting all numbers to decimal,

{q}
"""
        messages.append({"role": "user", "content": q})
        schema = {"anyOf": list(i[1].schema for i in commands)}

        x = ollama.chat(
            model=self.model,
            messages=messages,
            format=schema,
            options={
                "stop": ["```\n\n"],
                "temperature": 0.0,
                "num_predict": 80,
                "top_k": 5,
            },
        )
        m = x["message"]["content"]
        print(m)
        # Common LLM errors
        m = (
            m.replace(':  , "', ':  "')
            .replace("```json\n", "")
            .replace("\n```", "")
        )
        j = json.loads(m)

        for i in sorted(
            commands, key=lambda x: len(x[0].split(" ")[0]), reverse=True
        ):
            if j["command"] == i[0].split(" ")[0]:
                j.pop("command")
                return i[1], j

    def document_rag(self, q: str, c: list[tuple[float, str, str]]) -> str:
        # messages = [
        #     {
        #         "role": "system",
        #         "content": """You are Qwen, created by Alibaba Cloud. You are a helpful assistant.""",
        #     }
        # ]
        messages = []

        messages.append(
            {
                "role": "tool",
                "content": "It is "
                + time.strftime("%I:%M%p on %A, %B %e, %Y", time.localtime()),
            }
        )

        for i in c:
            print(f"{i[1]} ({i[0]}):\n{i[2]}\n\n")
            messages.append({"role": "tool", "content": i[1] + ": " + i[2]})

        messages.append({"role": "user", "content": "Query:" + q})
        # x= ollama.chat(model='qwen2.5-coder:0.5b', messages=messages, options={"temperature": 0.4, "num_predict": 480, "top_k": 5})

        for i in range(4):
            try:
                x = ollama.chat(
                    model=self.model,
                    messages=messages,
                    options={
                        "temperature": 0.0,
                        "num_predict": 96,
                        "top_k": 5,
                    },
                )

                return x["message"]["content"]
            except Exception as e:
                if i == 3:
                    raise e


# x = LLMSession()
# c = [
#     ("calculate <a> <operator> <b>", "2 + 2"),
#     ("check-time 'Bakersfield'", "time"),
#     ("check-weather <place>", "cw"),
#     ("check-oil-prices <place>", "cop"),
#     ("search-knowledge 'Where is mount everest' ", "sk"),
#     ("web-search <query>", "lu"),
#     ("translate <language> '<text>' ", "translate"),
#     ("report-unknown-request <text>", "fh"),
#     ("cant-do-that <text>", "cdt"),
# ]

# print(x.find_command("what is nine times eighty one", c))
# print(x.find_command("what is nine time ninety one", c))

# print(x.find_command("Turn on the lights", c))
# print(x.find_command("Launch a rocket", c))

# print(x.find_command("Translate lets buy a hat to french", c))

# print(x.find_command("Print hello world", c))
# print(x.find_command("Get the time in fiji", c))
# print(x.find_command("what is nine times five", c))
# print(x.find_command("Where is the capital of canada", c))
# x = LLMSession()
# c = [
#     ("hello-world", "hello"),
#     ("calculate <expression>", "2 + 2"),
#     ("check-time 'Bakersfield'", "time"),
#     ("check-weather <place>", "cw"),
#     ("check-oil-prices <place>", "cop"),
#     ("search-knowledge 'Where is mount everest' ", "sk"),
#     ("web-search <query>", "lu"),
#     ("translate <language> '<text>' ", "translate"),
#     ("report-unknown-request <text>", "fh"),
#     ("cant-do-that <text>", "cdt"),
# ]
