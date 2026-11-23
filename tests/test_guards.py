"""Structural guards on the workflow and playbook that are easy to break by accident."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
WF = yaml.safe_load((ROOT / ".github" / "workflows" / "provision.yml").read_text())
ON = WF[True] if True in WF else WF["on"]  # PyYAML reads the bare `on` key as True


def test_is_reusable_with_role_input():
    call = ON["workflow_call"]
    assert set(call["inputs"]) >= {
        "params_file",
        "environment",
        "aws_plan_role_arn",
        "aws_role_arn",
    }
    assert "secrets" not in call


def test_job_order_and_apply_gate():
    jobs = WF["jobs"]
    assert list(jobs) == ["validate", "plan", "apply"]
    assert jobs["plan"]["needs"] == "validate"
    assert jobs["apply"]["needs"] == ["validate", "plan"]
    assert jobs["apply"]["environment"] == "${{ inputs.environment }}"


def test_only_plan_and_apply_get_oidc_tokens():
    assert WF["permissions"] == {"contents": "read"}
    assert "permissions" not in WF["jobs"]["validate"]
    for job in ("plan", "apply"):
        assert WF["jobs"][job]["permissions"]["id-token"] == "write"


def _assumed_role(job):
    [step] = [
        s
        for s in WF["jobs"][job]["steps"]
        if s.get("uses", "").startswith("aws-actions/configure-aws-credentials@")
    ]
    return step["with"]["role-to-assume"]


def test_plan_uses_its_own_read_only_role():
    assert _assumed_role("plan") == "${{ inputs.aws_plan_role_arn }}"
    assert _assumed_role("apply") == "${{ inputs.aws_role_arn }}"
    plan_runs = "\n".join(s.get("run", "") for s in WF["jobs"]["plan"]["steps"])
    assert "-lock=false" in plan_runs


def test_one_run_per_environment():
    assert WF["concurrency"] == {
        "group": "golden-path-provision-${{ inputs.environment }}",
        "cancel-in-progress": False,
    }


def test_no_stored_aws_keys():
    text = (ROOT / ".github" / "workflows" / "provision.yml").read_text()
    assert "aws-access-key-id" not in text
    assert "secrets." not in text


def test_apply_uses_the_reviewed_plan_file():
    steps = WF["jobs"]["apply"]["steps"]
    runs = "\n".join(s.get("run", "") for s in steps)
    assert "terraform apply -input=false tfplan" in runs
    assert "terraform plan" not in runs


def test_every_action_pinned_to_a_sha():
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        for ref in re.findall(r"uses:\s*(\S+)", wf.read_text()):
            assert re.search(r"@[0-9a-f]{40}$", ref), f"{wf.name}: {ref}"


def test_playbook_rules_from_repo_17():
    site = (ROOT / "ansible" / "site.yml").read_text()
    assert not re.search(r"failed_when:\s*false", site)
    assert "host_key_checking = True" in (ROOT / "ansible" / "ansible.cfg").read_text()
    for play in yaml.safe_load(site):
        for task in play["tasks"]:
            module = next(k for k in task if k not in {"name", "when", "tags", "vars"})
            assert module.count(".") == 2, f"not FQCN: {module}"


def test_cluster_play_is_tagged_so_check_mode_can_skip_it():
    plays = yaml.safe_load((ROOT / "ansible" / "site.yml").read_text())
    assert plays[0]["tags"] == ["prepare"]
    assert plays[1]["tags"] == ["cluster"]
    modules = {k for t in plays[0]["tasks"] for k in t if k.startswith("kubernetes.")}
    assert modules == set()  # prepare play never touches a cluster
