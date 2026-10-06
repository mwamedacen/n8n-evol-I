"""Resolve {{INTERPOLATE_uuid:identifier}} (alias `{{@uuid:identifier}}`) placeholders with fresh UUIDs."""
import re
import uuid

PATTERN = re.compile(r"\{\{(?:INTERPOLATE_|@)uuid:([^}]+)\}\}")


def resolve(text: str, namespace: str | None = None) -> str:
    """Replace each {{INTERPOLATE_uuid:identifier}} / {{@uuid:identifier}} with a fresh UUID v4.

    Each unique identifier gets one consistent UUID within a single resolve call.
    Different identifiers always get different UUIDs.
    """
    seen: dict[str, str] = {}

    def _replace(match: re.Match) -> str:
        identifier = match.group(1).strip()
        if identifier not in seen:
            seen[identifier] = str(uuid.uuid5(uuid.NAMESPACE_URL, namespace + ':' + identifier) if namespace else uuid.uuid4())
        return seen[identifier]

    return PATTERN.sub(_replace, text)
