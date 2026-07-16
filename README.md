English | [日本語](./README_ja.md) | [中文](./README_cn.md)

# ComfyUI on AWS

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This sample repository provides a seamless and cost-effective solution to deploy ComfyUI, a powerful AI-driven image generation tool, on AWS. This repository provides a comprehensive infrastructure code and configuration setup, leveraging the power of ECS, EC2, and other AWS services. Experience a hassle-free deployment process while enjoying uncompromised security and scalability.

💡 Note: this solution will incur AWS costs. You can find more information about it in the [Cost Estimation](#cost-estimation) section.

![comfy](docs/assets/comfy.png)
![comfy gallery](docs/assets/comfy_gallery.png)

## Solution Features

1. **Effortless Deployment** 🚀: Harness the power of [Cloud Development Kit (CDK)](https://aws.amazon.com/cdk/) for a streamlined and automated deployment process.
2. **Cost Optimization** 💰: Leverage cost-saving options like Spot Instances, Automatic Shutdown, and Scheduled Scaling to maximize your budget efficiency.
3. **Robust Security** 🔒: Enjoy peace of mind with robust security measures, including Authentication (with SAML such as Microsoft Entra ID / Google Workspace), Email Domain Restriction, IP Restriction, Custom Domain SSL, Security Scans, etc.

## Architecture Overview

![AWS Architecture](docs/drawio/ComfyUI.drawio.png)

## Services

- **[Amazon VPC](https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html)** - A VPC with public and private subnets is created to host the ECS cluster
- **[ECS Cluster](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/clusters.html)** - An ECS cluster is created to run the ComfyUI task
- **[Auto Scaling Group](https://docs.aws.amazon.com/autoscaling/ec2/userguide/auto-scaling-groups.html)** - An ASG is created and associated with ECS as a capacity provider. It launches GPU instances to host ECS tasks.
- **[ECS Task Definition](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definitions.html)** - Defines the ComfyUI container and mounts EBS volume for persistence
- **[ECS Service](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_services.html)** - Creates an ECS service to run the ComfyUI task definition
- **[Application Load Balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/introduction.html)** - An ALB is setup to route traffic to the ECS service 
- **[Amazon ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/what-is-ecr.html)** - Holds the ComfyUI Docker image
- **[CloudWatch Log Group](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Working-with-log-groups-and-streams.html)** - Stores logs from the ECS task
- **[Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-identity-pools.html)** - User directory for having authentication in front of the ALB
- **[AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/waf-chapter.html)** - Block access by IP
- **[AWS Lambda](https://docs.aws.amazon.com/lambda/)** - To manage ComfyUI state

## Getting Started

### Prepare the AWS environment

For the sake of reproducability and consistency, we recommend using [Amazon SageMaker Studio Code Editor](https://docs.aws.amazon.com/sagemaker/latest/dg/code-editor.html) for deploying and testing this solution.

ℹ️ You can use your local development environment, but you will need to **make sure that you have Python 3.9+, Node.js 20+, AWS CLI, and AWS CDK properly setup**.

<details>
<summary>Click to see environment setup with Amazon SageMaker Studio Code Editor</summary>

1. Launch Amazon SageMaker Studio Code Editor using CloudFormation template from link in [sagemaker-studio-code-editor-template](https://github.com/aws-samples/sagemaker-studio-code-editor-template/). (This template launches Code Editor with some necessary capabilities including Docker, auto termination)
2. Open SageMaker Studio from url in CloudFormation Output.
3. Navigate to Code Editor from Application section in top left.
</details>

<details>
<summary>Click to see environment setup with Local environment</summary>

The following tools are required to deploy this solution locally:

- **[Python 3.9+](https://www.python.org/downloads/)** — Required for the CDK application and infrastructure code (local testing only)
- **[Node.js 20.x or later](https://nodejs.org/)** — Required for AWS CDK CLI (`npx cdk`) (local testing only)
- **[AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)** — For AWS account authentication and resource management
- **[GNU Make](https://www.gnu.org/software/make/)** — Used for build automation (pre-installed on macOS/Linux; on Windows use WSL or install via chocolatey)

> Docker is NOT required locally. All container builds happen in CodeBuild (AWS).

If you do not have AWS CLI, follow [AWS CLI Install Guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

If you do not have CDK, follow [CDK Start Guide](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html)

If you do not have Docker follow [Docker Install Guide](https://docs.docker.com/engine/install/)

If you haven't setup AWS CLI after installation, execute the following commands on your local environment:

```bash
aws configure
```

When prompted, enter your AWS Access Key ID, Secret Access Key, and then the default region name (eg. us-east-1). You can leave the output format field as default or specify it as per your preference.
</details>

> [!NOTE]
> Make sure your account has quota for GPU instance. Go to [Service Quota](https://us-west-2.console.aws.amazon.com/servicequotas/home/services/ec2/quotas/L-3819A6DF) and set `All G and VT Spot Instance Requests` to at least 8.

### Deploying ComfyUI

1. (First time only) Clone this repo (`git clone https://github.com/aws-samples/cost-effective-aws-deployment-of-comfyui.git`)
2. (First time only) cd into repo directory (`cd cost-effective-aws-deployment-of-comfyui`)
3. (First time only) Run `make setup` — creates the CodeBuild CI/CD pipeline (no Docker required)
4. Run `make` — deploys everything via CodeBuild in AWS

Set your target region before deploying:
```bash
export AWS_DEFAULT_REGION=us-west-2  # or your preferred region
make setup
make deploy
```

No local Docker or Finch is needed. All builds run in CodeBuild.

| Command | What it does |
|---------|-------------|
| `make setup` | One-time: create CodeBuild infrastructure |
| `make` | Deploy via CodeBuild (runs in AWS) |
| `make status` | Check latest build status |
| `make logs` | Print last 40 lines of build logs |
| `make destroy` | Delete ComfyUI stack (keeps CodeBuild for redeployment) |
| `make cleanup` | Delete everything (ComfyUI + CodeBuild) |

Depending on your custom_nodes and extenstions in the dockerfile, the deployment will take approx. 8-10 minutes to have ComfyUI ready
 
```
 ✅  ComfyUIStack

✨  Deployment time: 579.07s

Outputs:
ComfyUIStack.CognitoDomainName = comfyui-alb-auth-XXXXXXX
ComfyUIStack.Endpoint = ComfyUiALB-XXXXX.uw-west-2.elb.amazonaws.com
ComfyUIStack.UserPoolId = us-west-2_XXXXXXX
Stack ARN:
arn:aws:cloudformation:[us-east-1]:[your-account-id]:stack/ComfyUIStack/[uuid]

✨  Total time: 582.53s
```

You can access application from output value of `ComfyUIStack.Endpoint`.

#### Verifying the Deployment

After deployment completes, verify each component is working:

1. **CloudFormation stack** — Check the stack status is `CREATE_COMPLETE`:
   ```bash
   aws cloudformation describe-stacks --stack-name ComfyUIStack --query 'Stacks[0].StackStatus'
   ```

2. **EC2 instance running** — Confirm a GPU instance launched:
   ```bash
   aws ec2 describe-instances --filters "Name=tag:Name,Values=*ComfyUI*" "Name=instance-state-name,Values=running" --query 'Reservations[].Instances[].{Type:InstanceType,State:State.Name}' --output table
   ```

3. **ECS task healthy** — Confirm the container is running:
   ```bash
   aws ecs list-tasks --cluster $(aws ecs list-clusters --query 'clusterArns[0]' --output text) --query 'taskArns' --output text
   ```

4. **Application accessible** — Open the `Endpoint` URL from the stack outputs in a browser. You should see either the Cognito login page or the ComfyUI admin panel.

5. **Create a user** (if not using self-signup or SAML):
   ```bash
   aws cognito-idp admin-create-user --user-pool-id <UserPoolId from outputs> --username your-email@example.com --temporary-password TempPass123!
   ```

### Uploading models

1. You can install models, loras, embedding, controlnets over ComfyUI-Manager or other extension (custom node). See [User Guide](docs/USER_GUIDE.md#model-installation) for detail.
2. You can extend (optional) and execute the upload script in this repo with a preselected list of models, controlnets etc. If the SSM command is not working, make sure that the role you are using is allowed to access the EC2. You'll find some additional examples in the `/scripts/upload_models.sh` file.

```bash
# 1. SSM into EC2
aws ssm start-session --target "$(aws ec2 describe-instances --filters "Name=tag:Name,Values=ComfyUIStack/Host" "Name=instance-state-name,Values=running" --query 'Reservations[].Instances[].[InstanceId]' --output text)" --region $AWS_DEFAULT_REGION

# 2. SSH into Container
container_id=$(sudo docker container ls --format '{{.ID}} {{.Image}}' | grep 'comfyui:latest$' | awk '{print $1}')
sudo docker exec -it $container_id /bin/bash

# 3. install models, loras, controlnets or whatever you need (you can also include all in a script and execute it to install)

# FACE SWAP EXAMPLE Upscaler - https://huggingface.co/ai-forever/Real-ESRGAN
wget -c https://huggingface.co/ai-forever/Real-ESRGAN/blob/main/RealESRGAN_x2.pth -P ./models/upscale_models/
```

### Access ComfyUI

The deployed solution provides an EC2 accessible through an Application Load Balancer. The Load Balancer requires authentication through Amazon Cognito User Pool. 

You may [enable self-signup](docs/DEPLOY_OPTION.md#enable-self-sign-up), enable [SAML authentication](docs/DEPLOY_OPTION.md#saml-authentication), or manually create user in Cognito console.

### User Guide

To unlock the full potential of ComfyUI and ensure a seamless experience, explore our detailed [User Guide](docs/USER_GUIDE.md). This comprehensive resource will guide you through every step, from installation to advanced configurations, empowering you to harness the power of AI-driven image generation with ease.

- [Installing Extensions (Custom Nodes)](docs/USER_GUIDE.md#installing-extensions-custom-nodes)
    - [Recommended Extensions](docs/USER_GUIDE.md#recommended-extensions)
        - [ComfyUI Workspace Manager](docs/USER_GUIDE.md#comfyui-workspace-manager)
- [Installing Models](docs/USER_GUIDE.md#installing-models)
    - [Using ComfyUI-Manager](docs/USER_GUIDE.md#using-comfyui-manager)
    - [Using Other Extensions](docs/USER_GUIDE.md#using-other-extensions)
    - [Manual Installation](docs/USER_GUIDE.md#manual-installation)
- [Running a Workflow](docs/USER_GUIDE.md#running-a-workflow)

### Deploy Option

With our comprehensive Deploy Options, you have the power to craft a tailored solution that aligns perfectly with your security requirements, and budget constraints. Unlock the full potential of ComfyUI on AWS with unparalleled flexibility and control.You can enable following features with just few steps.

- [Configuration Method](docs/DEPLOY_OPTION.md#configuration-method)
    - [How to Change Values in cdk.json](docs/DEPLOY_OPTION.md#how-to-change-values-in-cdkjson)
- [Security Related Settings](docs/DEPLOY_OPTION.md#security-related-settings)
    - [Enable Self Sign-Up](docs/DEPLOY_OPTION.md#enable-self-sign-up)
    - [Enable MFA](docs/DEPLOY_OPTION.md#enable-mfa)
    - [Restrict the email address domains that can sign up](docs/DEPLOY_OPTION.md#restrict-the-email-address-domains-that-can-sign-up)
    - [Enable AWS WAF restrictions](docs/DEPLOY_OPTION.md#enable-aws-waf-restrictions)
        - [IP address restrictions](docs/DEPLOY_OPTION.md#ip-address-restrictions)
    - [SAML Authentication](docs/DEPLOY_OPTION.md#saml-authentication)
- [Cost-related Settings](docs/DEPLOY_OPTION.md#cost-related-settings)
    - [Spot Instance](docs/DEPLOY_OPTION.md#spot-instance)
    - [Scale Down automatically / on schedule](docs/DEPLOY_OPTION.md#scale-down-automatically--on-schedule)
    - [Use NAT Insatnce instead of NAT Gateway](docs/DEPLOY_OPTION.md#use-nat-insatnce-instead-of-nat-gateway)
- [Using a Custom Domain](docs/DEPLOY_OPTION.md#using-a-custom-domain)



### Delete deployments and cleanup resources

To remove the deployment and all associated resources:

**Delete the ComfyUI stack** (keeps CodeBuild for redeployment):
```bash
make destroy
```

**Delete everything** (ComfyUI + CodeBuild + S3):
```bash
make cleanup
```

Both options delete the CloudFormation stack. The following resources are **retained** and must be cleaned up manually:

1. **EBS Data Volume** — Created by the rexray Docker plugin at runtime (not managed by CloudFormation). Login to AWS Console → EC2 → Volumes → Select the ComfyUI data volume → Delete.
2. **S3 Bucket** (ComfyUI data) — Retained to prevent accidental data loss. Login to AWS Console → S3 → Empty and delete the `comfyuistack*-ecsconstructecsconstructcomf*` bucket.

> The ASG, ALB, Cognito User Pool, and other stack-managed resources are deleted automatically by CloudFormation.

## Notes and Additional Information

### Cost Estimation

This section provides cost estimations for running the application on AWS. Costs vary by instance type, region, Spot market conditions, and usage patterns. Use the [AWS Pricing Calculator](https://calculator.aws/) for precise estimates based on your configuration.

#### Flexible Workload (Default)

For non-critical workloads, use Spot Instances for significant savings. Spot Instances typically offer 60–90% savings compared to On-Demand pricing for GPU instances. Actual discounts vary by instance type, region, and availability — check the [AWS Spot Instance Advisor](https://aws.amazon.com/ec2/spot/instance-advisor/) for current data. A NAT Instance replaces the NAT Gateway to further reduce fixed costs.

The following assumptions are made for the cost estimation:

- No services from the AWS Free Tier are included.
- Instance Type: `g6e.2xlarge` with 8 vCPU, 64 GiB memory, and 1 NVIDIA L40S GPU (Spot Instance pricing — estimates assume ~70% savings; actual savings vary by region and time).
- 250 GB SSD storage.
- 1 Application Load Balancer.
- VPC with NAT Instance.
- Elastic Container Registry (ECR) with 10 GB of data stored per month.
- 5 GB of logging data per month.

| Service \ Runtime  | 2h/day Mon-Fri | 8h/day Mon-Fri | 12h/day Mon-Fri | 24/7          |
|--------------------|----------------|----------------|-----------------|---------------|
| Compute (Spot)     | ~$30           | ~$118          | ~$176           | ~$492         |
| Storage            | -              | -              | -               | $20           |
| ALB                | -              | -              | -               | $20           |
| Networking         | -              | -              | -               | $6            |
| Registry           | -              | -              | -               | $1            |
| Logging            | -              | -              | -               | $3            |
| Total Monthly Cost | ~$80           | ~$168          | ~$226           | ~$542         |

> These are rough estimates. Spot pricing is dynamic. Check the [Spot pricing history](https://aws.amazon.com/ec2/spot/pricing/) for your region.

#### Business-Critical Workload

For business-critical workloads, use On-Demand instances and a NAT Gateway for higher availability.

The following assumptions are made for the cost estimation:

- Instance Type: `g6e.2xlarge` On-Demand pricing (~$2.24/hr in us-west-2).
- VPC with 50 GB of data processed per NAT Gateway per month.
- Other assumptions are the same as the Flexible Workload scenario.

| Service \ Runtime  | 2h/day Mon-Fri | 8h/day Mon-Fri | 12h/day Mon-Fri | 24/7          |
|--------------------|----------------|----------------|-----------------|---------------|
| Compute (On-Demand)| ~$98           | ~$391          | ~$586           | ~$1,636       |
| Storage            | -              | -              | -               | $20           |
| ALB                | -              | -              | -               | $20           |
| Networking         | -              | -              | -               | $70           |
| Registry           | -              | -              | -               | $1            |
| Logging            | -              | -              | -               | $3            |
| Total Monthly Cost | ~$212          | ~$505          | ~$700           | ~$1,750       |

### Useful Commands

* `make setup`            one-time: create CodeBuild CI/CD pipeline
* `make`                  deploy via CodeBuild (runs in AWS)
* `make status`           check latest build status
* `make logs`             print last 40 lines of build logs
* `make destroy`          delete ComfyUI stack (keep CodeBuild)
* `make cleanup`          delete everything
* `make test`             run snapshot tests locally
* `npx cdk synth`         emit the synthesized CloudFormation template
* `npx cdk diff`          compare deployed stack with current state

### Auto-Scaling Behavior

This solution supports automatic scale-to-zero to eliminate compute costs during idle periods.

**Scale-down (enabled by default with `auto_scale_down=True`):**
- A CloudWatch alarm monitors the ASG's average CPU utilization every minute
- If CPU remains below 1% for 60 consecutive minutes (1 hour idle), the alarm triggers
- A Step Scaling action reduces the ASG desired capacity to 0, terminating the GPU instance
- The EBS data volume persists independently (managed by the rexray Docker volume plugin)

**Scale-up:**
- When a user visits the ALB endpoint while the instance is down, the admin Lambda is invoked
- The Lambda sets the ASG desired capacity back to 1
- A new GPU Spot Instance launches, registers with ECS, and starts the ComfyUI container
- Cold start takes approximately 5-8 minutes (instance launch + Docker image pull + ECS task start)

**Scheduled scaling (optional, `schedule_auto_scaling=True`):**
- Define cron schedules for scale-up and scale-down (e.g., work hours only)
- Default: scale up at 9:00 AM Mon-Fri, scale down at 6:00 PM daily (UTC)
- Configure timezone with the `timezone` parameter

### Known Limitations

> ⚠️ This is a sample deployment intended for personal or non-production use.

- **No EBS backup automation** — The persistent data volume (models, outputs, custom nodes) has no automatic snapshots. If the volume is deleted or corrupted, data is permanently lost. Consider implementing [EBS Snapshots](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-snapshots.html) for important data.
- **Single Availability Zone** — The EBS volume is AZ-bound. If the instance launches in a different AZ than the volume, the container will fail to mount it. The ASG is configured to use the same AZ as the volume.
- **No multi-instance scaling** — The ASG max capacity is 1. This solution does not support multiple concurrent users generating images simultaneously.
- **Spot Instance interruptions** — Spot Instances can be reclaimed by AWS with 2 minutes notice. In-progress image generations will be lost. The instance will be replaced automatically.
- **ALB idle timeout** — ComfyUI uses WebSockets for generation progress updates. The default ALB idle timeout is 60 seconds. For long-running workflows (SDXL, video generation), increase the timeout via the ALB settings in the AWS Console or by modifying `alb_construct.py` (target: 300+ seconds).

### Configuration Reference

All parameters are set in `app.py` when instantiating `ComfyUIStack`. See [Deployment Options](docs/DEPLOY_OPTION.md) for detailed examples.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `cheap_vpc` | `True` | Use NAT Instance instead of NAT Gateway (cheaper, lower throughput) |
| `use_spot` | `True` | Use Spot Instances for GPU compute |
| `spot_price` | `"0.752"` | Maximum Spot price (USD/hr). Instance only launches when Spot price is below this value |
| `comfyui_instance_type` | `"g6e.2xlarge"` | GPU instance type for ComfyUI |
| `enable_comfyui` | `True` | Enable ComfyUI ECS deployment |
| `auto_scale_down` | `True` | Scale to zero after 1 hour of idle (CPU < 1%) |

> **Note:** The defaults above are from `ComfyUIStack`. Your `app.py` may override them (e.g., `use_spot=False` for On-Demand instances during development).
| `schedule_auto_scaling` | `False` | Enable cron-based scheduled scaling |
| `timezone` | `"UTC"` | Timezone for scheduled scaling |
| `schedule_scale_up` | `"0 9 * * 1-5"` | Cron for scale-up (default: 9 AM Mon-Fri) |
| `schedule_scale_down` | `"0 18 * * *"` | Cron for scale-down (default: 6 PM daily) |
| `self_sign_up_enabled` | `False` | Allow users to self-register via Cognito |
| `allowed_sign_up_email_domains` | `None` | Restrict sign-up to specific email domains |
| `mfa_required` | `False` | Require MFA for Cognito users |
| `saml_auth_enabled` | `False` | Enable SAML SSO (disables Cognito user pool login) |
| `allowed_ip_v4_address_ranges` | `None` | IPv4 CIDR allowlist for WAF |
| `allowed_ip_v6_address_ranges` | `None` | IPv6 CIDR allowlist for WAF |
| `waf_rate_limit_enabled` | `False` | Enable WAF rate limiting on `/api/prompt` |
| `waf_rate_limit_requests` | `300` | Max requests per interval before blocking |
| `waf_rate_limit_interval` | `300` | Rate limit evaluation window (seconds) |
| `host_name` | `None` | Custom domain hostname (requires Route 53 hosted zone) |
| `domain_name` | `None` | Custom domain name |
| `hosted_zone_id` | `None` | Route 53 hosted zone ID |

### Well-Architected Considerations

This sample deployment prioritizes cost and simplicity. The following trade-offs are made against AWS Well-Architected pillars:

**Operational Excellence**
- CI/CD via CodeBuild (`make deploy`). No local Docker required. No automated rollback — failed deploys require manual intervention or redeployment.
- Monitoring relies on CloudWatch Container Insights (enabled by default).

**Security**
- Authentication via Amazon Cognito (user pool or SAML). Optional WAF with IP allowlisting and rate limiting.
- IAM roles use broad managed policies (see [IAM Roles](#iam-roles-and-permissions)). Not suitable for production without scoping down.
- EBS root volume is encrypted. The rexray-managed data volume uses gp3 but does not explicitly specify encryption — verify your account-level EBS encryption default.
- No VPC Flow Logs or ALB access logs are enabled (to reduce cost). Enable for auditing in regulated environments.
- cdk-nag (AwsSolutions pack) is run during synth to surface security findings.

**Reliability**
- Single-AZ deployment. The EBS data volume is AZ-bound; if the AZ has an outage, the service is down until it recovers.
- No automated EBS snapshots. Data loss is permanent if the volume is deleted.
- Spot Instance interruptions cause in-progress work to be lost. The ASG replaces the instance automatically.
- ASG max capacity is 1. No redundancy or failover.

**Performance Efficiency**
- GPU instance type is configurable (`comfyui_instance_type`). Default `g6e.2xlarge` provides 48GB VRAM suitable for SDXL and video workflows.
- Container Insights provides CPU/memory/GPU utilization metrics.
- ALB idle timeout defaults to 60 seconds. Increase for long-running generation workflows.

**Cost Optimization**
- Spot Instances (60-90% savings over On-Demand) enabled by default.
- Auto scale-to-zero after 1 hour idle eliminates compute costs when not in use.
- NAT Instance instead of NAT Gateway reduces fixed monthly costs.
- Actual costs depend on usage patterns, Spot market, and region. Use the [AWS Pricing Calculator](https://calculator.aws/) for estimates.

**Sustainability**
- Scale-to-zero reduces energy consumption when idle.
- No further sustainability optimizations are implemented. Consider ARM-based instances (g5g) when model compatibility allows.

### IAM Roles and Permissions

This solution creates the following IAM roles. These use broad managed policies suitable for a sample deployment. For production use, scope them down to least privilege.

| Role | Service | Policies | Purpose |
|------|---------|----------|---------|
| EC2 Instance Role | `ec2.amazonaws.com` | `AmazonEC2FullAccess`, `AmazonSSMManagedInstanceCore` | ASG instances: EBS volume management (rexray plugin), SSM Session Manager access |
| ECS Task Execution Role | `ecs-tasks.amazonaws.com` | `AmazonECSTaskExecutionRolePolicy` | Pull container images from ECR, write logs to CloudWatch |
| Admin Lambda Role | `lambda.amazonaws.com` | `AWSLambdaBasicExecutionRole`, `AutoScalingFullAccess` | Scale-up/shutdown/restart operations via ALB admin panel |
| Cert Lambda Role | `lambda.amazonaws.com` | `AWSLambdaBasicExecutionRole` + inline `acm:ImportCertificate`, `acm:AddTagsToCertificate` | Register self-signed TLS certificate with ACM |

> ⚠️ **Security note:** `AmazonEC2FullAccess` and `AutoScalingFullAccess` are overly broad for production. For a hardened deployment, replace these with custom policies scoped to the specific resources (ASG ARN, EBS volumes in the stack's VPC, specific ECS cluster).

## Q&A

#### Does the Dockerfile already pre-install models?

Dockerfile includes only ComfyUI and ComfyUI-Manager. To install models either go over ComfyUI-Manager after deployment or over the section [Upload Models](README.md#uploading-models).

#### Can I contribute to this project?

Yes, feel free to follow the [contribution](CONTRIBUTING.md#security-issue-notifications) guide.

#### Can this be consiered for production deployments?

Consider this setup as an sample deployment for personal or non-production use.

## Contributors

[![contributors](https://contrib.rocks/image?repo=aws-samples/cost-effective-aws-deployment-of-comfyui&max=1500)](https://github.com/aws-samples/cost-effective-aws-deployment-of-comfyui/graphs/contributors)
 
## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

- [License](LICENSE) of the project.
- [Code of Conduct](CONTRIBUTING.md#code-of-conduct) of the project.
- [THIRD-PARTY](THIRD-PARTY) for more information about third party usage
