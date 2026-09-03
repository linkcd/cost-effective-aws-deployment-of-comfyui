import datetime
import re
from unittest.mock import patch

import aws_cdk as cdk
from aws_cdk.assertions import Template

from comfyui_aws_stack.comfyui_aws_stack import ComfyUIStack


class FrozenDateTime(datetime.datetime):
    @classmethod
    def utcnow(cls):
        return cls(2026, 7, 26, 0, 3, 18)


def normalize_generated_values(value):
    if isinstance(value, dict):
        return {
            key: normalize_generated_values(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [normalize_generated_values(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"TOKEN\.\d+", "TOKEN.ID", value)
    return value


def test_comfyui_aws_stack_snapshot(snapshot):
    app = cdk.App()
    with patch(
        "comfyui_aws_stack.construct.ecs_construct.datetime.datetime",
        FrozenDateTime,
    ):
        stack = ComfyUIStack(
            app,
            "ComfyUIStack",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

    template = Template.from_stack(stack)
    assert normalize_generated_values(template.to_json()) == snapshot
