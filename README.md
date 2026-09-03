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

> Docker is NOT required for the default (CodeBuild) deployment. If you prefer to deploy locally, Docker or Finch is required.

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

#### Option B: Local deployment (requires Docker or Finch)

If you prefer deploying directly from your machine:

```bash
export AWS_DEFAULT_REGION=us-west-2
make local-bootstrap   # first time only
make local-deploy
```

| Command | What it does |
|---------|-------------|
| `make local-bootstrap` | One-time: bootstrap CDK in your account |
| `make local-deploy` | Deploy directly via `cdk deploy` (requires Docker) |
| `make local-synth` | Synthesize the CloudFormation template locally |

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

### MiniMax H3 Video Generation: AWS Instance Guidance

Last verified: September 1, 2026.

The official [MiniMax H3 repository](https://github.com/MiniMax-AI/MiniMax-H3), [ComfyUI H3 workflow guide](https://docs.comfy.org/tutorials/video/minimax/minimax-h3), and [ComfyUI launch notes](https://blog.comfy.org/p/minimax-h3-day-0-support-in-comfyui) show that H3 is a large video model. ComfyUI's launch notes report approximately 123.6 GB for the full-precision model set and 42.5 GB for the smallest optimized set. Dynamic VRAM offloading can make the optimized workflow run on smaller GPUs, but it shifts pressure to system RAM and is much slower. The official SGLang serving example uses four GPUs.

This stack's ECS task reserves exactly one GPU, so selecting an eight-GPU EC2 instance does not automatically make ComfyUI use all eight GPUs. Multi-GPU serving requires a different task/runtime configuration.

| EC2 instance | GPU | System RAM | Guidance for this stack |
|--------------|-----|------------|-------------------------|
| `g6e.2xlarge` | 1 NVIDIA L40S, 48 GB VRAM | 64 GiB | Minimum cost-oriented experiment. Use optimized/quantized H3 Turbo workflows and monitor both host RAM and VRAM. It was not reliable for the investigated H3 workload. |
| `g6e.4xlarge` | 1 NVIDIA L40S, 48 GB VRAM | 128 GiB | Recommended cost-conscious default. GPU capacity is the same as `g6e.2xlarge`, but the extra host RAM gives model offloading and custom nodes substantially more headroom. |
| `p5.4xlarge` | 1 NVIDIA H100, 80 GB VRAM | 256 GiB | Recommended single-GPU performance option when quota, availability, and cost allow it. It provides more VRAM, memory bandwidth, and host RAM. |
| `p5.48xlarge` / `p5en.48xlarge` | 8 H100 / H200 GPUs | Large multi-GPU host | Consider only for a deliberately configured multi-GPU H3 server such as the official SGLang setup. The current ECS task will use only one GPU. |

Instance availability and service quotas vary by Region and Availability Zone. See the official [Amazon EC2 G6e](https://aws.amazon.com/ec2/instance-types/g6e/) and [Amazon EC2 P5](https://aws.amazon.com/ec2/instance-types/p5/) specifications before deployment.

#### Observed `g6e.2xlarge` out-of-memory failure

During the Tokyo deployment investigation, the old ECS task stopped with exit code `137` and:

```text
OutOfMemoryError: Container killed due to memory usage
```

This was a host/system-memory OOM, not a confirmed GPU-VRAM OOM:

- The `g6e.2xlarge` host had approximately 63,430 MiB of RAM.
- The container's `memory_reservation_mib=15000` is a soft scheduling reservation, not a 15 GiB hard limit.
- Immediately before the failure, logs showed H3 model-resolution/download requests for the H3 VAE, Qwen3-VL text encoder, Turbo LoRA, and diffusion model.
- The timing does not prove that generation itself caused the OOM, but it confirms that 64 GiB of host RAM did not provide enough headroom for that model-loading path.

For this deployment, start with `g6e.4xlarge` for a cost-conscious H3 setup. Use `p5.4xlarge` when faster generation and greater VRAM/RAM headroom justify the price. Keep `g6e.2xlarge` for controlled tests using the smallest optimized model set, and avoid loading unnecessary models at the same time.

### ComfyUI Model Resolver: `diffusion_models` Issue and Workaround

Last verified: September 1, 2026.

In the investigated deployment, ComfyUI Model Resolver reported:

```text
Could not find directory for category: diffusion_models
```

The directory `/home/user/opt/ComfyUI/models/diffusion_models` did exist and contained models such as Wan2.2. Downloads to `loras` and `sams` also worked. The problem was therefore not EBS write permissions or a generally missing models directory.

The installed Model Resolver version was `v1.1.0`. Its diffusion-model category checks these aliases:

```text
diffusion_models, unet, unet_gguf, model_gguf
```

The downloader wrapped the complete alias lookup in one error handler. If an optional alias such as `unet_gguf` or `model_gguf` was not registered by ComfyUI, that lookup failed and discarded the valid `diffusion_models` path found earlier. Categories such as `loras` and `sams` did not hit the same missing-alias path, which explains why their downloads succeeded.

#### Workaround applied to the deployment and source

The following directories were created on the persistent ComfyUI EBS volume:

```bash
mkdir -p /home/user/opt/ComfyUI/models/unet_gguf
mkdir -p /home/user/opt/ComfyUI/models/model_gguf
```

These mappings were added under the existing ComfyUI base-path entry in `/home/user/opt/ComfyUI/extra_model_paths.yaml`:

```yaml
    diffusion_models: models/diffusion_models/
    unet_gguf: models/unet_gguf/
    model_gguf: models/model_gguf/
```

The same mappings are declared in `comfyui_aws_stack/docker/comfyui_config/extra_model_paths.yaml`, and the container startup script creates the corresponding directories. Future image builds therefore retain the workaround when provisioning a new volume.

After restarting the ECS task, all three categories resolved successfully. A backup was saved as:

```text
/home/user/opt/ComfyUI/extra_model_paths.yaml.bak-before-model-resolver-alias-workaround
```

The whole `/home/user/opt/ComfyUI` path is EBS-backed, so the live workaround and installed custom nodes survive normal container/task replacement while the same volume is reused.

#### Upstream fix status

The upstream fix is commit [`026ba97c5b1528a79686e77832877bfc7caff0fc`](https://github.com/Azornes/Comfyui-Model-Resolver/commit/026ba97c5b1528a79686e77832877bfc7caff0fc), “Fix model download directory alias resolution.” It was committed immediately after the [`v1.2.0` release tag](https://github.com/Azornes/Comfyui-Model-Resolver/releases/tag/v1.2.0), so installing the official `v1.2.0` tag alone does **not** include the fix. The long-term solution is to install that commit or a later release that contains it; the alias mappings above are the current workaround.

### Installing Custom Nodes and Python Packages from the UI

The container enables ComfyUI-Manager's `allow_git_url_install` and `allow_pip_install` settings at startup. ComfyUI listens on `127.0.0.1:8182`, as required by Manager, while `socat` exposes port `8181` to the authenticated ALB and ECS health checks.

The image also pre-installs the current official ComfyUI-ReActor Python requirements, GPU-enabled ONNX Runtime, and `importlib-metadata`. ReActor 0.7.0-a2 needs the latter as an installer fallback because current Setuptools releases no longer provide the legacy `pkg_resources` module. ReActor itself remains installable and updatable through ComfyUI-Manager.

> [!WARNING]
> These Manager features allow authenticated users to install and execute arbitrary code inside the ComfyUI task. Installed code can access the persistent EBS volume and the ECS task role's AWS permissions. Restrict Cognito access to trusted administrators; this configuration is not appropriate for public or untrusted self-sign-up.

### Provisioned AWS Resources and Their Roles

The EC2 instance types have different jobs:

- The small `t4g.nano` instances are NAT instances when `cheap_vpc=True`. They only give resources in private subnets outbound internet access, for example to download models or contact ECR, Hugging Face, and package repositories. They do **not** run ComfyUI.
- The GPU instance, `g6e.2xlarge` by default, joins the ECS cluster and runs the ComfyUI Docker container. It can scale to zero when idle.
- Set `cheap_vpc=False` to use AWS-managed NAT Gateways instead of the `t4g.nano` instances. A NAT Gateway has higher availability and throughput and requires less instance management, but has a higher fixed and data-processing cost.

The VPC does not explicitly cap the NAT count. By CDK default, it can create one NAT instance or NAT Gateway per selected Availability Zone. The exact count therefore depends on the synthesized/deployed AZ context and should be included in the cost estimate.

| Resource | Role |
|----------|------|
| VPC and subnets | Creates public and private-with-egress subnets across up to three Availability Zones. The ALB and NAT are public; the GPU/ECS host remains private. |
| `t4g.nano` NAT instance(s) | Low-cost outbound internet path for private subnets when `cheap_vpc=True`. CDK can create one per selected AZ, and they normally remain running even when GPU compute scales to zero. |
| S3 gateway VPC endpoint | Keeps supported S3 traffic, including ECR image-layer downloads, off the NAT path. |
| GPU Auto Scaling Group | Launches the ECS-optimized GPU EC2 host. Defaults to one Spot `g6e.2xlarge`, with minimum 0, desired 1, maximum 1, and an encrypted 200 GiB root volume. It can choose any configured private AZ with capacity. |
| ECS cluster and capacity provider | Registers the GPU host and schedules the EC2-backed ComfyUI task onto it. |
| ECS task and service | Runs the ComfyUI Docker image, reserves one GPU, exposes port `8181` plus worker ports `8189`–`8191`, reports health, and replaces failed/stopped tasks. |
| REX-Ray EBS data volume | Creates a 5,000 GiB gp3 Docker volume mounted at `/home/user/opt/ComfyUI`. Models, custom nodes/plugins, workflows, outputs, and settings persist independently of a container restart. It is created at runtime and requires manual cleanup. |
| ECR/CDK Docker image asset | Stores the built ComfyUI container image that ECS pulls when starting a task. Files installed only into a container layer are lost on replacement unless added to the image or stored on the mounted EBS path. |
| S3 data bucket | Retained, encrypted object storage exposed to the task through `COMFYUI_S3_BUCKET`. It is separate from the locally mounted ComfyUI models directory. |
| Application Load Balancer | Public HTTPS entry point. Redirects HTTP to HTTPS, performs Cognito authentication, forwards ComfyUI traffic to port `8181`, and checks `/system_stats`. |
| Cognito | Provides the user pool, application client, and hosted authentication domain; optional SAML, MFA, self-sign-up, and email-domain restrictions are supported. |
| Lambda and EventBridge | Implement admin actions such as scale-up, shutdown, restart, sign-out, and lifecycle handling around ECS/EC2 state changes. |
| CloudWatch | Stores ECS and VPC Flow Logs, enables Container Insights, and supplies alarms used for idle scale-to-zero and optional notifications. |
| Optional WAF | Adds IP allowlisting and request-rate limiting in front of the ALB. |
| ACM and Route 53 | Provide TLS and DNS for a supplied custom domain. Without one, the stack creates and imports a self-signed certificate. |
| IAM roles and security groups | Allow ECS registration, image pulls, logging, EBS plugin operations, S3 access, SSM access, and tightly scoped network paths between the public ALB and private task. |

The persistent EBS volume remains tied to one Availability Zone even though the GPU Auto Scaling Group can now search multiple AZs for capacity. An existing EBS volume cannot attach to an instance launched in another AZ, so this improves initial capacity selection but does not provide multi-AZ storage or failover.

### Cost Estimation

This section provides cost estimations for running the application on AWS. Costs vary by instance type, region, Spot market conditions, and usage patterns. Use the [AWS Pricing Calculator](https://calculator.aws/) for precise estimates based on your configuration.

> [!WARNING]
> The legacy tables below assume 250 GB of SSD storage and one NAT instance. The current CDK requests a 5,000 GiB gp3 data volume plus a 200 GiB GPU-host root volume, and it can create one NAT instance per selected AZ. Recalculate storage and networking costs for the synthesized stack before deployment.

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

### Scalability and Cost-Saving Behavior

This deployment implements **scale-to-zero**, not horizontal workload scaling. The GPU Auto Scaling Group has minimum capacity `0`, desired capacity `1`, and maximum capacity `1`. The ECS service also runs one task that reserves one GPU. The system can therefore switch between zero and one GPU host, but it cannot add more instances for concurrent users or a larger queue. There is no request-count, queue-depth, or GPU-utilization scale-up policy.

> [!IMPORTANT]
> The current `app.py` overrides the stack defaults with `auto_scale_down=False` and `use_spot=False`. Therefore, a deployment made from the current file uses an On-Demand GPU instance and does not automatically shut it down after one idle hour. Scheduled scaling is also disabled by default. Manual **Shutdown Services** and **Scale Up** actions remain available.

#### Trigger and Lambda summary

| Trigger or event | Component invoked | Result |
|------------------|-------------------|--------|
| Initial stack deployment | Auto Scaling Group; no Lambda | Starts with desired capacity `1`, so a GPU instance is launched. |
| Open `/` or `/admin` while scaled down | ALB → Cognito → `AdminFunction` Lambda | Displays current ASG/ECS status and a **Scale Up** button. Merely opening or refreshing the page does **not** start the GPU. |
| Click **Scale Up** (`/admin/scaleup`) | `ScaleUpTriggerFunction` Lambda | Sets ASG desired capacity to `1` if necessary and ensures ECS service desired count is `1`. |
| ECS task changes to `RUNNING` | EventBridge → `ScaleupListenerFunction` Lambda | If the ASG is at `1` and the ECS service has a running task, changes the ALB admin rule so `/` routes to ComfyUI while `/admin` continues to route to the admin page. |
| Click **Shutdown Services** (`/admin/shutdown`) | `ShutdownFunction` Lambda | Sets ASG desired capacity to `0` with no cooldown, provided the ASG minimum size is `0`. |
| Host CPU remains below the idle threshold | CloudWatch alarm → ASG Step Scaling; no Lambda initiates it | When enabled, reduces ASG desired capacity by one, from `1` to `0`. |
| Scheduled start or stop time | ASG scheduled action; no Lambda | Directly sets desired capacity to `1` or `0`. |
| ASG instance-termination lifecycle action | EventBridge → `ScaleinListenerFunction` Lambda | After confirming desired capacity is `0` and all ECS services are down, changes the ALB admin rule so both `/` and `/admin` reach the admin page. This Lambda updates routing; it does not initiate shutdown. |
| Click **Restart Docker** (`/admin/restart`) | `RestartDockerFunction` Lambda → Systems Manager | Restarts Docker on the existing GPU instance. This is a restart operation, not a scale-up or scale-down action. |
| ASG launch/termination error, when Slack notifications are configured | EventBridge → ASG monitor Lambda → SNS/AWS Chatbot | Sends an error notification. It observes failures but does not change desired capacity. |

All browser-facing admin routes are protected by the configured Cognito authentication.

#### Scale-up sequence

1. While the ASG is at zero, `/admin` reaches the admin Lambda. After a completed scale-in routing update, `/` reaches it as well.
2. `AdminFunction` reads the ASG desired capacity and ECS desired/running task counts. If everything is down, it displays the **Scale Up** button.
3. Clicking the button invokes `ScaleUpTriggerFunction`, which sets the ASG desired capacity to `1` and restores the ECS service desired count to `1` if needed. The Lambda then redirects the browser to `/`.
4. The ASG launches the configured GPU instance, using Spot or On-Demand capacity according to `use_spot`. The instance boots, joins the ECS cluster, pulls the image, mounts the persistent EBS volume, and starts the ComfyUI task.
5. An ECS `RUNNING` task event invokes `ScaleupListenerFunction`. It changes the ALB rule so `/` can reach the ECS target group. The ALB still uses `/system_stats` health checks to decide whether the target is ready to receive traffic.

The admin page reports that scale-up can take approximately 5–10 minutes and reloads every 30 seconds while it detects a service starting. Actual time depends on EC2 capacity, Spot availability, instance boot, image pull, EBS attachment, plugin startup, and model/custom-node initialization.

#### Scale-down paths

There are three independent ways to request scale-down:

1. **Manual shutdown:** An authenticated user clicks **Shutdown Services**. `ShutdownFunction` immediately requests ASG desired capacity `0`.
2. **Idle CPU alarm:** When `auto_scale_down=True`, CloudWatch evaluates the GPU host's average EC2 `CPUUtilization` every minute. All 60 of the last 60 datapoints must be below `1%`; the alarm then invokes an ASG Step Scaling policy that subtracts one instance.
3. **Schedule:** When `schedule_auto_scaling=True`, ASG scheduled actions set desired capacity directly. The defaults are scale-up at 09:00 Monday–Friday and scale-down at 18:00 every day in the configured `timezone`.

The idle detector watches **host CPU**, not GPU utilization, ComfyUI queue state, browser sessions, or active WebSockets. A GPU-heavy workflow with very low CPU use could therefore be considered idle. Scheduled or manual shutdown can also interrupt an active generation. Adjust or disable these mechanisms for unattended long-running video workflows.

When the GPU instance terminates, its ECS task stops and in-progress work is lost. The REX-Ray EBS data volume remains, so models, custom nodes, settings, workflows, and saved outputs survive the next scale-up.

#### Restart and failure recovery

- **Restart Docker** is allowed only when the ASG has exactly one `InService` instance and all ECS services are running. The Lambda sends `sudo systemctl restart docker` through Systems Manager and temporarily restores `/` to the admin route. The ECS service starts the task again, and the `RUNNING` event restores normal root routing.
- If only the ComfyUI task fails or becomes unhealthy, the ECS service attempts to replace it on the existing GPU host. This does not intentionally change ASG desired capacity.
- If the EC2 instance fails or a Spot instance is interrupted while desired capacity remains `1`, the ASG attempts to launch a replacement and ECS schedules the task again. This is replacement, not scale-to-zero, and the interrupted generation is not resumed.
- The shortened container stop timeout, target-group drain delay, and ALB health-check interval reduce task-restart delay. They do not reduce EC2 launch, image-pull, EBS-mount, or ComfyUI initialization time.

#### What scale-to-zero saves

Scaling to zero stops the expensive GPU EC2 instance charge. It does **not** remove the rest of the stack. Charges can continue for the persistent 5,000 GiB gp3 EBS volume, ALB, NAT instance(s) or NAT Gateway(s), S3, CloudWatch, data transfer, and other retained or always-on resources.

Manual and scheduled actions can override each other over time: for example, a manual shutdown remains at zero only until a later scheduled scale-up action sets the ASG back to one.

### Known Limitations

> ⚠️ This is a sample deployment intended for personal or non-production use.

- **No EBS backup automation** — The persistent data volume (models, outputs, custom nodes) has no automatic snapshots. If the volume is deleted or corrupted, data is permanently lost. Consider implementing [EBS Snapshots](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-snapshots.html) for important data.
- **EBS volume is Availability Zone-bound** — The GPU ASG can try private subnets across up to three AZs, but an existing REX-Ray EBS volume can attach only in its own AZ. A replacement launched in another AZ may fail to mount it. This is not multi-AZ storage.
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
| `slack_workspace_id` | `None` | Slack workspace ID for notifications (enables ASG/ECS alerts) |
| `slack_channel_id` | `None` | Slack channel ID for notifications |

> **Note:** The defaults above are from `ComfyUIStack`. Your `app.py` may override them. The current `app.py` sets `use_spot=False`, `auto_scale_down=False`, and `self_sign_up_enabled=True`.

### Well-Architected Considerations

This sample deployment prioritizes cost and simplicity. The following trade-offs are made against AWS Well-Architected pillars:

**Operational Excellence**
- CI/CD via CodeBuild (`make deploy`). No local Docker required. No automated rollback — failed deploys require manual intervention or redeployment.
- Monitoring relies on CloudWatch Container Insights (enabled by default). Optional Slack notifications for ASG and ECS health events.

**Security**
- Authentication via Amazon Cognito (user pool or SAML). Optional WAF with IP allowlisting and rate limiting.
- IAM roles use broad managed policies (see [IAM Roles](#iam-roles-and-permissions)). Not suitable for production without scoping down.
- EBS root volume is encrypted. The rexray-managed data volume uses gp3 but does not explicitly specify encryption — verify your account-level EBS encryption default.
- VPC Flow Logs are enabled. ALB access logs are not enabled; consider enabling them for auditing in regulated environments.
- cdk-nag (AwsSolutions pack) is run during synth to surface security findings.

**Reliability**
- GPU capacity can be selected from private subnets across up to three AZs, but the EBS data volume is AZ-bound. This is not true multi-AZ failover, and an instance in another AZ cannot mount the existing volume.
- No automated EBS snapshots. Data loss is permanent if the volume is deleted.
- Spot Instance interruptions cause in-progress work to be lost. The ASG replaces the instance automatically.
- ASG max capacity is 1. No redundancy or failover.

**Performance Efficiency**
- GPU instance type is configurable (`comfyui_instance_type`). Default `g6e.2xlarge` provides 48GB VRAM suitable for SDXL and video workflows.
- Container Insights provides CPU/memory/GPU utilization metrics.
- ALB idle timeout defaults to 60 seconds. Increase for long-running generation workflows.

**Cost Optimization**
- The stack supports Spot Instances, but the current `app.py` sets `use_spot=False` and therefore launches On-Demand GPU capacity.
- Idle scale-to-zero is available with `auto_scale_down=True`, but the current `app.py` disables it. Manual shutdown remains available.
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
