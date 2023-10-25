import copy
import yaml


def indent(s, prefix="    "):
    s = [prefix + i for i in s.split("\n")]
    return "\n".join(s)


def toPyFile(r):
    r = copy.deepcopy(r)
    "Encode an event resource as a python file"
    s = r["setup"]
    del r["setup"]
    a = r["action"]
    del r["action"]
    t = r["trigger"]
    del r["trigger"]
    d = "## Code outside the data string, and the setup and action blocks is ignored\n"
    d += "## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new\n"

    d += '__data__="""\n'
    d += yaml.dump(r).replace("\\", "\\\\").replace('"""', r'\"""') + '\n"""\n\n'

    # Autoselect what quote to use
    if not "'" in t:
        d += "__trigger__='" + t.replace("\\", "\\\\").replace("'", r"\'") + "'\n\n"
    else:
        d += '__trigger__="' + t.replace("\\", "\\\\").replace('"', r"\"") + '"\n\n'

    d += "if __name__=='__setup__':\n"
    d += indent(s)
    d += "\n\n"

    d += "def eventAction():\n"
    d += indent(a)
    d += "\n"
    return d
