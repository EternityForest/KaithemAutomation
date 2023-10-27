import os
import json
from jsonschema import Draft202012Validator, validators
from typing import Dict, Any

def extend_with_default(validator_class):
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator, properties, instance, schema):
        for property, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(property, subschema["default"])

        for error in validate_properties(
            validator, properties, instance, schema,
        ):
            yield error

    return validators.extend(
        validator_class, {"properties": set_defaults},
    )


DefaultValidatingValidator = extend_with_default(Draft202012Validator)


def get_validator(schemaName: str):
    fn = os.path.join(os.path.dirname(os.path.normpath(__file__)),'schemas', schemaName+".json")
    with open(fn) as f:
        return DefaultValidatingValidator(json.load(f))


def clean_data_inplace(schemaName: str, data: Dict[str, Any], deprecated_only: bool = False):
    "Remove top level keys not in the schema or that are deprecated."

    fn = os.path.join(os.path.dirname(os.path.normpath(__file__)),'schemas', schemaName+".json")
    with open(fn) as f:
        sc = json.load(f)

    to_remove = []

    if not deprecated_only:
        if not sc.get('additionalProperties', True):
            for i in data:
                if i not in sc['properties']:
                    # print(f"Removing property not in schema {i}")
                    to_remove.append(i)

    # Check for deprecation
    for i in data:
        if (i in sc['properties']) and sc['properties'][i].get('deprecated', False):
            # print(f"Removing deprecated property {i}")
            to_remove.append(i)

    for i in to_remove:
        data.pop(i)

