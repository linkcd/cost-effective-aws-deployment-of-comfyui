from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_servicediscovery as servicediscovery,
    aws_ecr_assets as ecr_assets,
    aws_logs as logs,
    aws_iam as iam,
    aws_cognito as cognito,
    aws_autoscaling as autoscaling,
    aws_elasticloadbalancingv2 as elbv2,
    aws_s3 as s3,
    aws_sns as sns,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
    Duration,
    RemovalPolicy,
)
from constructs import Construct
from cdk_nag import NagSuppressions
import datetime


class EcsConstruct(Construct):
    cluster: ecs.Cluster
    service: ecs.IService
    ecs_target_group: elbv2.ApplicationTargetGroup
    ecs_health_topic: sns.Topic

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        comfy_asg: autoscaling.AutoScalingGroup,
        alb_security_group: ec2.SecurityGroup,
        is_sagemaker_studio: bool,
        suffix: str,
        region: str,
        user_pool: cognito.UserPool,
        user_pool_client: cognito.UserPoolClient,
        cluster: ecs.Cluster,
        enable_nvme_model_cache: bool = True,
        comfyui_ebs_volume_name: str = None,
        slack_workspace_id: str = None,
        slack_channel_id: str = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # === Capacity Providers ===
        comfy_capacity_provider = ecs.AsgCapacityProvider(
            self,
            f"{construct_id}ComfyCapacityProvider",
            auto_scaling_group=comfy_asg,
            enable_managed_scaling=False,
            enable_managed_termination_protection=False,
            target_capacity_percent=100,
        )


        cluster.add_asg_capacity_provider(comfy_capacity_provider)

        # === S3 Bucket for ComfyUI file storage ===
        comfyui_bucket = s3.Bucket(
            self,
            f"{construct_id}ComfyUIBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
        )

        # === IAM Role for Task Execution ===
        task_exec_role = iam.Role(
            self,
            f"{construct_id}ECSTaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                ),
            ],
        )

        # Bedrock access for ComfyUI custom nodes
        task_exec_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:ListFoundationModels",
            ],
            resources=["*"]
        ))

        # S3 access for file storage
        comfyui_bucket.grant_read_write(task_exec_role)

        # === Log Group ===
        log_group = logs.LogGroup(
            self,
            f"{construct_id}LogGroup",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # === ComfyUI Docker Image Asset ===
        docker_image_asset = ecr_assets.DockerImageAsset(
            self,
            f"{construct_id}ComfyUIImage",
            directory="comfyui_aws_stack/docker",
            platform=ecr_assets.Platform.LINUX_AMD64,
            network_mode=ecr_assets.NetworkMode.custom("sagemaker") if is_sagemaker_studio else None,
        )

        # Preserve an explicitly selected REX-Ray volume across task revisions.
        # The timestamp fallback retains the existing fresh-deployment behavior.
        unique_suffix = (
            suffix + "-" + datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        )
        volume_name = (
            comfyui_ebs_volume_name
            if comfyui_ebs_volume_name
            else "ComfyUIVolume-" + unique_suffix
        )
        
        comfy_volume = ecs.Volume(
            name=volume_name,
            docker_volume_configuration=ecs.DockerVolumeConfiguration(
                scope=ecs.Scope.SHARED,
                driver="public.ecr.aws/j1l5j1d1/rexray-ebs",
                driver_opts={
                    "volumetype": "gp3",
                    "size": "5000"  # Size in GiB
                },
                autoprovision=True
            )
        )

        task_volumes = [comfy_volume]
        cache_volume = None
        if enable_nvme_model_cache:
            cache_volume = ecs.Volume(
                name="ComfyUIModelCache",
                host=ecs.Host(source_path="/mnt/comfy-cache"),
            )
            task_volumes.append(cache_volume)

        # === ComfyUI Task Definition ===
        comfy_task_definition = ecs.Ec2TaskDefinition(
            self,
            f"{construct_id}ComfyTaskDef",
            network_mode=ecs.NetworkMode.AWS_VPC,
            task_role=task_exec_role,
            execution_role=task_exec_role,
            volumes=task_volumes,
        )

        cache_start_period = (
            Duration.minutes(15)
            if enable_nvme_model_cache
            else Duration.seconds(30)
        )

        comfy_container = comfy_task_definition.add_container(
            "ComfyUIContainer",
            image=ecs.ContainerImage.from_ecr_repository(
                docker_image_asset.repository,
                docker_image_asset.image_tag,
            ),
            gpu_count=1,
            memory_reservation_mib=15000,
            # ComfyUI runs on the only GPU in the ASG, so the replacement task
            # cannot start until the old container releases it.
            stop_timeout=Duration.seconds(30),
            logging=ecs.LogDriver.aws_logs(stream_prefix="comfy-ui", log_group=log_group),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8181/system_stats || exit 1"],
                interval=Duration.seconds(15),
                timeout=Duration.seconds(10),
                retries=8,
                start_period=cache_start_period,
            ),
            environment={
                "AWS_REGION": region,
                "COGNITO_USER_POOL_ID": user_pool.user_pool_id,
                "COGNITO_CLIENT_ID": user_pool_client.user_pool_client_id,
                "COMFYUI_S3_BUCKET": comfyui_bucket.bucket_name,
                "COMFYUI_MODEL_CACHE_ENABLED": (
                    "1" if enable_nvme_model_cache else "0"
                ),
                "COMFYUI_MODEL_CACHE_ROOT": "/mnt/comfy-cache",
            },
        )

        comfy_container.add_mount_points(
            ecs.MountPoint(
                container_path="/home/user/opt/ComfyUI",
                source_volume=comfy_volume.name,
                read_only=False,
            )
        )

        if cache_volume is not None:
            comfy_container.add_mount_points(
                ecs.MountPoint(
                    container_path="/mnt/comfy-cache",
                    source_volume=cache_volume.name,
                    read_only=False,
                )
            )

        # comfy_container.add_port_mappings(
        #     ecs.PortMapping(container_port=8181, host_port=8181, protocol=ecs.Protocol.TCP)
        # )
        comfy_container.add_port_mappings(
            ecs.PortMapping(container_port=8181, host_port=8181, protocol=ecs.Protocol.TCP),
            ecs.PortMapping(container_port=8189, host_port=8189, protocol=ecs.Protocol.TCP),
            ecs.PortMapping(container_port=8190, host_port=8190, protocol=ecs.Protocol.TCP),
            ecs.PortMapping(container_port=8191, host_port=8191, protocol=ecs.Protocol.TCP),
        )

        comfy_sg = ec2.SecurityGroup(
            self,
            f"{construct_id}ComfyServiceSecurityGroup",
            vpc=vpc,
            description="ComfyUI ECS Security Group",
            allow_all_outbound=True,
        )
        comfy_sg.add_ingress_rule(
            ec2.Peer.security_group_id(alb_security_group.security_group_id),
            ec2.Port.tcp(8181),
            "Allow traffic to ComfyUI",
        )

        for port in range(8189, 8192):
            comfy_sg.add_ingress_rule(
                ec2.Peer.security_group_id(alb_security_group.security_group_id),
                ec2.Port.tcp(port),
                f"Allow inbound traffic on port {port}"
            )
        
        # Allow internal access to worker ports only from within VPC CIDR
        for port in range(8189, 8192):
            comfy_sg.add_ingress_rule(
                ec2.Peer.ipv4(vpc.vpc_cidr_block),
                ec2.Port.tcp(port),
                f"Allow internal VPC traffic on port {port}"
            )        


        comfy_service = ecs.Ec2Service(
            self,
            f"{construct_id}ComfyUIService",
            cluster=cluster,
            task_definition=comfy_task_definition,
            capacity_provider_strategies=[
                ecs.CapacityProviderStrategy(
                    capacity_provider=comfy_capacity_provider.capacity_provider_name,
                    weight=1,
                )
            ],
            placement_constraints=[ecs.PlacementConstraint.distinct_instances()],
            security_groups=[comfy_sg],
            health_check_grace_period=cache_start_period,
            min_healthy_percent=0,
            cloud_map_options=ecs.CloudMapOptions(
                name="comfy",
                cloud_map_namespace=cluster.default_cloud_map_namespace,
            ),
        )

        comfy_target_group = elbv2.ApplicationTargetGroup(
            self,
            f"{construct_id}EcsTargetGroup",
            port=8181,
            vpc=vpc,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            targets=[
                comfy_service.load_balancer_target(
                    container_name=comfy_container.container_name, container_port=8181
                )
            ],
            health_check=elbv2.HealthCheck(
                enabled=True,
                path="/system_stats",
                port="8181",
                healthy_http_codes="200",
                interval=Duration.seconds(10),
                timeout=Duration.seconds(5),
                unhealthy_threshold_count=3,
                healthy_threshold_count=2,
            ),
        )
        # The ALB default is 300 seconds. A shorter drain substantially reduces
        # single-GPU task replacement time while still allowing brief requests
        # and WebSocket connections to finish.
        comfy_target_group.set_attribute(
            "deregistration_delay.timeout_seconds",
            "30",
        )

        comfy_service.enable_execute_command = True

        # NagSuppressions - apply carefully to correct resources
        NagSuppressions.add_resource_suppressions(
            [alb_security_group, comfy_sg],
            suppressions=[
                {"id": "AwsSolutions-EC23", "reason": "Allow 0.0.0.0/0 for ALB access via Cognito"},
                {"id": "AwsSolutions-ELB2", "reason": "Omitting access logs for simplicity"},
            ],
            apply_to_children=True,
        )

        NagSuppressions.add_resource_suppressions(
            [comfy_task_definition],
            suppressions=[
                {"id": "AwsSolutions-ECS2", "reason": "AWS_REGION is added automatically"},
            ],
            apply_to_children=True,
        )

        NagSuppressions.add_resource_suppressions(
            [comfyui_bucket],
            suppressions=[
                {"id": "AwsSolutions-S1", "reason": "Access logs omitted for simplicity in sample deployment"},
            ],
            apply_to_children=True,
        )

        # CloudWatch Monitoring and Slack Notifications
        ecs_health_topic = None
        if slack_workspace_id and slack_channel_id:
            # Create SNS Topic for ECS Task Health Alerts
            ecs_health_topic = sns.Topic(
                self, f"{construct_id}EcsHealthTopic",
                display_name="ECS Task Health Alerts",
                enforce_ssl=True
            )

            # Monitor ECS Task Count using Container Insights
            running_tasks_metric = cloudwatch.Metric(
                namespace="ECS/ContainerInsights",
                metric_name="RunningTaskCount",
                dimensions_map={
                    "ClusterName": cluster.cluster_name,
                    "ServiceName": comfy_service.service_name
                },
                period=Duration.minutes(1)
            )

            # Alarm when task count is 0
            no_running_tasks_alarm = cloudwatch.Alarm(
                self, f"{construct_id}NoRunningTasksAlarm",
                metric=running_tasks_metric,
                evaluation_periods=3,
                threshold=0,
                comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
                alarm_description="Alert when there are no running tasks in the service",
                treat_missing_data=cloudwatch.TreatMissingData.BREACHING
            )

            # Attach SNS topic to the alarm
            no_running_tasks_alarm.add_alarm_action(
                cloudwatch_actions.SnsAction(ecs_health_topic)
            )

            # Also monitor ALB target health
            target_group_health_metric = cloudwatch.Metric(
                namespace="AWS/ApplicationELB",
                metric_name="UnHealthyHostCount",
                dimensions_map={
                    "TargetGroup": comfy_target_group.target_group_arn.split(":")[-1],
                    "LoadBalancer": "app/ComfyUIALB"
                },
                period=Duration.minutes(1)
            )

            # Create alarm for unhealthy hosts
            unhealthy_hosts_alarm = cloudwatch.Alarm(
                self, f"{construct_id}UnhealthyHostsAlarm",
                metric=target_group_health_metric,
                evaluation_periods=3,
                threshold=0,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
                alarm_description="Alert when there are unhealthy hosts in the target group",
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
            )

            # Add SNS action to the alarm
            unhealthy_hosts_alarm.add_alarm_action(
                cloudwatch_actions.SnsAction(ecs_health_topic)
            )

        # Nag
        NagSuppressions.add_resource_suppressions(
            [comfy_asg],
            suppressions=[
                {"id": "AwsSolutions-L1", "reason": "Custom lambda runtime, implicit ECS drain hook"},
                {"id": "AwsSolutions-SNS2", "reason": "SNS topic implicit by LifeCycleActions"},
                {"id": "AwsSolutions-SNS3", "reason": "SNS topic implicit by LifeCycleActions"},
                {"id": "AwsSolutions-AS3", "reason": "Not all notifications critical for sample"},
            ],
            apply_to_children=True,
        )

        if ecs_health_topic:
            NagSuppressions.add_resource_suppressions(
                [ecs_health_topic],
                suppressions=[
                    {"id": "AwsSolutions-SNS2",
                     "reason": "SNS topic is implicitly created by LifeCycleActions and is not critical for sample purposes."
                     },
                    {"id": "AwsSolutions-SNS3",
                     "reason": "SNS topic is implicitly created by LifeCycleActions and is not critical for sample purposes."
                     },
                ],
            )

        # Export class properties for external access
        self.cluster = cluster
        self.service = comfy_service
        self.ecs_target_group = comfy_target_group
        self.comfyui_bucket = comfyui_bucket
        self.ecs_health_topic = ecs_health_topic
