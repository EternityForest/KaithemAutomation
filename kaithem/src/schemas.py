# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import json
import os
from functools import cache
from typing import Any, Dict

import yaml
from jsonschema import Draft202012Validator, validators


def json_roundtrip(d):
    # Python converts int dict keys to strings.
    # We avoid undefined behavior by first serializing as
    # a canonical JSON
    return json.loads(json.dumps(d))


def extend_with_default(validator_class):
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator, properties, instance, schema):
        for property, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(property, subschema["default"])

        yield from validate_properties(
            validator,
            properties,
            instance,
            schema,
        )

    return validators.extend(
        validator_class,
        {"properties": set_defaults},
    )


DefaultValidatingValidator = extend_with_default(Draft202012Validator)


@cache
def get_schema(schemaName: str):
    fn = os.path.join(
        os.path.dirname(os.path.normpath(__file__)),
        "schemas",
        schemaName + ".yaml",
    )
    with open(fn) as f:
        return yaml.load(f, Loader=yaml.SafeLoader)


def get_validator(schemaName: str):
    sc = get_schema(schemaName)
    return Draft202012Validator(sc)


def validate(schemaName: str, data: Any):
    data = json_roundtrip(data)
    get_validator(schemaName).validate(data)


def clean_data_inplace(
    schemaName: str, data: Dict[str, Any], deprecated_only: bool = False
):
    "Remove top level keys not in the schema or that are deprecated."

    sc = get_schema(schemaName)

    to_remove = []

    if not deprecated_only:
        if not sc.get("additionalProperties", True):
            for i in data:
                if i not in sc["properties"]:
                    # print(f"Removing property not in schema {i}")
                    to_remove.append(i)

    # Check for deprecation
    for i in data:
        if (i in sc["properties"]) and sc["properties"][i].get(
            "deprecated", False
        ):
            # print(f"Removing deprecated property {i}")
            to_remove.append(i)

    for i in to_remove:
        data.pop(i)


def suppress_defaults(schemaName: str, data: Dict[str, Any]):
    "Remove top level keys that are the same as the default value in the schema"

    sc = get_schema(schemaName)

    to_remove = []

    # Check for deprecation
    for i in data:
        if (i in sc["properties"]) and "default" in sc["properties"][i]:
            d = sc["properties"][i]["default"]
            if d == data[i]:
                to_remove.append(i)

    for i in to_remove:
        data.pop(i)
