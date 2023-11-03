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
    d = re.sub(r"%"+ tok +r"\s(.+): *$", msub(tok), d, flags=re.MULTILINE)
    d = re.sub(r"%end"+ tok +r"$", esub(tok), d, flags=re.MULTILINE)
    return d

tokens = ['if', 'for']

for i in tokens:
    d= rep(i, d)

d = re.sub(r"%else: *$", "{% else %}", d, flags=re.MULTILINE)

def f(m):
    d = m[1]
    d = re.sub(r"\| *u *$", "| urlencode", d)
    d = re.sub(r"\| *h *$", "| escape", d)

    if not 'for' in d:
        d = "{{ " + d+ " }}"
    else:
        d = "{{ (" + d+ ") }}"

    return d

d = re.sub(r"\$\{(.+?)\}",f, d)




print(d)

with open(sys.argv[1]+".j2", 'w') as f:
    f.write(d)