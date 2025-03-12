import re
import time
from typing import Any

import ollama


class LLMSession:
    def __init__(self, model: str = "qwen2.5-coder:0.5b"):
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
        q = (
            f"Using these commands: {', '.join([i[0] for i in commands])}, with quoted arguments,\n\n what command should I use for "
            + q
        )
        messages.append({"role": "user", "content": q})

        x = ollama.chat(
            model=self.model,
            messages=messages,
            options={
                "stop": ["```\n\n"],
                "temperature": 0.0,
                "num_predict": 80,
                "top_k": 5,
            },
        )
        m = x["message"]["content"]
        m = re.search(r"```.*\n(.*)\n", m)
        if m:
            x = m.group(1)
        else:
            return None

        for i in sorted(
            commands, key=lambda x: len(x[0].split(" ")[0]), reverse=True
        ):
            if x.strip().startswith(i[0].split(" ")[0]):
                return i[1], x

    def document_rag(self, q: str, c: list[tuple[float, str, str]]) -> str:
        messages = [
            {
                "role": "system",
                "content": """You are Qwen, created by Alibaba Cloud. You are a helpful assistant.""",
            }
        ]

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

        x = ollama.chat(
            model=self.model,
            messages=messages,
            options={"temperature": 0.0, "num_predict": 128, "top_k": 5},
        )

        return x["message"]["content"]
