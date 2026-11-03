import re


def source_json(mapping) -> dict:
    result = {"provider": mapping.provider, "external_id": mapping.external_id, "url": None}
    if mapping.provider == "spotify" and re.fullmatch(r"[A-Za-z0-9]{22}", mapping.external_id):
        result["url"] = f"https://open.spotify.com/{mapping.entity_type}/{mapping.external_id}"
    return result
