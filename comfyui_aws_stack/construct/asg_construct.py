from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_autoscaling as autoscaling,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    Aws,
    Duration,
    RemovalPolicy,
    Tags,
)
from constructs import Construct
from cdk_nag import NagSuppressions


class AsgConstruct(Construct):
    auto_scaling_group: autoscaling.AutoScalingGroup

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            vpc: ec2.Vpc,
            use_spot: bool,
            spot_price: str,
            auto_scale_down: bool,
            schedule_auto_scaling: bool,
            timezone: str,
            ecs_cluster_name: str,
            schedule_scale_down: str,
            schedule_scale_up: str,
            instance_type: str,
            enable_nvme_model_cache: bool = True,
            subnet_id: str = None,
            desired_capacity: int = 1,
            min_capacity: int = 0,
            max_capacity: int = 1,        
            launch_template_id: str = None,
            auto_scaling_group_id: str = "ASG",
            **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Set unique IDs based on construct_id if not provided
        if launch_template_id is None:
            launch_template_id = f"{construct_id}LaunchTemplate"
    
        if auto_scaling_group_id is None:
            auto_scaling_group_id = f"{construct_id}AutoScalingGroup"
        

        # Create Auto Scaling Group Security Group
        asg_security_group = ec2.SecurityGroup(
            self,
            f"{construct_id}SecurityGroup", 
            vpc=vpc,
            description="Security Group for ASG",
            allow_all_outbound=True,
        )

        # EC2 Role for AWS internal use (if necessary)
        ec2_role = iam.Role(
            self,
            f"{construct_id}Role", 
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"),
            ]
        )

        volume_resource = (
            f"arn:{Aws.PARTITION}:ec2:{Aws.REGION}:"
            f"{Aws.ACCOUNT_ID}:volume/*"
        )
        instance_resource = (
            f"arn:{Aws.PARTITION}:ec2:{Aws.REGION}:"
            f"{Aws.ACCOUNT_ID}:instance/*"
        )

        # REX-Ray documents these EBS discovery calls as required. The
        # list-style EC2 Describe APIs do not support resource ARNs or
        # resource-tag conditions, so restrict them to the deployment Region.
        ec2_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "ec2:DescribeAvailabilityZones",
                "ec2:DescribeInstances",
                "ec2:DescribeSnapshots",
                "ec2:DescribeTags",
                "ec2:DescribeVolumes",
                "ec2:DescribeVolumesModifications",
                "ec2:DescribeVolumeStatus",
            ],
            resources=["*"],
            conditions={
                "StringEquals": {
                    "aws:RequestedRegion": Aws.REGION,
                },
            },
        ))
        ec2_role.add_to_policy(iam.PolicyStatement(
            actions=["ec2:DescribeVolumeAttribute"],
            resources=[volume_resource],
        ))
        ec2_role.add_to_policy(iam.PolicyStatement(
            actions=["ec2:CreateVolume"],
            resources=[volume_resource],
            conditions={
                "Bool": {
                    "ec2:Encrypted": "true",
                },
                "StringEquals": {
                    "aws:RequestedRegion": Aws.REGION,
                    "ec2:VolumeType": "gp3",
                },
                "NumericEquals": {
                    "ec2:VolumeSize": "5000",
                },
                # The persistent data volume must be newly created. Omitting
                # snapshot permission and requiring this request key to be
                # absent prevents REX-Ray from restoring arbitrary snapshots.
                "Null": {
                    "ec2:ParentSnapshot": "true",
                },
            },
        ))
        ec2_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "ec2:CreateTags",
                "ec2:DeleteTags",
                "ec2:DeleteVolume",
                "ec2:ModifyVolume",
            ],
            resources=[volume_resource],
        ))

        user_data_script = ec2.UserData.for_linux()
        user_data_script.add_commands(
            "set -euxo pipefail",
            "systemctl stop ecs || true",
            f"echo ECS_CLUSTER={ecs_cluster_name} >> /etc/ecs/ecs.config",
        )

        if enable_nvme_model_cache:
            user_data_script.add_commands(
                'CACHE_MOUNT="/mnt/comfy-cache"',
                'mkdir -p "$CACHE_MOUNT"',
                (
                    "INSTANCE_STORE_DEVICE=$(lsblk -dn -o NAME,MODEL "
                    "| awk '$0 ~ /Amazon EC2 NVMe Instance Storage/ "
                    "{print \"/dev/\" $1; exit}' || true)"
                ),
                'if [ -n "$INSTANCE_STORE_DEVICE" ]; then',
                '  echo "Preparing ComfyUI cache on $INSTANCE_STORE_DEVICE"',
                '  if ! blkid "$INSTANCE_STORE_DEVICE" >/dev/null 2>&1; then',
                '    mkfs.ext4 -F -m 0 -L COMFY_CACHE "$INSTANCE_STORE_DEVICE"',
                "  fi",
                (
                    '  CACHE_UUID=$(blkid -s UUID -o value '
                    '"$INSTANCE_STORE_DEVICE" || true)'
                ),
                '  if [ -n "$CACHE_UUID" ]; then',
                (
                    '    grep -q "UUID=$CACHE_UUID " /etc/fstab '
                    '|| echo "UUID=$CACHE_UUID $CACHE_MOUNT ext4 '
                    'defaults,nofail,noatime 0 2" >> /etc/fstab'
                ),
                '    if mountpoint -q "$CACHE_MOUNT" || mount "$CACHE_MOUNT"; then',
                '      chown 1000:1000 "$CACHE_MOUNT"',
                '      chmod 0775 "$CACHE_MOUNT"',
                '      touch "$CACHE_MOUNT/.comfyui-instance-store"',
                (
                    '      chown 1000:1000 '
                    '"$CACHE_MOUNT/.comfyui-instance-store"'
                ),
                "    else",
                (
                    '      echo "WARNING: unable to mount instance-store cache; '
                    'ComfyUI will use EBS" >&2'
                ),
                "    fi",
                "  fi",
                "else",
                (
                    '  echo "WARNING: no EC2 instance-store NVMe device found; '
                    'ComfyUI will use EBS" >&2'
                ),
                "fi",
            )

        user_data_script.add_commands(
            (
                "TOKEN=$(curl -sS -X PUT "
                '-H "X-aws-ec2-metadata-token-ttl-seconds: 21600" '
                "http://169.254.169.254/latest/api/token)"
            ),
            (
                "REGION=$(curl -sS "
                '-H "X-aws-ec2-metadata-token: $TOKEN" '
                "http://169.254.169.254/latest/meta-data/placement/region)"
            ),
            (
                "if ! docker plugin inspect "
                "public.ecr.aws/j1l5j1d1/rexray-ebs >/dev/null 2>&1; then "
                "docker plugin install "
                "public.ecr.aws/j1l5j1d1/rexray-ebs "
                "--grant-all-permissions "
                "REXRAY_PREEMPT=true EBS_REGION=$REGION; "
                "fi"
            ),
            "systemctl restart docker",
            "systemctl enable --now ecs",
        )

        # Create an Auto Scaling Group
        launchTemplate = ec2.LaunchTemplate(
            self,
            launch_template_id,
            machine_image=ecs.EcsOptimizedImage.amazon_linux2023(
                hardware_type=ecs.AmiHardwareType.GPU
            ),
            role=ec2_role,
            security_group=asg_security_group,
            user_data=user_data_script,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(volume_size=200,
                                                     encrypted=True)
                )
            ],
        )

        asg_subnet_selection = ec2.SubnetSelection(
            # Fresh stacks can search private AZs for GPU capacity.
            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
        )
        if subnet_id:
            # An existing REX-Ray EBS volume is AZ-bound. Pinning the host to
            # its current subnet guarantees that a replacement can reattach it.
            asg_subnet_selection = ec2.SubnetSelection(
                subnets=[
                    ec2.Subnet.from_subnet_id(
                        self,
                        f"{construct_id}ExistingEbsSubnet",
                        subnet_id,
                    )
                ]
            )

        auto_scaling_group = autoscaling.AutoScalingGroup(
            self,
            auto_scaling_group_id,
            vpc=vpc,
            vpc_subnets=asg_subnet_selection,
            # Use Mixed Instance Policy to increase availability in case capacity is not available.
            mixed_instances_policy=autoscaling.MixedInstancesPolicy(
                instances_distribution=autoscaling.InstancesDistribution(
                    on_demand_base_capacity=0,
                    on_demand_percentage_above_base_capacity=0 if use_spot else 100,
                    on_demand_allocation_strategy=autoscaling.OnDemandAllocationStrategy.LOWEST_PRICE,
                    spot_allocation_strategy=autoscaling.SpotAllocationStrategy.LOWEST_PRICE,
                    spot_instance_pools=1,
                    spot_max_price=spot_price,
                ),
                launch_template=launchTemplate,
                launch_template_overrides=[
                    autoscaling.LaunchTemplateOverrides(
                        instance_type=ec2.InstanceType(instance_type)
                    ),
                ],                
            ),
            min_capacity=min_capacity,
            max_capacity=max_capacity,
            desired_capacity=desired_capacity,
            new_instances_protected_from_scale_in=False,
            update_policy=autoscaling.UpdatePolicy.rolling_update(
                max_batch_size=1,
                min_instances_in_service=0,
                pause_time=Duration.minutes(20),
                wait_on_resource_signals=False,
            ),
        )

        auto_scaling_group.apply_removal_policy(RemovalPolicy.DESTROY)
        Tags.of(auto_scaling_group).add(
            "comfyui:ebs-host",
            "true",
            apply_to_launched_instances=True,
        )

        # Attach and detach authorize both the EBS volume and the target
        # instance. The REX-Ray EBS driver does not support user-defined EBS
        # tags, so a volume-tag condition would block plugin-managed volumes.
        # Keep the volume side account/Region scoped and require the ASG tag on
        # the instance side.
        ec2_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "ec2:AttachVolume",
                "ec2:DetachVolume",
            ],
            resources=[volume_resource],
        ))
        ec2_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "ec2:AttachVolume",
                "ec2:DetachVolume",
            ],
            resources=[instance_resource],
            conditions={
                "StringEquals": {
                    "ec2:ResourceTag/comfyui:ebs-host": "true",
                },
            },
        ))

        cpu_utilization_metric = cloudwatch.Metric(
            namespace='AWS/EC2',
            metric_name='CPUUtilization',
            dimensions_map={
                'AutoScalingGroupName': auto_scaling_group.auto_scaling_group_name
            },
            statistic='Average',
            period=Duration.minutes(1)
        )

        # Scale down to zero if no activity for an hour
        if auto_scale_down:
            # create a CloudWatch alarm to track the CPU utilization
            cpu_alarm = cloudwatch.Alarm(
                scope,
                f"{construct_id}CPUUtilizationAlarm", 
                metric=cpu_utilization_metric,
                threshold=1,
                evaluation_periods=60,
                datapoints_to_alarm=60,
                comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD
            )
            scaling_action = autoscaling.StepScalingAction(
                scope,
                f"{construct_id}ScalingAction", 
                auto_scaling_group=auto_scaling_group,
                adjustment_type=autoscaling.AdjustmentType.CHANGE_IN_CAPACITY,
                cooldown=Duration.seconds(120)
            )
            # Add scaling adjustments
            scaling_action.add_adjustment(
                # scaling adjustment (reduce instance count by 1)
                adjustment=-1,
                upper_bound=1   # upper threshold for CPU utilization
            )
            scaling_action.add_adjustment(
                adjustment=0,   # No change in instance count
                lower_bound=1   # Apply this when the metric is above 2%
            )
            # Link the StepScalingAction to the CloudWatch alarm
            cpu_alarm.add_alarm_action(
                cw_actions.AutoScalingAction(scaling_action)
            )
        
        # Scheduled Scaling:
        # (default) set desired capacity to 0 after work hour and 1 on start of work hour (only mon-fri)
        # Use TZ identifier for timezone https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
        if schedule_auto_scaling:
            # Create a scheduled action to set the desired capacity to 0
            after_work_hours_action = autoscaling.ScheduledAction(
                scope,
                f"{construct_id}AfterWorkHoursAction", 
                auto_scaling_group=auto_scaling_group,
                desired_capacity=0,
                time_zone=timezone,
                schedule=autoscaling.Schedule.expression(schedule_scale_down)
            )
            # Create a scheduled action to set the desired capacity to 1
            start_work_hours_action = autoscaling.ScheduledAction(
                scope,
                f"{construct_id}StartWorkHoursAction", 
                auto_scaling_group=auto_scaling_group,
                desired_capacity=1,
                time_zone=timezone,
                schedule=autoscaling.Schedule.expression(schedule_scale_up)
            )

        # Nag

        NagSuppressions.add_resource_suppressions(
            [asg_security_group],
            suppressions=[
                {"id": "AwsSolutions-EC23",
                 "reason": "The Security Group and ALB needs to allow 0.0.0.0/0 inbound access for the ALB to be publicly accessible. Additional security is provided via Cognito authentication."
                 },
                {"id": "AwsSolutions-ELB2",
                 "reason": "Adding access logs requires extra S3 bucket so removing it for sample purposes."},
            ],
            apply_to_children=True
        )

        NagSuppressions.add_resource_suppressions(
            [auto_scaling_group],
            suppressions=[
                {"id": "AwsSolutions-L1",
                 "reason": "Lambda Runtime is provided by custom resource provider and drain ecs hook implicitely and not critical for sample"
                 },
                {"id": "AwsSolutions-SNS2",
                 "reason": "SNS topic is implicitly created by LifeCycleActions and is not critical for sample purposes."
                 },
                {"id": "AwsSolutions-SNS3",
                 "reason": "SNS topic is implicitly created by LifeCycleActions and is not critical for sample purposes."
                 },
                {"id": "AwsSolutions-AS3",
                 "reason": "Not all notifications are critical for ComfyUI sample"
                 }
            ],
            apply_to_children=True
        )

        # Output

        self.auto_scaling_group = auto_scaling_group
