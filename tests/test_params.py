import copy
import json
import re
from pathlib import Path

import pytest
import yaml

from golden.cli import main
from golden.params import ParamsError, render, validate

ROOT = Path(__file__).parent.parent
GOOD = yaml.safe_load((ROOT / "params" / "dev.yaml").read_text())


def with_change(path: str, value):
    data = copy.deepcopy(GOOD)
    *parents, last = path.split(".")
    node = data
    for p in parents:
        node = node[p]
    if value is DELETE:
        del node[last]
    else:
        node[last] = value
    return data


DELETE = object()


def test_example_params_are_valid():
    validate(copy.deepcopy(GOOD))


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        ("environment", "Dev_1", "does not match"),
        ("aws.account_id", "12345", "does not match"),
        ("aws.region", "europe", "does not match"),
        ("network.vpc_cidr", "10.0.0.0/8", "/16 to /20"),
        ("network.vpc_cidr", "8.8.0.0/16", "private range"),
        ("network.vpc_cidr", "10.40.0.1/16", "invalid CIDR"),
        ("network.availability_zones", ["eu-west-2a"], "too short"),
        ("network.availability_zones", ["eu-west-2a", "us-east-1a"], "not in eu-west-2"),
        ("cluster.kubernetes_version", "1.20", "is not one of"),
        ("cluster.node_desired_size", 9, "node_min_size <= node_desired_size <= node_max_size"),
        ("cluster.node_max_size", 50, "greater than the maximum"),
        ("cluster.api_allowed_cidrs", ["0.0.0.0/0"], "0.0.0.0/0 is not allowed"),
        ("observability.retention_days", 0, "less than the minimum"),
        ("app.image", "nginx:latest", "should not be valid"),
        ("app.image", "nginx", "does not match"),
        ("app.replicas", "two", "is not of type"),
        ("app.name", DELETE, "'name' is a required property"),
        ("app.extra", "x", "Additional properties are not allowed"),
    ],
)
def test_bad_params_rejected(path, value, message):
    with pytest.raises(ParamsError) as err:
        validate(with_change(path, value))
    assert any(message in p for p in err.value.problems), err.value.problems


def test_all_problems_reported_together():
    data = with_change("aws.region", "nowhere")
    data["app"]["replicas"] = 0
    with pytest.raises(ParamsError) as err:
        validate(data)
    assert len(err.value.problems) == 2


def test_render_outputs(tmp_path):
    out = render(copy.deepcopy(GOOD), tmp_path)
    tfvars = json.loads((out / "terraform.tfvars.json").read_text())
    ansible = json.loads((out / "ansible-vars.json").read_text())
    meta = json.loads((out / "meta.json").read_text())
    assert tfvars["name"] == "gp-dev"
    assert tfvars["private_subnets"] == ["10.40.0.0/20", "10.40.16.0/20"]
    assert tfvars["public_subnets"] == ["10.40.128.0/20", "10.40.144.0/20"]
    assert tfvars["allowed_account_ids"] == ["123456789012"]
    assert ansible["golden_path_app_namespace"] == "hello-dev"
    assert ansible["golden_path_observability_enabled"] is True
    assert meta == {"environment": "dev", "region": "eu-west-2", "cluster_name": "gp-dev"}


def test_tfvars_keys_match_terraform_variables(tmp_path):
    declared = set(
        re.findall(r'^variable "(\w+)"', (ROOT / "terraform" / "variables.tf").read_text(), re.M)
    )
    tfvars = json.loads(
        (render(copy.deepcopy(GOOD), tmp_path) / "terraform.tfvars.json").read_text()
    )
    assert set(tfvars) == declared


def test_ansible_vars_cover_playbook_and_templates(tmp_path):
    ansible = json.loads((render(copy.deepcopy(GOOD), tmp_path) / "ansible-vars.json").read_text())
    used = set()
    for f in [ROOT / "ansible" / "site.yml", *(ROOT / "ansible" / "templates").glob("*.j2")]:
        used |= set(re.findall(r"\b(golden_path_\w+)\b", f.read_text()))
    defined_in_play = {"golden_path_build_dir", "golden_path_prometheus_chart_version"}
    assert used - defined_in_play <= set(ansible)


def test_cli_exit_codes(tmp_path, capsys):
    assert main(["validate", str(ROOT / "params" / "dev.yaml")]) == 0
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(with_change("cluster.node_min_size", 0)))
    assert main(["validate", str(bad)]) == 1
    assert "node_min_size" in capsys.readouterr().err
    assert main(["render", str(bad), "--out", str(tmp_path / "b")]) == 1
    assert not (tmp_path / "b").exists()
