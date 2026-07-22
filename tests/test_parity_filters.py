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
