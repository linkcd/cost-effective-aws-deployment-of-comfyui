import json
import boto3
import os

def handler(event, context):
    # Check required environment variables early
    required_env_vars = ['ASG_NAME', 'ECS_CLUSTER_NAME', 'LISTENER_RULE_ARN']
    missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
    if missing_vars:
        return {
            'statusCode': 400,
            'body': json.dumps(f"Missing environment variables: {', '.join(missing_vars)}")
        }

    asg_name = os.environ['ASG_NAME']
    cluster_name = os.environ['ECS_CLUSTER_NAME']
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

        # Get all ECS service ARNs in the cluster
        paginator = ecs_client.get_paginator('list_services')
        service_arns = []
        for page in paginator.paginate(cluster=cluster_name):
            service_arns.extend(page['serviceArns'])

        # Describe ECS services in batches of 10
        all_services = []
        for i in range(0, len(service_arns), 10):
            response = ecs_client.describe_services(
                cluster=cluster_name,
                services=service_arns[i:i + 10]
            )
            all_services.extend(response['services'])

        # Check if all ECS services are stopped (runningCount == 0)
        all_services_down = all(s['runningCount'] == 0 for s in all_services)

        if desired_capacity == 0 and all_services_down:
            # Describe existing rule to get current conditions and actions
            rule_response = elbv2_client.describe_rules(RuleArns=[listener_rule_arn])
            if not rule_response['Rules']:
                return {
                    'statusCode': 404,
                    'body': json.dumps(f"Listener rule '{listener_rule_arn}' not found")
                }
            rule = rule_response['Rules'][0]

            conditions = rule.get('Conditions', [])
            actions = rule.get('Actions', [])

            # Modify path-pattern condition or add it if not present
            path_condition_found = False
            for cond in conditions:
                if cond.get('Field') == 'path-pattern':
                    cond['Values'] = ['/', '/admin']
                    path_condition_found = True
                    break
            if not path_condition_found:
                conditions.append({
                    'Field': 'path-pattern',
                    'Values': ['/', '/admin']
                })

            # Modify the listener rule with updated conditions
            elbv2_client.modify_rule(
                RuleArn=listener_rule_arn,
                Conditions=conditions,
                Actions=actions
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
