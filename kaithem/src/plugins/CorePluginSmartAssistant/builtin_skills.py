import subprocess
from typing import Any

import num2words

from .skills import SimpleSkillResponse, Skill, available_skills

s = Skill(
    examples=["What's the weather like in georgia?"],
    command="check-weather",
    params=["place"],
)

available_skills.append(s)

s = Skill(
    examples=["What time is it in georgia?", "What's the time in georgia?"],
    command="check-time",
    params=["place"],
)

available_skills.append(s)


class MathSkill(Skill):
    def go(self, *args, context: dict[str, Any]):
        # Trial and error hackery

        expr = " ".join(args)
        expr = expr.replace("×", "*").replace("÷", "/").replace('"', "")
        expr = expr.replace("% *", "/100 *")
        if "(" in expr:
            return SimpleSkillResponse("I don't support parenthesis yet")

        res = eval(expr)
        res = num2words.num2words(res, lang=context.get("lang", "en"))

        return SimpleSkillResponse(f"{expr} is {res}")


s = MathSkill(
    examples=["What is fifty times ten?", "What's 20 percent of 80?"],
    command="calculate",
    params=["expression"],
)
available_skills.append(s)


class UnitSkill(Skill):
    def go(self, *args, context: dict[str, Any]):
        args = list(args)

        if "to" in args:
            args.remove("to")

        if len(args) == 3:
            val = args[0] + args[1]
            unit = args[2]
        elif len(args) == 2:
            val = args[0]
            unit = args[1]

        else:
            return SimpleSkillResponse(
                "I don't understand that unit conversion"
            )

        x = subprocess.check_output(
            ["units", "--terse", "--compact", val, unit]
        ).decode("utf-8")
        x = x.replace("\n", "").replace("\r", "").strip()

        return SimpleSkillResponse(f"{val} is {x}{unit}")


s = UnitSkill(
    examples=[
        "What's 100 grams in pounds?",
        "Convert 90 millimeters to inches",
    ],
    command="unit-convert",
    params=["value", "from", "to"],
)

available_skills.append(s)

s = Skill(
    examples=["Bag bagada boog boo"],
    command="not-understood",
    params=["error message"],
)
available_skills.append(s)
