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


def parity_diff(source_map, target_map):
    """Compare two normalize_objects maps; source is the reference."""
    missing = sorted(k for k in source_map if k not in target_map)
    extra = sorted(k for k in target_map if k not in source_map)
    mismatches = []
    for k in sorted(set(source_map) & set(target_map)):
        for field, sval in source_map[k].items():
            tval = target_map[k].get(field)
            if sval != tval:
                mismatches.append(
                    {"key": k, "field": field, "source": sval, "target": tval})
    return {"missing_on_target": missing, "extra_on_target": extra,
            "field_mismatches": mismatches}


def parity_report(results, meta):
    """Render per-type diffs as a Markdown report ending in RESULT: PASS/FAIL."""
    failed = any(d["missing_on_target"] or d["field_mismatches"]
                 for d in results.values())
    verdict = "FAIL" if failed and meta.get("fail_on") == "missing" else "PASS"
    lines = [
        "# Migration content parity report",
        "",
        f"- Source: {meta.get('source')}",
        f"- Target: {meta.get('target')}",
        f"- Timestamp: {meta.get('timestamp')}",
        f"- Fail mode: {meta.get('fail_on')}",
        "",
        "## Summary",
        "",
        "| Type | Missing on target | Field mismatches | Extra on target |",
        "|---|---|---|---|",
    ]
    for name in sorted(results):
        d = results[name]
        lines.append(
            f"| {name} | {len(d['missing_on_target'])} "
            f"| {len(d['field_mismatches'])} | {len(d['extra_on_target'])} |")
    for name in sorted(results):
        d = results[name]
        lines += ["", f"## {name}", ""]
        if not (d["missing_on_target"] or d["extra_on_target"]
                or d["field_mismatches"]):
            lines.append("Clean.")
            continue
        for k in d["missing_on_target"]:
            lines.append(f"- MISSING on target: `{k}`")
        for m in d["field_mismatches"]:
            lines.append(
                f"- MISMATCH `{m['key']}` field `{m['field']}`: "
                f"source=`{m['source']}` target=`{m['target']}`")
        for k in d["extra_on_target"]:
            lines.append(f"- extra on target (info): `{k}`")
    lines += ["", f"RESULT: {verdict}", ""]
    return "\n".join(lines)


class FilterModule(object):
    def filters(self):
        return {
            "normalize_objects": normalize_objects,
            "parity_diff": parity_diff,
            "parity_report": parity_report,
        }
