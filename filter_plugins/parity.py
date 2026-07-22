"""Parity comparison filters for AAP migration verification.

Pure functions; no Ansible imports so they are unit-testable with pytest.
"""

from urllib.parse import urlsplit, urlunsplit


def resolve_pagination_url(trusted_host, next_value):
    """Return an absolute URL whose scheme/host/port always come from
    trusted_host, using only the path and query of next_value.

    The API's pagination ``next`` link is untrusted input: on AAP it is a
    full absolute URL, and following it verbatim while sending Basic
    credentials could leak them to another origin. This helper keeps the
    origin pinned to trusted_host and forwards only path+query.

    - Empty string or None -> "".
    - A relative path is joined to trusted_host.
    - An absolute next URL contributes only its path and query.
    - Credentials embedded in either value are never propagated.
    - Unsupported/malformed schemes raise ValueError.
    - Query strings are preserved exactly.
    """
    if not next_value:
        return ""
    # Coerce away any Ansible lazy-template proxy so urlsplit parses correctly.
    trusted_host = str(trusted_host)
    next_value = str(next_value)
    th = urlsplit(trusted_host)
    if th.scheme not in ("http", "https") or not th.hostname:
        raise ValueError(
            "trusted_host must be an absolute http(s) URL, got %r" % (trusted_host,))
    nv = urlsplit(next_value)
    if nv.scheme and nv.scheme not in ("http", "https"):
        raise ValueError(
            "unsupported scheme in pagination link: %r" % (nv.scheme,))
    # Origin is always taken from trusted_host; hostname/port only (drop creds).
    netloc = th.hostname
    if th.port:
        netloc = "%s:%d" % (th.hostname, th.port)
    path = nv.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    # Collapse duplicate slashes in the path only (never in the query).
    while "//" in path:
        path = path.replace("//", "/")
    return urlunsplit((th.scheme, netloc, path, nv.query, ""))


def _get(row, dotted_path):
    cur = row
    for part in dotted_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _normalize_with_dupes(rows, key, fields=None, exclude=None):
    """Core normalizer. Returns (map, duplicate_keys).

    A None key segment renders as "" so a missing org qualifier never collides
    with a literal string, and duplicates are reported rather than silently
    overwritten (last-row-wins would hide missing resources).
    """
    key_paths = [key] if isinstance(key, str) else list(key)
    fields = fields or {}
    exclude = exclude or {}
    out = {}
    dupes = []
    for row in rows or []:
        if any(_get(row, path) in values for path, values in exclude.items()):
            continue
        parts = []
        for p in key_paths:
            v = _get(row, p)
            parts.append("" if v is None else str(v))
        k = " / ".join(parts)
        if k in out and k not in dupes:
            dupes.append(k)
        out[k] = {name: _get(row, path) for name, path in fields.items()}
    return out, sorted(dupes)


def normalize_objects(rows, key, fields=None, exclude=None):
    """Map raw API rows to {key: {field: value}}; raise on duplicate keys."""
    out, dupes = _normalize_with_dupes(rows, key, fields, exclude)
    if dupes:
        raise ValueError("duplicate normalized keys: " + ", ".join(dupes))
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


def _empty_result():
    return {"missing_on_target": [], "extra_on_target": [],
            "field_mismatches": [], "errors": []}


def parity_compare(source_rows, target_rows, spec):
    """Compare one object type. spec may carry separate source/target key and
    field maps (source API shapes differ from target). Returns the standard
    per-type result schema with an ``errors`` list for operational problems
    (duplicate normalized keys). Never raises."""
    result = _empty_result()
    skey = spec.get("source_key") or spec.get("key")
    tkey = spec.get("target_key") or spec.get("key")
    sfields = spec.get("source_fields") or spec.get("fields") or {}
    tfields = spec.get("target_fields") or spec.get("fields") or {}
    exclude = spec.get("exclude") or {}
    smap, sdup = _normalize_with_dupes(source_rows, skey, sfields, exclude)
    tmap, tdup = _normalize_with_dupes(target_rows, tkey, tfields, exclude)
    for k in sdup:
        result["errors"].append("duplicate normalized key on source: %s" % k)
    for k in tdup:
        result["errors"].append("duplicate normalized key on target: %s" % k)
    diff = parity_diff(smap, tmap)
    result["missing_on_target"] = diff["missing_on_target"]
    result["extra_on_target"] = diff["extra_on_target"]
    result["field_mismatches"] = diff["field_mismatches"]
    return result


def parity_error_result(message):
    """Build a per-type result carrying a single operational error."""
    r = _empty_result()
    r["errors"] = [message]
    return r


def parity_failed(results, fail_on):
    """Exit-code decision for a whole parity run.

    Operational errors (errors list non-empty, including truncation and
    duplicate keys) ALWAYS fail, in every mode. Content policy:
      missing -> fail on missing source objects (mismatches are report-only)
      drift   -> fail on missing OR field mismatches
      none    -> content differences tolerated
    An empty results set fails (nothing was verified).
    """
    if not results:
        return True
    if any(d.get("errors") for d in results.values()):
        return True
    if fail_on == "none":
        return False
    missing = any(d.get("missing_on_target") for d in results.values())
    if fail_on == "missing":
        return missing
    if fail_on == "drift":
        drift = any(d.get("field_mismatches") for d in results.values())
        return missing or drift
    # Unknown mode is itself a failure (should be rejected earlier).
    return True


def parity_report(results, meta):
    """Render per-type results as Markdown ending in RESULT: PASS/FAIL.

    Operational errors are listed before content differences and always drive
    the verdict to FAIL regardless of fail mode.
    """
    fail_on = meta.get("fail_on")
    verdict = "FAIL" if parity_failed(results, fail_on) else "PASS"
    op_error_types = sorted(
        name for name, d in results.items() if d.get("errors"))
    lines = [
        "# Migration content parity report",
        "",
        f"- Source: {meta.get('source')}",
        f"- Target: {meta.get('target')}",
        f"- Timestamp: {meta.get('timestamp')}",
        f"- Fail mode: {fail_on}",
        "",
        "## Summary",
        "",
        "| Type | Errors | Missing on target | Field mismatches | Extra on target |",
        "|---|---|---|---|---|",
    ]
    for name in sorted(results):
        d = results[name]
        lines.append(
            f"| {name} | {len(d.get('errors', []))} "
            f"| {len(d['missing_on_target'])} "
            f"| {len(d['field_mismatches'])} | {len(d['extra_on_target'])} |")
    if op_error_types:
        lines += ["", "## Operational errors (always fail)", ""]
        for name in op_error_types:
            for e in results[name]["errors"]:
                lines.append(f"- `{name}`: {e}")
    for name in sorted(results):
        d = results[name]
        lines += ["", f"## {name}", ""]
        if not (d["missing_on_target"] or d["extra_on_target"]
                or d["field_mismatches"] or d.get("errors")):
            lines.append("Clean.")
            continue
        for e in d.get("errors", []):
            lines.append(f"- ERROR: {e}")
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
            "resolve_pagination_url": resolve_pagination_url,
            "normalize_objects": normalize_objects,
            "parity_diff": parity_diff,
            "parity_compare": parity_compare,
            "parity_error_result": parity_error_result,
            "parity_failed": parity_failed,
            "parity_report": parity_report,
        }
