"""Usage:

pi_boot_cfg --for=PiTypeName --file=/boot/firmware/config.txt --rm-key=foo --add_key=bar=baz --set_key=foo=bar

"key" is a key as would be found in /boot/firmware/config.txt but with _ instead of -.

--for defaults to the top level, no section.  --file defaults to /boot/firmware/config.txt

Example:

pi_boot_cfg --for=cm4 --set_camera_auto_detect=1


Usage when installed with kaithem

# If you have installed it the default way, this works regardless of username
sudo /home/$(id -nu 1000)/.local/bin/kaithem-pi-boot-cfg --for=cm4 --set_camera_auto_detect=1


"""

import os
import sys

args = {}
file = "/boot/firmware/config.txt"

for i in sys.argv[1:]:
    if i.startswith("--"):
        if "=" in i:
            i = i.split("=")
            args[i[0][2:]] = i[1]
        else:
            args[i[2:]] = ""

file = args.pop("file", file)

if not os.path.isfile(file):
    print(f"File not found: {file}, exiting")
    exit(1)

# Read boot.txt, parse into dicts of line objects indexe by section
config: list[tuple[str, str, list[str]]] = []
section = ("", "", [])
config.append(section)


def is_model(s: str) -> bool:
    """May return false negatve so the filterstack will need an unnecessary all section"""
    return s in [
        "pi1",
        "pi2",
        "pi3",
        "pi4",
        "pi0w1",
        "pi400",
        "pi400w",
        "pi500",
        "cm1",
        "cm3",
        "cm4",
        "cm5",
        "cm4s",
        "pi02",
    ]


with open(file) as f:
    for i in f.readlines():
        i = i.strip()
        if i.startswith("["):
            current_section_accum = section[1]
            new_section_name = i[1:-1]

            # Filter stack simplify stuff.
            # This is not  normal ini file
            if new_section_name.strip() == "all":
                new_section_accum = "all"
            elif is_model(new_section_name) and is_model(current_section_accum):
                # Model resets stack if all that was in the stack was a model
                new_section_accum = new_section_name
            else:
                if current_section_accum:
                    new_section_accum = (
                        current_section_accum + "." + new_section_name
                    )
                else:
                    new_section_accum = new_section_name

            section = (new_section_name, new_section_accum, [])

            config.append(section)

        else:
            section[2].append(i)


def rm_key(section: str, key: str):
    key = key.replace("-", "_")

    lines = []
    for i in config:
        if i[1] == section:
            lines = i[2]
    if not lines:
        return

    for idx, i in enumerate(lines):
        if i.split("=")[0].strip().lower() == key:
            c = 0
            lines.pop(idx)

            # Remove empty lines and comments up to last declaration
            idx -= 1
            while idx:
                if c > 3:
                    break

                if "=" not in lines[idx]:
                    lines.pop(idx)
                    idx -= 1
                    c += 1
                else:
                    break


def add_key(section: str, key: str, value: str):
    key = key.replace("-", "_")
    for i in config:
        if i[1] == section:
            i[2].append(f"{key}={value}")
            return

    current_filter_accum = config[-1][1]

    need_filters = section.split(".")

    incompatible_found = False

    for i in current_filter_accum.split("."):
        if i == "all":
            continue
        # Just a plain model overrides anither model, no need to reset stack
        if is_model(i) and is_model(section):
            continue
        if i not in need_filters:
            incompatible_found = True
        else:
            need_filters.remove(i)

    # reset filter stack
    if incompatible_found:
        config.append(("all", "all", []))
        need_filters = section.split(".")

    for i in need_filters[:-1]:
        config.append((i, f"{current_filter_accum}.{i}", []))
        current_filter_accum = f"{current_filter_accum}.{i}"

    config.append(
        (
            need_filters[-1],
            f"{current_filter_accum}.{need_filters[-1]}",
            [f"{key}={value}"],
        )
    )


def set_key(section: str, key: str, value: str):
    key = key.replace("-", "_")
    rm_key(section, key)
    add_key(section, key, value)


heading = args.pop("for", "")

for i in args:
    if i.startswith("rm_"):
        rm_key(heading, i[3:])
    elif i.startswith("add_"):
        add_key(heading, i[4:], args[i])
    elif i.startswith("set_"):
        set_key(heading, i[4:], args[i])
    else:
        print(f"Unknown command: {i}")

s = ""
for i in config:
    if i[0]:
        s += f"[{i[0]}]\n"

    for j in i[2]:
        s += f"{j}\n"


def main():
    with open(file, "w") as f:
        f.write(s)


if __name__ == "__main__":
    main()
