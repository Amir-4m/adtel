import jsonschema
from django.core.exceptions import ValidationError


def validate_link_utm(value):
    schema = {
        "type": "object",
        "properties": {
            "link": {
                "type": "string",
                "pattern": r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            },
            "utm_source": {"type": "string"},
            "utm_campaign": {"type": ["string", "number"]},
            "utm_content": {"type": ["string", "number"]},
            "utm_medium": {"type": ["string", "number"]},
            "utm_term": {"type": ["string", "number"]},
        },
        "additionalProperties": False
    }

    try:
        jsonschema.validate(value, schema)
    except jsonschema.ValidationError as e:
        raise ValidationError(e.message)
