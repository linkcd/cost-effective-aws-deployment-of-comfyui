import json
import boto3
import os


def handler(event, context):

    scaling_client = boto3.client('autoscaling')
    ecs_client = boto3.client('ecs')
    elbv2_client = boto3.client('elbv2')

    asg_names = [os.environ.get('ASG_NAME')]
    cluster_name = os.environ.get('ECS_CLUSTER_NAME')
    service_name = os.environ.get('ECS_SERVICE_NAME')
    listener_rule_arn = os.environ.get('LISTENER_RULE_ARN')

    try:
        for asg_name in asg_names:
            if not asg_name:
                print("Missing ASG name environment variable, skipping.")
                continue

            asg_response = scaling_client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )

            asgs = asg_response.get('AutoScalingGroups', [])
            if not asgs:
                print(f"ASG '{asg_name}' not found, skipping.")
                continue

            desired_capacity = asgs[0]['DesiredCapacity']
            print(f"ASG '{asg_name}' desired capacity: {desired_capacity}")

            if desired_capacity == 1:
                # Check ECS service running tasks
                if cluster_name and service_name:
                    ecs_response = ecs_client.describe_services(
                        cluster=cluster_name,
                        services=[service_name]
                    )
                    services = ecs_response.get('services', [])
                    if services:
                        running_count = services[0].get('runningCount', 0)
                        print(f"ECS service '{service_name}' running tasks: {running_count}")

                        if running_count >= 1 and listener_rule_arn:
                            # Update listener rule to redirect to /admin path
                            elbv2_client.modify_rule(
                                RuleArn=listener_rule_arn,
                                Conditions=[
                                    {
                                        'Field': 'path-pattern',
                                        'Values': ['/admin']
                                    }
                                ]
                            )
                            print(f"Listener rule '{listener_rule_arn}' updated to redirect to /admin.")
    except Exception as e:
        print(f"Error: {e}")
        # Optionally you can handle or log the error more explicitly here

    return {"statusCode": 200}
