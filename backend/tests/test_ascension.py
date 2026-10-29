import pytest

from ascension import load_manifest, manifest_checksum, platform_audit, validate_manifest


def test_plugin_manifest_is_validated_and_execution_is_restricted():
    result = validate_manifest({
        "plugin_id": "example.recipe",
        "name": "Example recipe",
        "version": "1.0.0",
        "author": "Polyglot",
        "category": "migration_recipe",
        "entry_point": "recipe.json",
        "permissions": ["read_project", "execute"],
    })
    assert result["valid"] is True
    assert result["execution_status"] == "unsupported_without_isolation"


def test_plugin_manifest_rejects_unknown_category_and_duplicate():
    with pytest.raises(ValueError):
        validate_manifest({
            "plugin_id": "bad.plugin",
            "name": "Bad",
            "version": "1.0.0",
            "author": "Test",
            "category": "arbitrary_code",
            "entry_point": "main.py",
        })
    with pytest.raises(ValueError):
        validate_manifest({
            "plugin_id": "known.plugin",
            "name": "Known",
            "version": "1.0.0",
            "author": "Test",
            "category": "validator",
            "entry_point": "main.py",
        }, existing_ids={"known.plugin"})


def test_audit_and_manifest_checksum_are_deterministic():
    audit = platform_audit()
    assert audit["release_status"] == "development"
    assert manifest_checksum({"plugin_id": "x"}) == manifest_checksum({"plugin_id": "x"})
