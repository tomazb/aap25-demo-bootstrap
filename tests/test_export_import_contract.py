from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def read_text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def load_play(name: str) -> dict[str, Any]:
    document = yaml.safe_load(read_text(name))
    assert isinstance(document, list), f"{name} must contain a play list"
    assert len(document) == 1, f"{name} must contain exactly one play"
    play = document[0]
    assert isinstance(play, dict), f"{name} play must be a mapping"
    return play


def all_tasks(play: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for section in ("pre_tasks", "tasks", "post_tasks"):
        tasks = play.get(section, [])
        assert isinstance(tasks, list), f"{section} must be a list"
        result.extend(task for task in tasks if isinstance(task, dict))
    return result


def find_tasks(play: dict[str, Any], module_name: str) -> list[dict[str, Any]]:
    return [task for task in all_tasks(play) if module_name in task]


def require_one_task(play: dict[str, Any], module_name: str) -> dict[str, Any]:
    matches = find_tasks(play, module_name)
    assert len(matches) == 1, (
        f"expected exactly one {module_name} task, found {len(matches)}"
    )
    return matches[0]


def test_export_file_is_the_assets_mapping_consumed_directly_by_import() -> None:
    export_play = load_play("export.yml")
    import_play = load_play("import.yml")

    export_task = require_one_task(export_play, "ansible.controller.export")
    assert export_task.get("register") == "export_output"

    asset_writes = [
        task
        for task in find_tasks(export_play, "ansible.builtin.copy")
        if "export_output.assets" in str(task["ansible.builtin.copy"].get("content", ""))
    ]
    assert len(asset_writes) == 1, (
        "export.yml must serialize export_output.assets, not the module wrapper"
    )

    import_task = require_one_task(import_play, "ansible.controller.import")
    assert import_task["ansible.controller.import"]["assets"] == "{{ imported_assets }}"

    export_text = read_text("export.yml")
    import_text = read_text("import.yml")
    assert "export_output | to_nice_yaml" not in export_text
    assert "imported_assets.export" not in import_text
    assert "import_output.status" not in import_text


def test_gateway_api_prefix_and_aap_25_controller_version_are_fail_closed() -> None:
    for name, module_name in (
        ("export.yml", "ansible.controller.export"),
        ("import.yml", "ansible.controller.import"),
    ):
        play = load_play(name)
        text = read_text(name)
        uri_tasks = find_tasks(play, "ansible.builtin.uri")
        assert any(
            task["ansible.builtin.uri"].get("url")
            == "{{ aap_hostname }}/api/controller/v2/config/"
            for task in uri_tasks
        ), f"{name} must probe the controller API through Platform Gateway"
        assert "/api/v2/config/" not in text
        assert "^4\\.6\\." in text, f"{name} must reject a non-AAP-2.5 controller"

        controller_task = require_one_task(play, module_name)
        assert controller_task.get("environment") == {
            "CONTROLLER_OPTIONAL_API_URLPATTERN_PREFIX": "/api/controller/"
        }


def test_import_requires_explicit_confirmation_valid_file_and_matching_checksum() -> None:
    play = load_play("import.yml")
    text = read_text("import.yml")

    assert play["vars"].get("import_confirm") is False
    assert "IMPORT_FILE" in str(play["vars"].get("import_file", ""))
    assert "reports/exported_objects.yml" not in text
    assert "import_confirm | bool" in text

    stat_tasks = find_tasks(play, "ansible.builtin.stat")
    assert len(stat_tasks) >= 2, "both the asset file and checksum sidecar must be stat'ed"
    assert "checksum_algorithm: sha256" in text
    assert "import_expected_checksum" in text
    assert "import_file_stat.stat.isreg" in text
    assert "import_checksum_file_stat.stat.isreg" in text
    assert "ignore_errors:" not in text
    assert "failed_when: false" not in text


def test_export_artifacts_are_private_deterministic_and_checksums_are_reported() -> None:
    play = load_play("export.yml")
    text = read_text("export.yml")

    directory_tasks = find_tasks(play, "ansible.builtin.file")
    assert any(
        task["ansible.builtin.file"].get("state") == "directory"
        and task["ansible.builtin.file"].get("mode") == "0700"
        for task in directory_tasks
    )

    copy_tasks = find_tasks(play, "ansible.builtin.copy")
    assert len(copy_tasks) == 2, "export file and checksum sidecar must both be written"
    assert all(task["ansible.builtin.copy"].get("mode") == "0600" for task in copy_tasks)
    assert all(task.get("diff") is False for task in copy_tasks)

    assert "checksum_algorithm: sha256" in text
    assert "export_checksum_file" in text
    assert "lookup('ansible.builtin.pipe'" not in text
    assert text.count("now(utc=true") == 1
    assert "export_output.assets" in text


def test_import_rejects_wrapped_or_malformed_export_documents() -> None:
    text = read_text("import.yml")
    for wrapper_key in ("assets", "export", "changed", "failed"):
        assert wrapper_key in text
    assert "imported_assets is mapping" in text
    assert "imported_assets | length > 0" in text
    assert "item.value is sequence" in text
    assert "item.value is not string" in text


def test_controller_collection_floor_contains_gateway_export_fix() -> None:
    requirements = yaml.safe_load(read_text("requirements.yml"))
    controller = next(
        item
        for item in requirements["collections"]
        if item["name"] == "ansible.controller"
    )
    assert controller["version"] == ">=4.6.20,<4.7.0"
