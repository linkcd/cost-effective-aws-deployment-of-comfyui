import json
import boto3
import os

def handler(event, context):
    # Check required environment variables early
    required_env_vars = [
        'ASG_NAME',
        'ECS_CLUSTER_NAME',
        'ECS_SERVICE_NAME',
        'LISTENER_RULE_ARN',
    ]
    missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
    if missing_vars:
        return {
            'statusCode': 400,
            'body': json.dumps(f"Missing environment variables: {', '.join(missing_vars)}")
        }

    asg_name = os.environ['ASG_NAME']
    cluster_name = os.environ['ECS_CLUSTER_NAME']
    service_name = os.environ['ECS_SERVICE_NAME']
    listener_rule_arn = os.environ['LISTENER_RULE_ARN']

    asg_client = boto3.client('autoscaling')
    ecs_client = boto3.client('ecs')
    elbv2_client = boto3.client('elbv2')

    try:
        # Get ASG info
        asg_response = asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )
        if not asg_response['AutoScalingGroups']:
            return {
                'statusCode': 404,
                'body': json.dumps(f"Auto Scaling Group '{asg_name}' not found")
            }

        asg_group = asg_response['AutoScalingGroups'][0]
        desired_capacity = asg_group['DesiredCapacity']

        response = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        all_services = response.get('services', [])

        # Check if all ECS services are stopped (runningCount == 0)
        all_services_down = bool(all_services) and all(
            s['runningCount'] == 0 for s in all_services
        )

        if desired_capacity == 0 and all_services_down:
            # Modify only the path condition; omitting Actions preserves the
            # existing Cognito authentication and Lambda forwarding actions.
            elbv2_client.modify_rule(
                RuleArn=listener_rule_arn,
                Conditions=[
                    {
                        'Field': 'path-pattern',
                        'Values': ['/', '/admin']
                    }
                ]
            )
            print(f"Listener rule '{listener_rule_arn}' updated successfully because ASG '{asg_name}' is at desired capacity 0 and all ECS services are down.")
        else:
            print(f"No modification needed: desired_capacity={desired_capacity}, all_services_down={all_services_down}")

    except Exception as e:
        print(f"Error modifying listener rule: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps("Error occurred while modifying Listener Rule.")
        }

    return {
        "statusCode": 200,
        "body": json.dumps("Listener rule check/modify completed.")
    }
