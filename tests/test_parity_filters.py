import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "filter_plugins"))

from parity import normalize_objects


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
