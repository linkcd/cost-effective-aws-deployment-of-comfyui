import datetime
import json
import re
from unittest.mock import patch

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from comfyui_aws_stack.comfyui_aws_stack import ComfyUIStack


class FrozenDateTime(datetime.datetime):
    @classmethod
    def utcnow(cls):
        return cls(2026, 7, 26, 0, 3, 18)


def create_template(enable_nvme_model_cache=True, **stack_kwargs):
    app = cdk.App()
    with patch(
        "comfyui_aws_stack.construct.ecs_construct.datetime.datetime",
        FrozenDateTime,
    ):
        stack = ComfyUIStack(
            app,
            "ComfyUIStack",
            enable_nvme_model_cache=enable_nvme_model_cache,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
            **stack_kwargs,
        )
    return Template.from_stack(stack)


def test_nvme_cache_is_enabled_by_default_without_changing_gp3():
    template = create_template()

    template.has_resource_properties(
        "AWS::ECS::TaskDefinition",
        {
            "Volumes": Match.array_with(
                [
                    Match.object_like(
                        {
                            "DockerVolumeConfiguration": Match.object_like(
                                {
                                    "DriverOpts": {
                                        "size": "5000",
                                        "volumetype": "gp3",
                                    }
                                }
                            )
                        }
                    ),
                    {
                        "Name": "ComfyUIModelCache",
                        "Host": {"SourcePath": "/mnt/comfy-cache"},
                    },
                ]
            ),
            "ContainerDefinitions": Match.array_with(
                [
                    Match.object_like(
                        {
                            "Environment": Match.array_with(
                                [
                                    {
                                        "Name": "COMFYUI_MODEL_CACHE_ENABLED",
                                        "Value": "1",
                                    },
                                    {
                                        "Name": "COMFYUI_MODEL_CACHE_ROOT",
                                        "Value": "/mnt/comfy-cache",
                                    },
                                ]
                            ),
                            "MountPoints": Match.array_with(
                                [
                                    {
                                        "ContainerPath": "/mnt/comfy-cache",
                                        "ReadOnly": False,
                                        "SourceVolume": "ComfyUIModelCache",
                                    }
                                ]
                            ),
                            "HealthCheck": Match.object_like(
                                {"StartPeriod": 900}
                            ),
                        }
                    )
                ]
            ),
        },
    )

    rendered = json.dumps(template.to_json())
    assert "Amazon EC2 NVMe Instance Storage" in rendered
    assert ".comfyui-instance-store" in rendered
    assert not re.search(r'"throughput"|"iops"', rendered, re.IGNORECASE)


def test_nvme_cache_can_be_disabled_with_ebs_only_task():
    template = create_template(enable_nvme_model_cache=False)
    rendered = json.dumps(template.to_json())

    assert "ComfyUIModelCache" not in rendered
    assert "COMFYUI_MODEL_CACHE_ENABLED" in rendered
    assert '"Value": "0"' in rendered
    assert "Amazon EC2 NVMe Instance Storage" not in rendered


def test_pinned_memory_can_be_disabled_for_low_ram_h3_host():
    template = create_template(comfyui_disable_pinned_memory=True)

    template.has_resource_properties(
        "AWS::ECS::TaskDefinition",
        {
            "ContainerDefinitions": Match.array_with(
                [
                    Match.object_like(
                        {"Command": ["--disable-pinned-memory"]}
                    )
                ]
            )
        },
    )


def test_existing_ebs_volume_and_subnet_are_preserved_for_host_replacement():
    template = create_template(
        comfyui_ebs_volume_name="ComfyUIVolume-existing",
        comfyui_subnet_id="subnet-existing",
    )

    template.has_resource_properties(
        "AWS::ECS::TaskDefinition",
        {
            "Volumes": Match.array_with(
                [
                    Match.object_like(
                        {"Name": "ComfyUIVolume-existing"}
                    )
                ]
            )
        },
    )
    template.has_resource_properties(
        "AWS::AutoScaling::AutoScalingGroup",
        {"VPCZoneIdentifier": ["subnet-existing"]},
    )

    asgs = template.find_resources("AWS::AutoScaling::AutoScalingGroup")
    assert len(asgs) == 1
    update_policy = next(iter(asgs.values()))["UpdatePolicy"]
    assert update_policy["AutoScalingRollingUpdate"]["MaxBatchSize"] == 1
    assert update_policy["AutoScalingRollingUpdate"]["MinInstancesInService"] == 0
