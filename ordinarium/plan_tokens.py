import json


def normalize_plan_token(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return f"text:{int(value)}"
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if ":" in raw:
            return raw
        if raw.isdigit():
            return f"text:{raw}"
    return None


def parse_plan_tokens(raw):
    if not raw:
        return []
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    tokens = []
    for value in data:
        token = normalize_plan_token(value)
        if token:
            tokens.append(token)
    return tokens


def parse_json_object(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
