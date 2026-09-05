from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_autoscaling as autoscaling,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as targets,
    aws_events as events,
    aws_events_targets as event_targets,
    Aws,
    Duration,
    aws_lambda as lambda_,
)
from constructs import Construct


class AdminConstruct(Construct):
    restart_docker_lambda: lambda_.Function
    scalein_listener_lambda: lambda_.Function
    scaleup_listener_lambda: lambda_.Function
    lambda_admin_target_group: elbv2.ApplicationTargetGroup
    lambda_restart_docker_target_group: elbv2.ApplicationTargetGroup
    lambda_shutdown_target_group: elbv2.ApplicationTargetGroup
    lambda_scaleup_target_group: elbv2.ApplicationTargetGroup
    lambda_signout_target_group: elbv2.ApplicationTargetGroup

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            vpc: ec2.Vpc,
            cluster: ecs.Cluster,
            service: ecs.IService,
            auto_scaling_group: autoscaling.AutoScalingGroup,
            user_pool_logout_url: str,
            **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        def grant_asg_describe(function: lambda_.Function) -> None:
            # DescribeAutoScalingGroups has no resource-level ARN support.
            function.add_to_role_policy(iam.PolicyStatement(
                actions=["autoscaling:DescribeAutoScalingGroups"],
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "aws:RequestedRegion": Aws.REGION,
                    },
                },
            ))

        def grant_asg_scale(function: lambda_.Function) -> None:
            function.add_to_role_policy(iam.PolicyStatement(
                actions=["autoscaling:SetDesiredCapacity"],
                resources=[auto_scaling_group.auto_scaling_group_arn],
            ))

        def grant_ecs_describe(function: lambda_.Function) -> None:
            function.add_to_role_policy(iam.PolicyStatement(
                actions=["ecs:DescribeServices"],
                resources=[service.service_arn],
            ))

        def grant_ecs_update(function: lambda_.Function) -> None:
            function.add_to_role_policy(iam.PolicyStatement(
                actions=["ecs:UpdateService"],
                resources=[service.service_arn],
            ))

        def grant_ssm_restart(function: lambda_.Function) -> None:
            # SendCommand authorizes both the exact SSM document and target
            # instance. AWS-RunShellScript is accountless, so scope it by its
            # complete regional ARN; SSM has no DocumentName condition key.
            function.add_to_role_policy(iam.PolicyStatement(
                actions=["ssm:SendCommand"],
                resources=[
                    f"arn:{Aws.PARTITION}:ssm:{Aws.REGION}:"
                    ":document/AWS-RunShellScript",
                ],
            ))
            function.add_to_role_policy(iam.PolicyStatement(
                actions=["ssm:SendCommand"],
                resources=[
                    f"arn:{Aws.PARTITION}:ec2:{Aws.REGION}:"
                    f"{Aws.ACCOUNT_ID}:instance/*",
                ],
                conditions={
                    "StringEquals": {
                        "ssm:resourceTag/aws:autoscaling:groupName":
                            auto_scaling_group.auto_scaling_group_name,
                    },
                },
            ))

        admin_lambda = lambda_.Function(
            scope,
            "AdminFunction",
            handler="admin.handler",
            code=lambda_.Code.from_asset(
                "./comfyui_aws_stack/lambda/admin_lambda"),
            runtime=lambda_.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(amount=60),
            environment={
                "ASG_NAME": auto_scaling_group.auto_scaling_group_name,
                "ECS_CLUSTER_NAME": cluster.cluster_name,
                "ECS_SERVICE_NAME": service.service_name
            }
        )
        grant_asg_describe(admin_lambda)
        grant_ecs_describe(admin_lambda)

        restart_docker_lambda = lambda_.Function(
            scope,
            "RestartDockerFunction",
            handler="restart_docker.handler",
            code=lambda_.Code.from_asset(
                "./comfyui_aws_stack/lambda/admin_lambda"),
            runtime=lambda_.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(amount=60),
            environment={
                "ASG_NAME": auto_scaling_group.auto_scaling_group_name,
                "ECS_CLUSTER_NAME": cluster.cluster_name,
                "ECS_SERVICE_NAME": service.service_name
            }
        )
        grant_asg_describe(restart_docker_lambda)
        grant_ecs_describe(restart_docker_lambda)
        grant_ssm_restart(restart_docker_lambda)

        shutdown_lambda = lambda_.Function(
            scope,
            "ShutdownFunction",
            handler="shutdown.handler",
            code=lambda_.Code.from_asset(
                "./comfyui_aws_stack/lambda/admin_lambda"),
            runtime=lambda_.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(amount=60),
            environment={
                "ASG_NAME": auto_scaling_group.auto_scaling_group_name,
                "ECS_CLUSTER_NAME": cluster.cluster_name,
            }
        )
        grant_asg_describe(shutdown_lambda)
        grant_asg_scale(shutdown_lambda)

        scaleup_trigger_lambda = lambda_.Function(
            scope,
            "ScaleUpTriggerFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="scaleup_trigger.handler",
            code=lambda_.Code.from_asset(
                "./comfyui_aws_stack/lambda/admin_lambda"),
            timeout=Duration.seconds(amount=60),
            environment={
                "ASG_NAME": auto_scaling_group.auto_scaling_group_name,
                "ECS_CLUSTER_NAME": cluster.cluster_name,
                "ECS_SERVICE_NAME": service.service_name
            }
        )
        grant_asg_describe(scaleup_trigger_lambda)
        grant_asg_scale(scaleup_trigger_lambda)
        grant_ecs_describe(scaleup_trigger_lambda)
        grant_ecs_update(scaleup_trigger_lambda)

        scalein_listener_lambda = lambda_.Function(
            scope,
            "ScaleinListenerFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="scalein_listener.handler",
            code=lambda_.Code.from_asset(
                "./comfyui_aws_stack/lambda/admin_lambda"),
            timeout=Duration.seconds(amount=60),
            environment={
                "ASG_NAME": auto_scaling_group.auto_scaling_group_name,
                "ECS_CLUSTER_NAME": cluster.cluster_name,
                "ECS_SERVICE_NAME": service.service_name
            }
        )
        grant_asg_describe(scalein_listener_lambda)
        grant_ecs_describe(scalein_listener_lambda)

        scaleup_listener_lambda = lambda_.Function(
            scope,
            "ScaleupListenerFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="scaleup_listener.handler",
            code=lambda_.Code.from_asset(
                "./comfyui_aws_stack/lambda/admin_lambda"),
            timeout=Duration.seconds(amount=60),
            environment={
                "ASG_NAME": auto_scaling_group.auto_scaling_group_name,
                "ECS_CLUSTER_NAME": cluster.cluster_name,
                "ECS_SERVICE_NAME": service.service_name
            }
        )
        grant_asg_describe(scaleup_listener_lambda)
        grant_ecs_describe(scaleup_listener_lambda)

        signout_lambda = lambda_.Function(
            scope,
            "SignoutFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="signout.handler",
            code=lambda_.Code.from_asset(
                "./comfyui_aws_stack/lambda/admin_lambda"),
            timeout=Duration.seconds(amount=60),
            environment={
                "REDIRECT_URL": user_pool_logout_url
            }
        )

        lambda_admin_target_group = elbv2.ApplicationTargetGroup(
            scope,
            "LambdaAdminTargetGroup",
            vpc=vpc,
            target_type=elbv2.TargetType.LAMBDA,
            targets=[targets.LambdaTarget(admin_lambda)]
        )

        lambda_restart_docker_target_group = elbv2.ApplicationTargetGroup(
            scope,
            "LambdaRestartDockerTargetGroup",
            vpc=vpc,
            target_type=elbv2.TargetType.LAMBDA,
            targets=[targets.LambdaTarget(restart_docker_lambda)]
        )

        lambda_shutdown_target_group = elbv2.ApplicationTargetGroup(
            scope,
            "LambdaShutdownTargetGroup",
            vpc=vpc,
            target_type=elbv2.TargetType.LAMBDA,
            targets=[targets.LambdaTarget(shutdown_lambda)]
        )

        lambda_scaleup_target_group = elbv2.ApplicationTargetGroup(
            scope,
            "LambdaScaleupTargetGroup",
            vpc=vpc,
            target_type=elbv2.TargetType.LAMBDA,
            targets=[targets.LambdaTarget(scaleup_trigger_lambda)]
        )

        lambda_signout_target_group = elbv2.ApplicationTargetGroup(
            scope,
            "LambdaSignoutTargetGroup",
            vpc=vpc,
            target_type=elbv2.TargetType.LAMBDA,
            targets=[targets.LambdaTarget(signout_lambda)]
        )

        # CloudWatch Event Rule for ASG scale-in events
        scale_in_event_pattern = events.EventPattern(
            source=["aws.autoscaling"],
            detail_type=["EC2 Instance-terminate Lifecycle Action"],
            detail={
                "AutoScalingGroupName": [auto_scaling_group.auto_scaling_group_name]
            }
        )

        scale_in_event_rule = events.Rule(
            scope,
            "ScaleInEventRule",
            event_pattern=scale_in_event_pattern,
            targets=[event_targets.LambdaFunction(scalein_listener_lambda)]
        )

        ecs_task_state_change_event_rule = events.Rule(
            scope,
            "EcsTaskStateChangeRule",
            event_pattern=events.EventPattern(
                source=["aws.ecs"],
                detail_type=["ECS Task State Change"],
                detail={
                    "clusterArn": [cluster.cluster_arn],
                    "lastStatus": ["RUNNING"],
                }
            ),
            targets=[event_targets.LambdaFunction(scaleup_listener_lambda)]
        )

        # Output

        self.restart_docker_lambda = restart_docker_lambda
        self.scalein_listener_lambda = scalein_listener_lambda
        self.scaleup_listener_lambda = scaleup_listener_lambda
        self.lambda_admin_target_group = lambda_admin_target_group
        self.lambda_restart_docker_target_group = lambda_restart_docker_target_group
        self.lambda_shutdown_target_group = lambda_shutdown_target_group
        self.lambda_scaleup_target_group = lambda_scaleup_target_group
        self.lambda_signout_target_group = lambda_signout_target_group

    def add_environments(self,
                         lambda_admin_rule: elbv2.ApplicationListenerRule,
                         ):
        self.restart_docker_lambda.add_environment(
            "LISTENER_RULE_ARN", lambda_admin_rule.listener_rule_arn)
        self.scalein_listener_lambda.add_environment(
            "LISTENER_RULE_ARN", lambda_admin_rule.listener_rule_arn)
        self.scaleup_listener_lambda.add_environment(
            "LISTENER_RULE_ARN", lambda_admin_rule.listener_rule_arn)

        for function in [
            self.restart_docker_lambda,
            self.scalein_listener_lambda,
            self.scaleup_listener_lambda,
        ]:
            function.add_to_role_policy(iam.PolicyStatement(
                actions=["elasticloadbalancing:ModifyRule"],
                resources=[lambda_admin_rule.listener_rule_arn],
            ))
