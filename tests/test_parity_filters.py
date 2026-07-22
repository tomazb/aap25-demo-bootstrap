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
    results = {"projects": {"missing_on_target": ["P1"],
                            "extra_on_target": [], "field_mismatches": []}}
    meta = {"source": "s", "target": "t", "timestamp": "T", "fail_on": "missing"}
    md = parity_report(results, meta)
    assert "RESULT: FAIL" in md and "P1" in md and "projects" in md
    meta["fail_on"] = "none"
    assert "RESULT: PASS" in parity_report(results, meta)
    clean = {"projects": {"missing_on_target": [], "extra_on_target": [],
                          "field_mismatches": []}}
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
