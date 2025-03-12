from typing import Any

import num2words

from .skills import SimpleSkillResponse, Skill, available_skills


class MathSkill(Skill):
    def go(self, a, operator, b, context: dict[str, Any]):
        # Trial and error hackery

        expr = str(a) + operator + str(b)
        expr = expr.replace("×", "*").replace("÷", "/").replace('"', "")
        expr = expr.replace("% *", "/100 *")
        if "(" in expr:
            return SimpleSkillResponse("I don't support parenthesis yet")

        res = eval(expr)
        res = num2words.num2words(res, lang=context.get("lang", "en"))
        expr = (
            expr.replace("*", " times ")
            .replace("+", " plus ")
            .replace("-", " minus ")
            .replace("/", " divided by ")
        )
        return SimpleSkillResponse(f"{expr} is {res}")


s = MathSkill(
    examples=["What is fifty times ten?", "What's 20 percent of 80?"],
    command="calculate",
    schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "const": "calculate"},
            "a": {"type": "number"},
            "operator": {"type": "string", "enum": ["+", "-", "*", "/"]},
            "b": {"type": "number"},
        },
        "required": ["a", "operator", "b", "command"],
    },
)
available_skills.append(s)


s = Skill(
    examples=[
        "Where is Georgia?",
        "Who discovered Fluorine?",
        "Where is the Eiffel Tower?",
        "How many states are there in the US?",
        "How tall is Mount Everest?",
    ],
    command="knowledge-search",
    schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "const": "knowledge-search"},
            "query": {"type": "string"},
        },
        "required": ["command", "summary"],
    },
)
available_skills.append(s)

# class UnitSkill(Skill):
#     def go(self, *args, context: dict[str, Any]):
#         args = list(args)

#         if "to" in args:
#             args.remove("to")

#         if len(args) == 3:
#             val = args[0] + args[1]
#             unit = args[2]
#         elif len(args) == 2:
#             val = args[0]
#             unit = args[1]

#         else:
#             return SimpleSkillResponse(
#                 "I don't understand that unit conversion"
#             )

#         x = subprocess.check_output(
#             ["units", "--terse", "--compact", val, unit]
#         ).decode("utf-8")
#         x = x.replace("\n", "").replace("\r", "").strip()

#         return SimpleSkillResponse(f"{val} is {x}{unit}")


# s = UnitSkill(
#     examples=[
#         "What's 100 grams in pounds?",
#         "Convert 90 millimeters to inches",
#     ],
#     command="unit-convert",
#     params=["value", "from", "to"],
# )

# available_skills.append(s)
