import boto3
import os
from datetime import datetime

def send_docker_restart_command(instance_id):
    ssm_client = boto3.client('ssm')
    command = "sudo systemctl restart docker"
    response = ssm_client.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={'commands': [command]}
    )
    return response['Command']['CommandId']

def handler(event, context):
    asg_name = os.environ.get("ASG_NAME")
    cluster_name = os.environ.get("ECS_CLUSTER_NAME")
    service_name = os.environ.get("ECS_SERVICE_NAME")
    listener_rule_arn = os.environ.get("LISTENER_RULE_ARN")

    ecs_client = boto3.client('ecs')
    scaling_client = boto3.client('autoscaling')
    elbv2_client = boto3.client('elbv2')

    try:
        # Describe ASG
        asg_response = scaling_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )
        asg_group = asg_response['AutoScalingGroups'][0]
        desired_capacity = asg_group['DesiredCapacity']
        instances = [i for i in asg_group['Instances'] if i['LifecycleState'] == 'InService']

        # Only continue if exactly one active instance
        if desired_capacity == 1 and len(instances) == 1:
            instance_id = instances[0].get('InstanceId')
            if not instance_id:
                raise ValueError("Instance ID not found.")

            if not cluster_name or not service_name:
                raise ValueError("ECS service configuration is missing.")

            response = ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            all_services = response.get('services', [])

            # Confirm all services are healthy
            all_services_healthy = bool(all_services) and all(
                s['desiredCount'] > 0 and s['runningCount'] >= s['desiredCount']
                for s in all_services
            )

            if all_services_healthy:
                command_id = send_docker_restart_command(instance_id)

                # Reset listener rule (optional safety)
                elbv2_client.modify_rule(
                    RuleArn=listener_rule_arn,
                    Conditions=[
                        {
                            'Field': 'path-pattern',
                            'Values': ['/', '/admin']
                        }
                    ]
                )
                message = f"Docker restart command sent to instance `{instance_id}`.<br>Command ID: {command_id}"
            else:
                message = "Not all ECS services are running. Docker restart aborted."
        else:
            message = "ASG must have exactly one healthy instance to restart Docker."

    except Exception as e:
        message = f"Error: {str(e)}"

    timestamp = datetime.utcnow().isoformat()
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Restart Docker</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #202020;
                color: #333;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }}
            main {{
                background-color: #ffffff;
                padding: 40px;
                border-radius: 5px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
                text-align: center;
                max-width: 600px;
            }}
            .button-link {{
                display: inline-block;
                background-color: #54646f;
                color: white;
                padding: 10px 20px;
                margin-top: 20px;
                text-decoration: none;
                border-radius: 2px;
            }}
            .button-link:hover {{
                background-color: #005fa3;
            }}
        </style>
    </head>
    <body>
        <main>
            <h2>ComfyUI Docker Restart</h2>
            <p>{message}</p>
            <p style="font-size: 0.9em; color: #666;">Time: {timestamp} UTC</p>
            <a href="/admin" class="button-link">Return to Admin Page</a>
        </main>
    </body>
    </html>
    """

    return {
        "statusCode": 200,
        "body": html,
        "headers": {
            "Content-Type": "text/html"
        }
    }
