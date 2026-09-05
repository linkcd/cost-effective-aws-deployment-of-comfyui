#!/usr/bin/env python3
import os
import aws_cdk as cdk
from aws_cdk import Environment
from aws_cdk import Aspects
from comfyui_aws_stack.comfyui_aws_stack import ComfyUIStack
from cdk_nag import AwsSolutionsChecks, NagSuppressions

app = cdk.App()
comfy_ui_stack = ComfyUIStack(
    app, "ComfyUIStack",
    description="ComfyUI on AWS (uksb-ggn3251wsp)",
    env=Environment(
        account=os.environ["CDK_DEFAULT_ACCOUNT"],
        region=os.environ["CDK_DEFAULT_REGION"]
    ),
    tags={
        "Repository": "aws-samples/cost-effective-aws-deployment-of-comfyui"
    },
    use_spot=False,
    auto_scale_down=False,
    enable_nvme_model_cache=True,
    comfyui_disable_pinned_memory=True,
    comfyui_ebs_volume_name="ComfyUIVolume-8a39c00b32-20260901154923",
    comfyui_subnet_id="subnet-0f26675ddc32e0174",
    self_sign_up_enabled=True,
)

Aspects.of(app).add(AwsSolutionsChecks(verbose=False))
NagSuppressions.add_stack_suppressions(stack=comfy_ui_stack, suppressions=[
    {"id": "AwsSolutions-L1", "reason": "Lambda Runtime is provided by custom resource provider and drain ecs hook implicitly and not critical for sample"},
    {"id": "AwsSolutions-IAM4",
        "reason": "For sample purposes the managed policy is sufficient"},
    {"id": "AwsSolutions-IAM5",
        "reason": "Some rules require '*' wildcard as an example ACM operations, and other are sufficient for sample"},
    {"id": "AwsSolutions-COG8",
        "reason": "Cognito plus tier/feature plan not required for this sample deployment"},
    {"id": "CdkNagValidationFailure",
        "reason": "CDK Nag cannot resolve some tokenized policies during synthesis; concrete IAM scopes are verified in synthesized-template tests"},
])

app.synth()
