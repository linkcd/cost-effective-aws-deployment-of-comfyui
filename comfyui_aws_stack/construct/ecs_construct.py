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

        # Use timestamp suffix to ensure a new volume name on redeployment
        unique_suffix = suffix + "-" + datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        
        comfy_volume = ecs.Volume(
            name="ComfyUIVolume-" + unique_suffix,
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

        # === ComfyUI Task Definition ===
        comfy_task_definition = ecs.Ec2TaskDefinition(
            self,
            f"{construct_id}ComfyTaskDef",
            network_mode=ecs.NetworkMode.AWS_VPC,
            task_role=task_exec_role,
            execution_role=task_exec_role,
            volumes=[comfy_volume],
        )

        comfy_container = comfy_task_definition.add_container(
            "ComfyUIContainer",
            image=ecs.ContainerImage.from_ecr_repository(
                docker_image_asset.repository,
                docker_image_asset.image_tag,
            ),
            gpu_count=1,
            memory_reservation_mib=15000,
            stop_timeout=Duration.seconds(90),
            logging=ecs.LogDriver.aws_logs(stream_prefix="comfy-ui", log_group=log_group),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8080/system_stats || exit 1"],
                interval=Duration.seconds(15),
                timeout=Duration.seconds(10),
                retries=8,
                start_period=Duration.seconds(30),
            ),
            environment={
                "AWS_REGION": region,
                "COGNITO_USER_POOL_ID": user_pool.user_pool_id,
                "COGNITO_CLIENT_ID": user_pool_client.user_pool_client_id,
                "COMFYUI_S3_BUCKET": comfyui_bucket.bucket_name,
            },
        )

        comfy_container.add_mount_points(
            ecs.MountPoint(
                container_path="/home/user/opt/ComfyUI",
                source_volume=comfy_volume.name,
                read_only=False,
            )
        )

        # comfy_container.add_port_mappings(
        #     ecs.PortMapping(container_port=8181, host_port=8181, protocol=ecs.Protocol.TCP)
        # )
        comfy_container.add_port_mappings(
            ecs.PortMapping(container_port=8080, host_port=8080, protocol=ecs.Protocol.TCP),
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
            ec2.Port.tcp(8080),
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
            health_check_grace_period=Duration.seconds(30),
            min_healthy_percent=0,
            cloud_map_options=ecs.CloudMapOptions(
                name="comfy",
                cloud_map_namespace=cluster.default_cloud_map_namespace,
            ),
        )

        comfy_target_group = elbv2.ApplicationTargetGroup(
            self,
            f"{construct_id}EcsTargetGroup",
            port=8080,
            vpc=vpc,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            targets=[
                comfy_service.load_balancer_target(
                    container_name=comfy_container.container_name, container_port=8080
                )
            ],
            health_check=elbv2.HealthCheck(
                enabled=True,
                path="/system_stats",
                port="8080",
                healthy_http_codes="200",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                unhealthy_threshold_count=3,
                healthy_threshold_count=2,
            ),
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

        # Fix: `auto_scaling_group` is undefined; suppressions likely for comfy_asg
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

        # Export class properties for external access
        self.cluster = cluster
        self.service = comfy_service
        self.ecs_target_group = comfy_target_group
        self.comfyui_bucket = comfyui_bucket
