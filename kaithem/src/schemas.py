import os
import yaml
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


def get_schema(schemaName: str):
    fn = os.path.join(os.path.dirname(os.path.normpath(__file__)),'schemas', schemaName+".yaml")
    with open(fn) as f:
        return yaml.load(f,Loader=yaml.SafeLoader)


def get_validator(schemaName: str):
    sc = get_schema(schemaName)
    return Draft202012Validator(sc)


def clean_data_inplace(schemaName: str, data: Dict[str, Any], deprecated_only: bool = False):
    "Remove top level keys not in the schema or that are deprecated."

    sc = get_schema(schemaName)

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


def supress_defaults(schemaName: str, data: Dict[str, Any]):
    "Remove top level keys that are the same as the default value in the schema"

    sc = get_schema(schemaName)

    to_remove = []

    # Check for deprecation
    for i in data:
        if (i in sc['properties']) and 'default' in sc['properties'][i]:

            d = sc['properties'][i]['default']
            if d==data[i]:
                to_remove.append(i)

    for i in to_remove:
        data.pop(i)
