import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "filter_plugins"))

from parity import normalize_objects, parity_diff, parity_report


def test_normalize_simple_key_and_fields():
    rows = [
        {"name": "Demo Linux", "description": "x",
         "summary_fields": {"organization": {"name": "Org A"}}},
    ]
    out = normalize_objects(
        rows, key="name",
        fields={"organization": "summary_fields.organization.name"})
    assert out == {"Demo Linux": {"organization": "Org A"}}


def test_normalize_compound_key():
    rows = [{"name": "web01", "summary_fields": {"inventory": {"name": "Inv"}}}]
    out = normalize_objects(rows, key=["summary_fields.inventory.name", "name"])
    assert list(out) == ["Inv / web01"]


def test_normalize_missing_path_is_none():
    out = normalize_objects([{"name": "a"}], key="name", fields={"image": "image"})
    assert out["a"]["image"] is None


def test_normalize_exclude():
    rows = [{"name": "smart", "kind": "smart"}, {"name": "plain", "kind": ""}]
    out = normalize_objects(rows, key="name", exclude={"kind": ["smart", "constructed"]})
    assert list(out) == ["plain"]


def test_diff_missing_extra_mismatch():
    src = {"a": {"f": 1}, "b": {"f": 2}, "c": {"f": 3}}
    tgt = {"a": {"f": 1}, "c": {"f": 9}, "d": {"f": 4}}
    d = parity_diff(src, tgt)
    assert d["missing_on_target"] == ["b"]
    assert d["extra_on_target"] == ["d"]
    assert d["field_mismatches"] == [
        {"key": "c", "field": "f", "source": 3, "target": 9}]


def test_diff_clean():
    d = parity_diff({"a": {}}, {"a": {}})
    assert d == {"missing_on_target": [], "extra_on_target": [],
                 "field_mismatches": []}


def test_report_fail_and_pass():
    results = {"projects": {"missing_on_target": ["P1"], "extra_on_target": [],
                            "field_mismatches": [], "errors": []}}
    meta = {"source": "s", "target": "t", "timestamp": "T", "fail_on": "missing"}
    md = parity_report(results, meta)
    assert "RESULT: FAIL" in md and "P1" in md and "projects" in md
    meta["fail_on"] = "none"
    assert "RESULT: PASS" in parity_report(results, meta)
    clean = {"projects": {"missing_on_target": [], "extra_on_target": [],
                          "field_mismatches": [], "errors": []}}
    meta["fail_on"] = "missing"
    assert "RESULT: PASS" in parity_report(clean, meta)


# --- resolve_pagination_url -------------------------------------------------

from parity import resolve_pagination_url

HOST = "https://target.example.com"


def test_resolve_initial_relative_path():
    assert resolve_pagination_url(
        HOST, "/api/v2/organizations/?page_size=200") \
        == "https://target.example.com/api/v2/organizations/?page_size=200"


def test_resolve_relative_next_path():
    assert resolve_pagination_url(HOST, "/api/v2/hosts/?page=2") \
        == "https://target.example.com/api/v2/hosts/?page=2"


def test_resolve_absolute_next_uses_trusted_host():
    # DRF returns an absolute URL for next; only its path+query may be used.
    got = resolve_pagination_url(
        HOST, "https://target.example.com/api/v2/hosts/?page=3")
    assert got == "https://target.example.com/api/v2/hosts/?page=3"


def test_resolve_absolute_next_different_host_is_pinned():
    # A hostile/different host in next must not redirect Basic credentials.
    got = resolve_pagination_url(
        HOST, "https://attacker.evil/api/v2/hosts/?page=2")
    assert got == "https://target.example.com/api/v2/hosts/?page=2"
    assert "attacker.evil" not in got


def test_resolve_protocol_relative_next_is_pinned():
    # Protocol-relative next links are untrusted and must not change origin.
    got = resolve_pagination_url(
        HOST, "//attacker.evil/api/v2/x/?page=2")
    assert got == "https://target.example.com/api/v2/x/?page=2"
    assert "attacker.evil" not in got


def test_resolve_absolute_next_with_port_pins_trusted_port():
    got = resolve_pagination_url(
        "https://target.example.com:8443",
        "https://target.example.com:9999/api/v2/x/?page=2")
    assert got == "https://target.example.com:8443/api/v2/x/?page=2"


def test_resolve_drops_embedded_credentials():
    got = resolve_pagination_url(
        HOST, "https://user:secret@attacker.evil/api/v2/x/?page=2")
    assert "secret" not in got and "user" not in got and "attacker" not in got
    assert got == "https://target.example.com/api/v2/x/?page=2"


def test_resolve_null_next_returns_empty():
    assert resolve_pagination_url(HOST, None) == ""


def test_resolve_empty_next_returns_empty():
    assert resolve_pagination_url(HOST, "") == ""


def test_resolve_unsupported_scheme_raises():
    import pytest
    with pytest.raises(ValueError):
        resolve_pagination_url(HOST, "ftp://target.example.com/x/")


def test_resolve_bad_trusted_host_raises():
    import pytest
    with pytest.raises(ValueError):
        resolve_pagination_url("not-a-url", "/api/v2/x/")


def test_resolve_preserves_encoded_query():
    got = resolve_pagination_url(
        HOST, "/api/v2/x/?name=a%20b&kind=smart")
    assert got == "https://target.example.com/api/v2/x/?name=a%20b&kind=smart"


def test_resolve_collapses_duplicate_slashes_in_path_only():
    got = resolve_pagination_url(HOST, "/api//v2///x/?a=b//c")
    assert got == "https://target.example.com/api/v2/x/?a=b//c"


# --- duplicate detection, compare, and fail modes ---------------------------

from parity import parity_compare, parity_failed, parity_error_result


def test_normalize_objects_raises_on_duplicate():
    import pytest
    rows = [{"name": "dup", "organization": "A"},
            {"name": "dup", "organization": "B"}]
    with pytest.raises(ValueError):
        normalize_objects(rows, key="name")


def test_compound_key_keeps_same_name_distinct_across_orgs():
    rows = [
        {"name": "Deploy", "summary_fields": {"organization": {"name": "Org A"}}},
        {"name": "Deploy", "summary_fields": {"organization": {"name": "Org B"}}},
    ]
    out = normalize_objects(
        rows, key=["summary_fields.organization.name", "name"])
    assert set(out) == {"Org A / Deploy", "Org B / Deploy"}


def test_compare_detects_duplicate_as_error():
    src = [{"name": "x", "org": "A"}, {"name": "x", "org": "B"}]
    tgt = [{"name": "x", "org": "A"}]
    spec = {"key": "name"}
    r = parity_compare(src, tgt, spec)
    assert any("duplicate" in e for e in r["errors"])


def test_compare_separate_source_target_keys_and_fields():
    # Source exposes org via a different path than target.
    src = [{"name": "P", "org_name": "A", "branch": "main"}]
    tgt = [{"name": "P",
            "summary_fields": {"organization": {"name": "A"}}, "branch": "dev"}]
    spec = {
        "source_key": ["org_name", "name"],
        "target_key": ["summary_fields.organization.name", "name"],
        "source_fields": {"branch": "branch"},
        "target_fields": {"branch": "branch"},
    }
    r = parity_compare(src, tgt, spec)
    assert r["missing_on_target"] == []
    assert r["field_mismatches"] == [
        {"key": "A / P", "field": "branch", "source": "main", "target": "dev"}]


def test_compare_missing_and_extra():
    src = [{"name": "a"}, {"name": "b"}]
    tgt = [{"name": "a"}, {"name": "c"}]
    r = parity_compare(src, tgt, {"key": "name"})
    assert r["missing_on_target"] == ["b"]
    assert r["extra_on_target"] == ["c"]
    assert r["errors"] == []


def _res(missing=None, mismatch=None, errors=None):
    return {"missing_on_target": missing or [], "extra_on_target": [],
            "field_mismatches": mismatch or [], "errors": errors or []}


def test_fail_modes_missing():
    r = {"t": _res(missing=["x"])}
    assert parity_failed(r, "missing") is True
    assert parity_failed({"t": _res(mismatch=[{"key": "x"}])}, "missing") is False


def test_fail_modes_drift():
    assert parity_failed({"t": _res(mismatch=[{"key": "x"}])}, "drift") is True
    assert parity_failed({"t": _res(missing=["x"])}, "drift") is True
    assert parity_failed({"t": _res()}, "drift") is False


def test_fail_modes_none_tolerates_content_but_not_errors():
    assert parity_failed({"t": _res(missing=["x"], mismatch=[{"k": 1}])}, "none") is False
    assert parity_failed({"t": _res(errors=["boom"])}, "none") is True


def test_operational_error_fails_every_mode():
    for mode in ("missing", "drift", "none"):
        assert parity_failed({"t": _res(errors=["op"])}, mode) is True


def test_empty_results_fails():
    assert parity_failed({}, "none") is True


def test_error_result_helper():
    r = parity_error_result("no source rows")
    assert r["errors"] == ["no source rows"]
    assert parity_failed({"t": r}, "none") is True


def test_report_lists_operational_errors_section():
    results = {"projects": parity_error_result("source retrieval failed: HTTP 500")}
    md = parity_report(results, {"fail_on": "none", "source": "s",
                                 "target": "t", "timestamp": "T"})
    assert "Operational errors" in md
    assert "HTTP 500" in md
    assert "RESULT: FAIL" in md
