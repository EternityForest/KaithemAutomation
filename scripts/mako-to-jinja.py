import sys
import re

with open(sys.argv[1]) as f:
    d = f.read()


def msub(tok: str):
    def sub(m: re.Match) -> str:
        return "{% " + tok +" "+ m[1] + " %}"
    return sub


def esub(tok: str):
    def sub(m: re.Match) -> str:
        return "{% end" + tok + " %}"
    return sub


def rep(tok, d):
    d = re.sub(r"%"+ tok +r"\s(.+):$", msub(tok), d, flags=re.MULTILINE)
    d = re.sub(r"%end"+ tok +r"$", esub(tok), d, flags=re.MULTILINE)
    return d

tokens = ['if', 'for']

for i in tokens:
    d= rep(i, d)

d = re.sub(r"%else:$", "{% endif %}", d, flags=re.MULTILINE)

d = re.sub(r"\$\{(.+?)\}", lambda m: "{{ " + m[1] + " }}", d)




print(d)

with open(sys.argv[1]+".jinja2", 'w') as f:
    f.write(d)