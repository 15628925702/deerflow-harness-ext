"""config loader tests. policies_from_config needs no yaml; load_config needs pyyaml."""
import pytest

from deerflow_harness_ext.deerflow.config import load_config, policies_from_config


def test_policies_from_config_context():
    ps = policies_from_config({"policies": {"context": {"target_fraction": 0.9}}})
    assert len(ps) == 1
    assert ps[0].name == "context"
    assert ps[0].target_fraction == 0.9


def test_policies_from_config_multiple():
    ps = policies_from_config({"policies": {
        "context": {}, "failure": {"max_repeats": 2}, "permissions": {"mode": "plan"}}})
    assert {p.name for p in ps} == {"context", "failure", "permissions"}


def test_policies_from_config_unknown_key_ignored():
    ps = policies_from_config({"policies": {"nope": {}}})
    assert ps == []


def test_load_config_yaml(tmp_path):
    yaml = pytest.importorskip("yaml")
    f = tmp_path / "c.yaml"
    f.write_text("policies:\n  context:\n    target_fraction: 0.8\n")
    cfg = load_config(str(f))
    assert cfg["policies"]["context"]["target_fraction"] == 0.8
