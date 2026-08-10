import json
import boto3
import os

def handler(event, context):
    asg_names = [os.environ.get("ASG_NAME")]
    ecs_cluster_name = os.environ.get("ECS_CLUSTER_NAME")
    ecs_service_name = os.environ.get("ECS_SERVICE_NAME")

    asg_client = boto3.client('autoscaling')
    ecs_client = boto3.client('ecs')

    messages = []

    try:
        for asg_name in asg_names:
            if not asg_name:
                messages.append("ASG_NAME environment variable missing.")
                continue

            # Check ASG status
            asg_response = asg_client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )
            asg_list = asg_response.get('AutoScalingGroups', [])
            if not asg_list:
                messages.append(f"ASG '{asg_name}' not found.")
                continue

            desired_capacity = asg_list[0]['DesiredCapacity']
            messages.append(f"ASG '{asg_name}' desired capacity: {desired_capacity}")

            # Get ECS service status (only once)
            current_service_desired_count = 0
            running_tasks_count = 0
            if ecs_cluster_name and ecs_service_name:
                ecs_response = ecs_client.describe_services(
                    cluster=ecs_cluster_name,
                    services=[ecs_service_name]
                )
                services = ecs_response.get('services', [])
                if services:
                    current_service_desired_count = services[0]['desiredCount']
                    running_tasks_count = services[0]['runningCount']
                    messages.append(
                        f"ECS service '{ecs_service_name}': desiredCount={current_service_desired_count}, runningCount={running_tasks_count}"
                    )

            # Always ensure ASG desired capacity is at least 1
            if desired_capacity < 1:
                asg_client.set_desired_capacity(
                    AutoScalingGroupName=asg_name,
                    DesiredCapacity=1,
                    HonorCooldown=False
                )
                messages.append(f"Triggered ASG scale-up for '{asg_name}'.")

            # Ensure ECS service is scaled to 1 if needed
            if ecs_cluster_name and ecs_service_name:
                if current_service_desired_count < 1 or running_tasks_count < 1:
                    ecs_client.update_service(
                        cluster=ecs_cluster_name,
                        service=ecs_service_name,
                        desiredCount=1
                    )
                    messages.append(f"ECS service '{ecs_service_name}' scale-up triggered.")

    except Exception as e:
        messages.append(f"Error: {str(e)}")

    print(" | ".join(messages))

    return {
        "statusCode": 302,
        "headers": {"Location": "/"},
        "body": json.dumps({"message": " | ".join(messages)})
    }
