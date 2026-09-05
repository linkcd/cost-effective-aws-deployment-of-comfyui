import boto3
import os

def handler(event, context):
    asg_names = [os.environ['ASG_NAME']]
    asg_names = [name for name in asg_names if name]  # Filter out None
    ecs_cluster_name = os.environ.get("ECS_CLUSTER_NAME")
    ecs_service_name = os.environ.get("ECS_SERVICE_NAME")

    # Clients
    asg_client = boto3.client('autoscaling')
    ecs_client = boto3.client('ecs')

    try:
        # Get ASG info from all relevant ASGs
        desired_capacity = 0
        instances = []

        for asg_name in asg_names:
            asg_response = asg_client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )
            group = asg_response['AutoScalingGroups'][0]
            desired_capacity += group['DesiredCapacity']
            instances.extend(group['Instances'])

        all_services = []
        if ecs_cluster_name and ecs_service_name:
            response = ecs_client.describe_services(
                cluster=ecs_cluster_name,
                services=[ecs_service_name]
            )
            all_services = response.get('services', [])

        # Check ECS service states
        all_services_healthy = bool(all_services) and all(
            s['desiredCount'] > 0 and s['runningCount'] >= s['desiredCount']
            for s in all_services
        )

        any_service_starting = any(
            s['desiredCount'] > 0 and s['runningCount'] < s['desiredCount']
            for s in all_services
        )

        any_service_running = any(
            s['runningCount'] > 0
            for s in all_services
        )

        # Determine the status
        if desired_capacity > 0 and all_services_healthy and instances:
            display_restart_shutdown = True
            display_scaleup = False
            status_message = ""
        elif desired_capacity > 0 and instances and any_service_starting:
            display_restart_shutdown = False
            display_scaleup = False
            status_message = "Services are currently scaling up. It may take 5–10 minutes."
        elif desired_capacity == 0 and any_service_running:
            display_restart_shutdown = False
            display_scaleup = False
            status_message = "Services are currently scaling down."
        elif desired_capacity == 0 and not any_service_running:
            display_restart_shutdown = False
            display_scaleup = True
            status_message = ""
        else:
            display_restart_shutdown = False
            display_scaleup = False
            status_message = "Services are in an unexpected state."

        # HTML Sections
        restart_shutdown_html = f"""
        <div style='display: flex; justify-content: space-around; gap: 25px;'>
            <div>
                <a href='/admin/restart' class='button-link'>Restart Docker</a>
            </div>
            <div>
                <a href='/admin/shutdown' class='button-link'>Shutdown Services</a>
            </div>
        </div>
        """ if display_restart_shutdown else ""

        scaleup_html = f"""
        <div>
            <p>Scale Up Services</p>
            <a href='/admin/scaleup' class='button-link'>Scale Up</a>
        </div>
        """ if display_scaleup else ""

        status_html = f"<p id='status-message'>{status_message}</p>" if status_message else ""
        if "scaling up" in status_message.lower():
            status_html += '<div class="loader"></div>'

        # Full HTML Page
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>ComfyUI Admin Page</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #202020;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    color: #333;
                }}
                main {{
                    text-align: center;
                    background-color: #ffffff;
                    padding: 40px;
                    border-radius: 5px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.2);
                    max-width: 600px;
                }}
                .button-link {{
                    display: inline-block;
                    background-color: #54646f;
                    color: white;
                    padding: 10px 20px;
                    text-decoration: none;
                    border-radius: 2px;
                    transition: background-color 0.3s ease;
                }}
                .button-link:hover {{
                    background-color: #005fa3;
                }}
                .loader {{
                    border: 5px solid #f3f3f3;
                    border-top: 5px solid #3498db;
                    border-radius: 50%;
                    width: 50px;
                    height: 50px;
                    animation: spin 1s linear infinite;
                    margin: 20px auto;
                }}
                @keyframes spin {{
                    0% {{ transform: rotate(0deg); }}
                    100% {{ transform: rotate(360deg); }}
                }}
            </style>
            <script>
                function checkAndReload() {{
                    const statusMessage = document.getElementById('status-message');
                    if (statusMessage && statusMessage.textContent.toLowerCase().includes("scaling up")) {{
                        setTimeout(() => {{
                            location.reload();
                        }}, 30000); // reload every 30 seconds
                    }}
                }}
                window.onload = checkAndReload;
            </script>
        </head>
        <body>
            <main>
                <h1>ComfyUI Admin</h1>
                {restart_shutdown_html}
                {scaleup_html}
                {status_html}
            </main>
        </body>
        </html>
        """
    except Exception as e:
        print(f"Error: {e}")
        html = "<p>Error occurred. Unable to determine the status of the services.</p>"

    return {
        "statusCode": 200,
        "body": html,
        "headers": {
            "Content-Type": "text/html"
        }
    }
