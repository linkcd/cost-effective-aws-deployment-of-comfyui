from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_autoscaling as autoscaling,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_lambda as lambda_,
    Duration,
    RemovalPolicy,
)
from constructs import Construct
from cdk_nag import NagSuppressions


class AsgConstruct(Construct):
    auto_scaling_group: autoscaling.AutoScalingGroup
    asg_events_topic: sns.Topic

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
            desired_capacity: int = 1,
            min_capacity: int = 0,
            max_capacity: int = 1,        
            launch_template_id: str = None,
            auto_scaling_group_id: str = "ASG",
            slack_workspace_id: str = None,
            slack_channel_id: str = None,
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
                    "AmazonEC2FullAccess"),  # check if less privilege can be given
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"),
            ]
        )

        # Attach an inline policy equivalent to AmazonEC2ContainerServiceforEC2Role
        ec2_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "ecs:RegisterContainerInstance",
                "ecs:DeregisterContainerInstance",
                "ecs:DiscoverPollEndpoint",
                "ecs:Submit*",
                "ecs:Poll",
                "ecs:StartTelemetrySession",
                "ecr:GetAuthorizationToken",
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
            ],
            resources=["*"]
        ))        

        user_data_script = ec2.UserData.for_linux()
        user_data_script.add_commands(f"""#!/bin/bash
        echo ECS_CLUSTER={ecs_cluster_name} >> /etc/ecs/ecs.config
        REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region)
        docker plugin install public.ecr.aws/j1l5j1d1/rexray-ebs --grant-all-permissions REXRAY_PREEMPT=true EBS_REGION=$REGION
        systemctl restart docker
        """)

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

        auto_scaling_group = autoscaling.AutoScalingGroup(
            self,
            auto_scaling_group_id,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnets=[vpc.private_subnets[0]]  # Only one subnet = single AZ
            ),
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
        )

        auto_scaling_group.apply_removal_policy(RemovalPolicy.DESTROY)

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

        # Notifications
        # CloudWatch Monitoring and Slack Notifications for ASG
        asg_events_topic = None
        if slack_workspace_id and slack_channel_id:
            # Create SNS Topic for ASG Scaling Events
            asg_events_topic = sns.Topic(
                self, f"{construct_id}AsgEventsTopic",
                display_name="ASG Scaling Events",
                enforce_ssl=True
            )

            # Create a Lambda function to monitor ASG activity and detect errors
            asg_monitor_lambda = lambda_.Function(
                self, f"{construct_id}AsgMonitorLambda",
                runtime=lambda_.Runtime.PYTHON_3_9,
                handler="asg.handler",
                code=lambda_.Code.from_asset(
                    "./comfyui_aws_stack/lambda/monitor_lambda"),
                environment={
                    "ASG_NAME": auto_scaling_group.auto_scaling_group_name,
                    "SNS_TOPIC_ARN": asg_events_topic.topic_arn
                },
                timeout=Duration.seconds(30)
            )

            # Grant permissions to the Lambda function
            asg_events_topic.grant_publish(asg_monitor_lambda)
            asg_monitor_lambda.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["autoscaling:DescribeScalingActivities"],
                    resources=["*"]
                )
            )

            # Create EventBridge rule to trigger Lambda on ASG error events
            events.Rule(
                self, f"{construct_id}AsgEventRule",
                event_pattern=events.EventPattern(
                    source=["aws.autoscaling"],
                    detail_type=[
                        "EC2 Instance Launch Unsuccessful",
                        "EC2 Instance Terminate Unsuccessful",
                        "EC2 Auto Scaling Instance Launch Error",
                        "EC2 Auto Scaling Instance Terminate Error",
                        "EC2 Auto Scaling Group Launch Error"
                    ],
                    resources=[auto_scaling_group.auto_scaling_group_arn]
                ),
                targets=[events_targets.LambdaFunction(asg_monitor_lambda)]
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

        if asg_events_topic:
            NagSuppressions.add_resource_suppressions(
                [asg_events_topic],
                suppressions=[
                    {"id": "AwsSolutions-SNS2",
                     "reason": "SNS topic is implicitly created by LifeCycleActions and is not critical for sample purposes."
                     },
                    {"id": "AwsSolutions-SNS3",
                     "reason": "SNS topic is implicitly created by LifeCycleActions and is not critical for sample purposes."
                     },
                ],
            )

        # Output

        self.auto_scaling_group = auto_scaling_group
        self.asg_events_topic = asg_events_topic