import json
from functools import lru_cache
from pathlib import Path

import aws_cdk as cdk
from aws_cdk.assertions import Template

from comfyui_aws_stack.comfyui_aws_stack import ComfyUIStack


ROOT = Path(__file__).parents[1]


@lru_cache(maxsize=1)
def synthesized_template():
    app = cdk.App()
    stack = ComfyUIStack(
        app,
        "ComfyUIStack",
        env=cdk.Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack).to_json()


def policy_statements(template):
    for resource in template["Resources"].values():
        if resource["Type"] != "AWS::IAM::Policy":
            continue
        statements = resource["Properties"]["PolicyDocument"]["Statement"]
        if isinstance(statements, dict):
            statements = [statements]
        yield from statements


def test_full_access_managed_policies_are_not_used():
    template_json = json.dumps(synthesized_template())

    assert "AmazonEC2FullAccess" not in template_json
    assert "AutoScalingFullAccess" not in template_json
    assert "AmazonECSTaskExecutionRolePolicy" not in template_json
    assert "autoscaling:DescribeScalingActivities" not in template_json
    assert "ecs:ListServices" not in template_json
    assert "elasticloadbalancing:DescribeRules" not in template_json

    codebuild_template = (ROOT / "codebuild-pipeline.yaml").read_text(
        encoding="utf-8"
    )
    assert "AdministratorAccess" not in codebuild_template
    assert "cdk-hnb659fds-deploy-role" in codebuild_template


def test_sensitive_write_actions_are_resource_scoped():
    sensitive_actions = {
        "acm:AddTagsToCertificate",
        "acm:DeleteCertificate",
        "acm:ImportCertificate",
        "autoscaling:SetDesiredCapacity",
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "cognito-idp:UpdateUserPoolClient",
        "ec2:AttachVolume",
        "ec2:CreateVolume",
        "ec2:DeleteVolume",
        "ec2:DetachVolume",
        "ec2:ModifyVolume",
        "ecs:UpdateService",
        "elasticloadbalancing:ModifyRule",
        "ssm:SendCommand",
    }

    for statement in policy_statements(synthesized_template()):
        actions = statement["Action"]
        if isinstance(actions, str):
            actions = [actions]
        if sensitive_actions.intersection(actions):
            assert statement["Resource"] != "*"


def test_scopeable_rexray_describe_action_uses_volume_arn():
    for statement in policy_statements(synthesized_template()):
        actions = statement["Action"]
        if isinstance(actions, str):
            actions = [actions]
        if "ec2:DescribeVolumeAttribute" in actions:
            assert statement["Resource"] != "*"


def test_ecs_task_and_execution_roles_are_separate():
    task_definitions = {
        logical_id: resource
        for logical_id, resource in synthesized_template()["Resources"].items()
        if resource["Type"] == "AWS::ECS::TaskDefinition"
    }

    assert len(task_definitions) == 1
    properties = next(iter(task_definitions.values()))["Properties"]
    assert properties["TaskRoleArn"] != properties["ExecutionRoleArn"]


def test_mfa_is_required_by_default():
    user_pools = [
        resource
        for resource in synthesized_template()["Resources"].values()
        if resource["Type"] == "AWS::Cognito::UserPool"
    ]

    assert len(user_pools) == 1
    assert user_pools[0]["Properties"]["MfaConfiguration"] == "ON"


def test_bedrock_model_access_is_region_scoped():
    template_json = json.dumps(synthesized_template())

    assert ":bedrock:*:" not in template_json


def test_unscopable_list_actions_are_region_restricted():
    expected_actions = {
        "autoscaling:DescribeAutoScalingGroups",
        "bedrock:ListFoundationModels",
    }
    seen_actions = set()

    for statement in policy_statements(synthesized_template()):
        actions = statement["Action"]
        if isinstance(actions, str):
            actions = [actions]

        for action in expected_actions.intersection(actions):
            assert statement["Resource"] == "*"
            assert statement["Condition"]["StringEquals"][
                "aws:RequestedRegion"
            ] == {"Ref": "AWS::Region"}
            seen_actions.add(action)

    assert seen_actions == expected_actions


def test_dockerfile_has_comfyui_healthcheck():
    dockerfile = (
        ROOT / "comfyui_aws_stack" / "docker" / "Dockerfile"
    ).read_text(encoding="utf-8")

    assert "HEALTHCHECK" in dockerfile
    assert "http://localhost:8181/system_stats" in dockerfile
