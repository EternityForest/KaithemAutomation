import subprocess
from typing import Any

import num2words

from .skills import SimpleSkillResponse, Skill, parse_command, skills

s = Skill(
    examples=["What's the weather like in georgia?"],
    command="check-weather",
    params=["place"],
    name="Weather",
)

skills.append(s)

s = Skill(
    examples=["What time is it in georgia?", "What's the time in georgia?"],
    command="check-time",
    params=["place"],
    name="Time",
)

skills.append(s)


class MathSkill(Skill):
    def go(self, query: str, context: dict[str, Any]):
        # Trial and error hackery
        expr = (
            query.split("calculate ")[1]
            .replace("×", "*")
            .replace("÷", "/")
            .replace('"', "")
        )
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
    name="Calculator",
)
skills.append(s)


class UnitSkill(Skill):
    def go(self, query: str, context: dict[str, Any]):
        x = parse_command(query)
        if "to" in x:
            x.remove("to")
        val: str
        unit: str
        print(x)
        if len(x) == 4:
            val = (x[1] + x[2]).replace(" ", "")
            unit = x[3]

        elif len(x) == 3:
            val = x[1].replace(" ", "")
            unit = x[2]

        else:
            return SimpleSkillResponse(
                "Sorry, I don't understand that unit conversion"
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
    name="UnitConverter",
)

skills.append(s)

s = Skill(
    examples=["Bag bagada boog boo"],
    command="not-understood",
    params=["error message"],
    name="BadCommand",
)
skills.append(s)
