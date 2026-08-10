import json
import boto3
import os

def handler(event, context):
    # Read ASG names from environment variables
    asg_names = [os.environ.get('ASG_NAME')]
    asg_names = [name for name in asg_names if name]  # Filter out None

    # Optional: capture ECS cluster (not used here, but available for extension)
    ecs_cluster_name = os.environ.get("ECS_CLUSTER_NAME")

    if not asg_names:
        return {
            'statusCode': 400,
            'body': json.dumps("No ASG names provided in environment variables (ASG_NAME)")
        }

    asg_client = boto3.client('autoscaling')
    results = {}

    for asg_name in asg_names:
        try:
            # Describe the ASG
            response = asg_client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )

            if not response.get('AutoScalingGroups'):
                results[asg_name] = "ASG not found"
                continue

            group = response['AutoScalingGroups'][0]
            desired_capacity = group['DesiredCapacity']
            min_size = group['MinSize']

            if min_size > 0:
                results[asg_name] = f"MinSize is {min_size}, cannot scale down to 0"
                continue

            if desired_capacity > 0:
                asg_client.set_desired_capacity(
                    AutoScalingGroupName=asg_name,
                    DesiredCapacity=0,
                    HonorCooldown=False
                )
                results[asg_name] = "Set desired capacity to 0 (shutting down)"
            else:
                results[asg_name] = "Already shut down"

        except Exception as e:
            results[asg_name] = f"Error: {str(e)}"

    return {
        'statusCode': 200,
        'body': json.dumps(results),
        'headers': {
            'Content-Type': 'application/json'
        }
    }
