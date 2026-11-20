import json
from pathlib import Path

path = Path("C:/doc/project/UnifiedMessagesManagement/contracts/openapi.json")
document = json.loads(path.read_text(encoding="utf-8"))
schemas = document["components"]["schemas"]
errors = []


def deref(schema):
    if "$ref" in schema:
        prefix = "#/components/schemas/"
        if not schema["$ref"].startswith(prefix):
            raise AssertionError(f"unsupported ref: {schema['$ref']}")
        return schemas[schema["$ref"][len(prefix):]]
    return schema


def union_properties(schema):
    schema = deref(schema)
    if "allOf" in schema:
        merged = {}
        for item in schema["allOf"]:
            merged.update(union_properties(item))
        merged.update(schema.get("properties", {}))
        return merged
    return dict(schema.get("properties", {}))


def union_required(schema):
    schema = deref(schema)
    if "allOf" in schema:
        required = []
        for item in schema["allOf"]:
            required.extend(union_required(item))
        required.extend(schema.get("required", []))
        return set(required)
    return set(schema.get("required", []))


def check_type(value, expected, label):
    options = expected if isinstance(expected, list) else [expected]
    valid = False
    for option in options:
        if option == "string":
            valid = valid or isinstance(value, str)
        elif option == "integer":
            valid = valid or (isinstance(value, int) and not isinstance(value, bool))
        elif option == "boolean":
            valid = valid or isinstance(value, bool)
        elif option == "object":
            valid = valid or isinstance(value, dict)
        elif option == "array":
            valid = valid or isinstance(value, list)
        elif option == "null":
            valid = valid or value is None
    if not valid:
        errors.append(f"{label}: expected {expected}, got {type(value).__name__}")


def validate(value, schema, label):
    schema = deref(schema)
    if "allOf" in schema:
        for item in schema["allOf"]:
            validate(value, item, label)
        allowed = union_properties(schema)
        for key in union_required(schema):
            if key not in value:
                errors.append(f"{label}.{key}: missing required field")
        if schema.get("unevaluatedProperties") is False:
            for key in value:
                if key not in allowed:
                    errors.append(f"{label}.{key}: unexpected field")
        return
    expected_type = schema.get("type")
    if expected_type:
        check_type(value, expected_type, label)
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{label}: {value!r} not in enum {schema['enum']}")
    if isinstance(value, int) and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{label}: below minimum {schema['minimum']}")
    if isinstance(value, str) and "minLength" in schema and len(value) < schema["minLength"]:
        errors.append(f"{label}: shorter than minLength {schema['minLength']}")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{label}.{key}: missing required field")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{label}.{key}: unexpected field")
        for key, child in value.items():
            if key in properties:
                validate(child, properties[key], f"{label}.{key}")
    if isinstance(value, list) and "items" in schema:
        for index, child in enumerate(value):
            validate(child, schema["items"], f"{label}[{index}]")


def operation_example(path_name, method, status):
    return document["paths"][path_name][method]["responses"][status]["content"]["application/json"]["example"]


checks = [
    ("MessagePage", operation_example("/api/v1/messages", "get", "200")),
    ("MessageDetail", operation_example("/api/v1/messages/{messageId}", "get", "200")),
    ("UnifiedMessage", operation_example("/api/v1/messages/{messageId}/process", "post", "200")),
    ("TodoPage", operation_example("/api/v1/todos", "get", "200")),
]
for name, example in checks:
    validate(example, schemas[name], name)

if errors:
    print("OpenAPI example validation failed")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)
print("OpenAPI examples schema validation passed: 4/4")
