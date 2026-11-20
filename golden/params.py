"""Validate the environment parameter file and render tool inputs from it."""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "environment.schema.json").read_text(encoding="utf-8"))


class ParamsError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    validate(data)
    return data


def validate(data) -> None:
    """Schema first, then the rules JSON Schema can't express. Collects every problem."""
    problems = [
        f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"
        for e in sorted(Draft202012Validator(SCHEMA).iter_errors(data), key=str)
    ]
    if problems:
        raise ParamsError(problems)

    c, net = data["cluster"], data["network"]
    if not c["node_min_size"] <= c["node_desired_size"] <= c["node_max_size"]:
        problems.append("cluster: need node_min_size <= node_desired_size <= node_max_size")

    for cidr in [net["vpc_cidr"], *c["api_allowed_cidrs"]]:
        try:
            ipaddress.IPv4Network(cidr)
        except ValueError as exc:
            problems.append(f"invalid CIDR {cidr}: {exc}")
    if not problems:
        vpc = ipaddress.IPv4Network(net["vpc_cidr"])
        if not 16 <= vpc.prefixlen <= 20:
            problems.append("network.vpc_cidr: prefix must be /16 to /20")
        if not vpc.is_private:
            problems.append("network.vpc_cidr: must be a private range")
        if "0.0.0.0/0" in c["api_allowed_cidrs"]:
            problems.append("cluster.api_allowed_cidrs: 0.0.0.0/0 is not allowed")

    region = data["aws"]["region"]
    for az in net["availability_zones"]:
        if az[:-1] != region:
            problems.append(f"network.availability_zones: {az} is not in {region}")
    if problems:
        raise ParamsError(problems)


def subnets(vpc_cidr: str, count: int) -> tuple[list[str], list[str]]:
    """Carve /4-smaller private and public subnets, one of each per AZ."""
    blocks = list(ipaddress.IPv4Network(vpc_cidr).subnets(prefixlen_diff=4))
    private = [str(b) for b in blocks[:count]]
    public = [str(b) for b in blocks[8 : 8 + count]]
    return private, public


def render(data: dict, out_dir: Path) -> Path:
    """Write terraform.tfvars.json, ansible-vars.json and meta.json for one environment."""
    env = data["environment"]
    target = out_dir / env
    target.mkdir(parents=True, exist_ok=True)
    c, net = data["cluster"], data["network"]
    private, public = subnets(net["vpc_cidr"], len(net["availability_zones"]))
    tags = {"environment": env, "managed-by": "golden-path"}

    tfvars = {
        "name": f"gp-{env}",
        "region": data["aws"]["region"],
        "allowed_account_ids": [data["aws"]["account_id"]],
        "vpc_cidr": net["vpc_cidr"],
        "availability_zones": net["availability_zones"],
        "private_subnets": private,
        "public_subnets": public,
        "kubernetes_version": c["kubernetes_version"],
        "node_instance_types": c["node_instance_types"],
        "node_min_size": c["node_min_size"],
        "node_desired_size": c["node_desired_size"],
        "node_max_size": c["node_max_size"],
        "api_allowed_cidrs": c["api_allowed_cidrs"],
        "tags": tags,
    }
    ansible_vars = {
        "golden_path_env": env,
        "golden_path_observability_enabled": data["observability"]["enabled"],
        "golden_path_retention_days": data["observability"]["retention_days"],
        "golden_path_app_name": data["app"]["name"],
        "golden_path_app_image": data["app"]["image"],
        "golden_path_app_replicas": data["app"]["replicas"],
        "golden_path_app_namespace": f"{data['app']['name']}-{env}",
    }
    meta = {"environment": env, "region": data["aws"]["region"], "cluster_name": tfvars["name"]}

    for name, content in (
        ("terraform.tfvars.json", tfvars),
        ("ansible-vars.json", ansible_vars),
        ("meta.json", meta),
    ):
        (target / name).write_text(json.dumps(content, indent=2, sort_keys=True) + "\n")
    return target
