from aws_cdk import (
    Stack,
    CfnOutput,
    aws_ecs as ecs,
    aws_servicediscovery as servicediscovery,
    aws_chatbot as chatbot,
    aws_iam as iam,
)
from constructs import Construct

from comfyui_aws_stack.construct.vpc_construct import VpcConstruct
from comfyui_aws_stack.construct.alb_construct import AlbConstruct
from comfyui_aws_stack.construct.asg_construct import AsgConstruct
from comfyui_aws_stack.construct.ecs_construct import EcsConstruct
from comfyui_aws_stack.construct.admin_construct import AdminConstruct
from comfyui_aws_stack.construct.auth_construct import AuthConstruct

import os
import hashlib
from typing import List

class ComfyUIStack(Stack):

    def __init__(self,
                 scope: Construct,
                 construct_id: str,
                 # VPC
                 cheap_vpc: bool = True,
                 # Spot
                 use_spot: bool = True,
                 spot_price: str = "0.752",
                 # Auto Scaling
                 auto_scale_down: bool = True,
                 schedule_auto_scaling: bool = False,
                 timezone: str = "UTC",
                 schedule_scale_up: str = "0 9 * * 1-5",
                 schedule_scale_down: str = "0 18 * * *",
                 # Sign up
                 self_sign_up_enabled: bool = False,
                 allowed_sign_up_email_domains: List[str] = None,
                 mfa_required: bool = True,
                 saml_auth_enabled: bool = False,
                 # Network Restriction
                 allowed_ip_v4_address_ranges: List[str] = None,
                 allowed_ip_v6_address_ranges: List[str] = None,
                 # WAF Rate Limiting
                 waf_rate_limit_enabled: bool = False,
                 waf_rate_limit_requests: int = 300,
                 waf_rate_limit_interval: int = 300,
                 # Custom Domain
                 host_name: str = None,
                 domain_name: str = None,
                 hosted_zone_id: str = None,
                 enable_comfyui: bool = True,
                 comfyui_instance_type: str = "g6e.2xlarge",
                 enable_nvme_model_cache: bool = True,
                 comfyui_disable_pinned_memory: bool = False,
                 comfyui_ebs_volume_name: str = None,
                 comfyui_subnet_id: str = None,
                 # Slack
                 slack_workspace_id: str = None,
                 slack_channel_id: str = None,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Setting
        region = self.region
        unique_input = f"{self.account}-{self.region}-{self.stack_name}"
        unique_hash = hashlib.sha256(
            unique_input.encode('utf-8')).hexdigest()[:10]
        suffix = unique_hash.lower()

        # Check host
        is_sagemaker_studio = "SAGEMAKER_APP_TYPE_LOWERCASE" in os.environ

        # VPC

        vpc_construct = VpcConstruct(
            self, "VpcConstruct",
            cheap_vpc=cheap_vpc
        )
        # After vpc_construct
        ecs_cluster = ecs.Cluster(
            self,
            "EcsCluster",
            vpc=vpc_construct.vpc,
            container_insights=True,
            default_cloud_map_namespace=ecs.CloudMapNamespaceOptions(
                name="local",
                type=servicediscovery.NamespaceType.DNS_PRIVATE,
            ),
        )  

        # ALB

        alb_construct = AlbConstruct(
            self, "AlbConstruct",
            vpc=vpc_construct.vpc,
            is_sagemaker_studio=is_sagemaker_studio,
            allowed_ip_v4_address_ranges=allowed_ip_v4_address_ranges,
            allowed_ip_v6_address_ranges=allowed_ip_v6_address_ranges,
            waf_rate_limit_enabled=waf_rate_limit_enabled,
            waf_rate_limit_requests=waf_rate_limit_requests,
            waf_rate_limit_interval=waf_rate_limit_interval,
            host_name=host_name,
            domain_name=domain_name,
            hosted_zone_id=hosted_zone_id,
        )

        # Auth

        auth_construct = AuthConstruct(
            self, "AuthConstruct",
            alb=alb_construct.alb,
            suffix=suffix,
            host_name=host_name,
            domain_name=domain_name,
            saml_auth_enabled=saml_auth_enabled,
            self_sign_up_enabled=self_sign_up_enabled,
            mfa_required=mfa_required,
            allowed_sign_up_email_domains=allowed_sign_up_email_domains,
        )        

        # === ASG for ComfyUI ===
        asg_comfy = None
        if enable_comfyui:
            asg_comfy = AsgConstruct(
                self,
                construct_id="ComfyUIAsg",
                vpc=vpc_construct.vpc,
                ecs_cluster_name=ecs_cluster.cluster_name, 
                use_spot=use_spot,
                spot_price=spot_price,
                auto_scale_down=auto_scale_down,
                schedule_auto_scaling=schedule_auto_scaling,
                timezone=timezone,
                schedule_scale_down=schedule_scale_down,
                schedule_scale_up=schedule_scale_up,
                instance_type=comfyui_instance_type,
                enable_nvme_model_cache=enable_nvme_model_cache,
                subnet_id=comfyui_subnet_id,
                desired_capacity=1,
                slack_workspace_id=slack_workspace_id,
                slack_channel_id=slack_channel_id,
            )

        # ECS

        if enable_comfyui:
            ecs_construct = EcsConstruct(
                self, "EcsConstruct",
                vpc=vpc_construct.vpc,
                comfy_asg=asg_comfy.auto_scaling_group,
                alb_security_group=alb_construct.alb_security_group,
                is_sagemaker_studio=is_sagemaker_studio,
                suffix=suffix,
                region=region,
                user_pool=auth_construct.user_pool,
                user_pool_client=auth_construct.user_pool_client,
                cluster=ecs_cluster,
                enable_nvme_model_cache=enable_nvme_model_cache,
                disable_pinned_memory=comfyui_disable_pinned_memory,
                comfyui_ebs_volume_name=comfyui_ebs_volume_name,
                slack_workspace_id=slack_workspace_id,
                slack_channel_id=slack_channel_id,
            )
        else:
            raise ValueError("ComfyUI must be enabled for ECS deployment.")


        # Admin Lambda

        if enable_comfyui:
            admin_construct = AdminConstruct(
                self, "AdminConstruct",
                vpc=vpc_construct.vpc,
                cluster=ecs_construct.cluster,
                service=ecs_construct.service,
                auto_scaling_group=asg_comfy.auto_scaling_group,
                user_pool_logout_url=auth_construct.user_pool_logout_url,
            )
        
            alb_construct.associate_resources(
                ecs_target_group=ecs_construct.ecs_target_group,
                lambda_admin_target_group=admin_construct.lambda_admin_target_group,
                lambda_restart_docker_target_group=admin_construct.lambda_restart_docker_target_group,
                lambda_shutdown_target_group=admin_construct.lambda_shutdown_target_group,
                lambda_scaleup_target_group=admin_construct.lambda_scaleup_target_group,
                lambda_signout_target_group=admin_construct.lambda_signout_target_group,
                user_pool=auth_construct.user_pool,
                user_pool_client=auth_construct.user_pool_client,
                user_pool_custom_domain=auth_construct.user_pool_custom_domain,
            )
        
            admin_construct.add_environments(
                lambda_admin_rule=alb_construct.lambda_admin_rule,
            )

        # Slack

        if slack_workspace_id and slack_channel_id:
            slack_channel = chatbot.SlackChannelConfiguration(
                self, "SlackChannel",
                slack_channel_configuration_name="TestChannel",
                slack_workspace_id=slack_workspace_id,
                slack_channel_id=slack_channel_id,
                notification_topics=[
                    asg_comfy.asg_events_topic, ecs_construct.ecs_health_topic]
            )
            slack_channel.role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchReadOnlyAccess"
                )
            )
            slack_channel.role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonQFullAccess"
                )
            )

        # Output

        CfnOutput(self, "Endpoint", value=auth_construct.application_dns_name)
        CfnOutput(self, "UserPoolId",
                  value=auth_construct.user_pool.user_pool_id)
        CfnOutput(self, "CognitoDomainName",
                  value=auth_construct.user_pool_custom_domain.domain_name)
        CfnOutput(self, "ComfyUIASGName", value=asg_comfy.auto_scaling_group.auto_scaling_group_name)
        CfnOutput(self, "ComfyUIS3Bucket", value=ecs_construct.comfyui_bucket.bucket_name)
