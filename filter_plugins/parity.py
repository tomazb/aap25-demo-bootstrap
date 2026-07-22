"""Parity comparison filters for AAP migration verification.

Pure functions; no Ansible imports so they are unit-testable with pytest.
"""


def _get(row, dotted_path):
    cur = row
    for part in dotted_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def normalize_objects(rows, key, fields=None, exclude=None):
    """Map raw API rows to {key: {field: value}} for comparison."""
    key_paths = [key] if isinstance(key, str) else list(key)
    fields = fields or {}
    exclude = exclude or {}
    out = {}
    for row in rows or []:
        if any(_get(row, path) in values for path, values in exclude.items()):
            continue
        k = " / ".join(str(_get(row, p)) for p in key_paths)
        out[k] = {name: _get(row, path) for name, path in fields.items()}
    return out


class FilterModule(object):
    def filters(self):
        return {
            "normalize_objects": normalize_objects,
        }
