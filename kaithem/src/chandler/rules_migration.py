# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-or-later

"""Migration from old nested list format to new dict-based rules format.

Old format: [["event", [["command", "arg1", "arg2"]]]]
New format: [{"event": "event", "actions": [{"command": "cmd", "arg1": "val", "arg2": "val2"}]}]
"""

import inspect
from typing import Any


def is_old_format(rules: Any) -> bool:
    """Detect if rules are in old nested list format vs new dict format.

    Args:
        rules: Rules data to check

    Returns:
        True if old list format, False if new dict format or unknown
    """
    if not isinstance(rules, list):
        return False
    if not rules:
        return False  # Empty list valid for both formats

    first = rules[0]

    # Old format: first element is [str, [[str, str, ...]]]
    if isinstance(first, list) and len(first) == 2:
        if isinstance(first[0], str) and isinstance(first[1], list):
            return True

    # New format: first element is dict with "event" and "actions" keys
    if isinstance(first, dict) and "event" in first and "actions" in first:
        return False

    return False  # Unknown format, treat as new


def migrate_rules_to_new_format(old_rules: list[list]) -> list[dict[str, Any]]:
    """Convert old nested list format to new dict format.

    Args:
        old_rules: Rules in old format [["event", [["cmd", "arg1"], ...]]]

    Returns:
        Rules in new format [{"event": "event", "actions": [...]}]
    """
    new_rules = []

    for binding in old_rules:
        if not isinstance(binding, list) or len(binding) != 2:
            continue

        event_name = binding[0]
        commands = binding[1]

        if not isinstance(commands, list):
            continue

        actions = []
        for cmd in commands:
            if not isinstance(cmd, list) or len(cmd) == 0:
                continue

            cmd_name = cmd[0]
            args = cmd[1:]

            # Get arg names for this command
            arg_names = get_arg_names_for_command(cmd_name)

            action = {"command": cmd_name}
            # Map positional args to named args
            for i, arg_name in enumerate(arg_names):
                if i < len(args):
                    action[arg_name] = args[i]

            actions.append(action)

        new_rules.append({"event": event_name, "actions": actions})

    return new_rules


def get_arg_names_for_command(cmd_name: str) -> list[str]:
    """Get parameter names for a command by introspecting its function.

    Args:
        cmd_name: Name of the command

    Returns:
        List of parameter names in order
    """
    # Handle special built-in commands
    special_args = {
        "set": ["variable", "value"],
        "pass": [],
        "maybe": ["chance"],
        "continue_if": ["condition"],
    }

    if cmd_name in special_args:
        return special_args[cmd_name]

    # Try to get the function from rootContext
    try:
        from . import groups as _groups

        cmd = _groups.rootContext.commands.get(cmd_name)
        if cmd:
            return _get_function_arg_names(cmd)
    except Exception:
        pass

    # Unknown command, return empty list
    return []


def _get_function_arg_names(f) -> list[str]:
    """Extract parameter names from a function.

    Args:
        f: Function or FunctionBlock class

    Returns:
        List of parameter names (excluding self)
    """
    from . import scriptbindings

    # Handle FunctionBlock classes
    if isinstance(f, type) and issubclass(f, scriptbindings.FunctionBlock):
        f = f.__call__

    try:
        sig = inspect.signature(f)
        result = []
        for p_name, param in sig.parameters.items():
            # Skip self parameter
            if p_name == "self":
                continue
            # Skip *args and **kwargs
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            result.append(p_name)
        return result
    except Exception:
        return []
