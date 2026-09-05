#!/bin/bash
# CI/CD pipeline for ComfyUI CDK stack.
# CodeBuild is a separate lightweight CloudFormation stack (no Docker needed to deploy).
#
# First-time setup:
#   ./scripts/run_codebuild.sh setup
#
# Workflow:
#   1. Make changes locally
#   2. Run: ./scripts/run_codebuild.sh deploy
#      → Zips source, uploads to S3, kicks off CodeBuild
#      → CodeBuild does: synth → verify → deploy
#   3. Watch in console or: ./scripts/run_codebuild.sh status
#   4. When done testing: ./scripts/run_codebuild.sh destroy
#
# Commands:
#   setup    - One-time: bootstrap CDK and create CodeBuild infrastructure
#   deploy   - Zip, upload, and start a full deploy build
#   synth    - Zip, upload, and start a synth-only build (no deploy)
#   status   - Check latest build status
#   logs     - Print recent build logs
#   destroy  - Tear down the ComfyUI application stack
#   cleanup  - Tear down everything (ComfyUI + CodeBuild + S3)

set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-${AWS_REGION:-}}"
if [ -z "$REGION" ]; then
  echo "Error: No AWS region configured. Set AWS_DEFAULT_REGION or AWS_REGION."
  echo "Example: AWS_DEFAULT_REGION=us-west-2 make deploy"
  exit 1
fi
CODEBUILD_STACK_NAME="ComfyUI-CodeBuild"
APP_STACK_NAME="ComfyUIStack"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Get CodeBuild stack outputs
get_output() {
  aws cloudformation describe-stacks \
    --stack-name "$CODEBUILD_STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
    --output text 2>/dev/null
}

PROJECT_NAME=$(get_output CodeBuildProjectName 2>/dev/null || echo "")
BUCKET_NAME=$(get_output SourceBucketName 2>/dev/null || echo "")

upload_source() {
  echo "Packaging source..."
  cd "$PROJECT_DIR"
  zip -r /tmp/comfyui-source.zip . \
    -x '.git/*' '.venv/*' 'venv/*' 'node_modules/*' 'cdk.out/*' '*/__pycache__/*' '.kiro/*' '*.pyc' 'temp/*' >/dev/null
  echo "Uploading to s3://${BUCKET_NAME}/comfyui-source.zip..."
  aws s3 cp /tmp/comfyui-source.zip "s3://${BUCKET_NAME}/comfyui-source.zip" --region "$REGION" >/dev/null
  rm -f /tmp/comfyui-source.zip
  echo "Done."
}

case "${1:-deploy}" in
  setup)
    CDK_CLI="$PROJECT_DIR/node_modules/.bin/cdk"
    if [ ! -x "$CDK_CLI" ]; then
      echo "Error: AWS CDK CLI is not installed."
      echo "Run 'npm install' or use 'make setup' first."
      exit 1
    fi
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    BOOTSTRAP_WORK_DIR=$(mktemp -d)
    trap 'rm -rf -- "$BOOTSTRAP_WORK_DIR"' EXIT
    echo "Bootstrapping CDK deployment roles..."
    (
      # Run outside the project so bootstrap does not load cdk.json, synthesize
      # the application, or require local Python and Docker dependencies.
      cd "$BOOTSTRAP_WORK_DIR"
      CDK_DEFAULT_ACCOUNT="$ACCOUNT_ID" \
        CDK_DEFAULT_REGION="$REGION" \
        "$CDK_CLI" bootstrap "aws://${ACCOUNT_ID}/${REGION}"
    )
    echo "Creating CodeBuild infrastructure..."
    aws cloudformation deploy \
      --stack-name "$CODEBUILD_STACK_NAME" \
      --template-file "$PROJECT_DIR/codebuild-pipeline.yaml" \
      --capabilities CAPABILITY_NAMED_IAM \
      --region "$REGION"
    echo ""
    echo "Setup complete. Outputs:"
    aws cloudformation describe-stacks --stack-name "$CODEBUILD_STACK_NAME" --region "$REGION" --query 'Stacks[0].Outputs' --output table
    ;;

  deploy)
    if [ -z "$PROJECT_NAME" ]; then
      echo "Error: CodeBuild stack not found. Run './scripts/run_codebuild.sh setup' first."
      exit 1
    fi
    upload_source
    echo "Starting full deploy build..."
    BUILD_ID=$(aws codebuild start-build \
      --project-name "$PROJECT_NAME" \
      --region "$REGION" \
      --query 'build.id' --output text)
    echo ""
    echo "Build: $BUILD_ID"
    echo "Console: https://${REGION}.console.aws.amazon.com/codesuite/codebuild/projects/${PROJECT_NAME}/build/${BUILD_ID}/log?region=${REGION}"
    echo ""
    echo "Check status: ./scripts/run_codebuild.sh status"
    ;;

  synth)
    if [ -z "$PROJECT_NAME" ]; then
      echo "Error: CodeBuild stack not found. Run './scripts/run_codebuild.sh setup' first."
      exit 1
    fi
    upload_source
    echo "Starting synth-only build..."
    BUILD_ID=$(aws codebuild start-build \
      --project-name "$PROJECT_NAME" \
      --region "$REGION" \
      --buildspec-override '{"version":"0.2","phases":{"install":{"runtime-versions":{"python":"3.12","nodejs":"20"},"commands":["python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt","npm install"]},"build":{"commands":["source .venv/bin/activate && npx cdk synth --quiet","echo \"PASS - Synth completed successfully\""]}}}'  \
      --query 'build.id' --output text)
    echo ""
    echo "Build: $BUILD_ID"
    echo "Console: https://${REGION}.console.aws.amazon.com/codesuite/codebuild/projects/${PROJECT_NAME}/build/${BUILD_ID}/log?region=${REGION}"
    ;;

  status)
    if [ -z "$PROJECT_NAME" ]; then
      echo "Error: CodeBuild stack not found."
      exit 1
    fi
    BUILD_ID=$(aws codebuild list-builds-for-project \
      --project-name "$PROJECT_NAME" \
      --region "$REGION" \
      --query 'ids[0]' --output text)
    echo "Latest build: $BUILD_ID"
    aws codebuild batch-get-builds \
      --ids "$BUILD_ID" \
      --region "$REGION" \
      --query 'builds[0].{Status:buildStatus,Phase:currentPhase,Duration:phases[-1].durationInSeconds}' \
      --output table
    ;;

  logs)
    if [ -z "$PROJECT_NAME" ]; then
      echo "Error: CodeBuild stack not found."
      exit 1
    fi
    BUILD_ID=$(aws codebuild list-builds-for-project \
      --project-name "$PROJECT_NAME" \
      --region "$REGION" \
      --query 'ids[0]' --output text)
    STREAM=$(echo "$BUILD_ID" | cut -d: -f2)
    aws logs get-log-events \
      --log-group-name "/aws/codebuild/$PROJECT_NAME" \
      --log-stream-name "$STREAM" \
      --region "$REGION" \
      --query 'events[].message' --output text | tail -40
    ;;

  destroy)
    echo "Destroying ComfyUI application stack..."
    CLUSTER_ARN=$(aws ecs list-clusters --region "$REGION" --query 'clusterArns[?contains(@, `ComfyUI`)] | [0]' --output text 2>/dev/null || echo "None")
    if [ "$CLUSTER_ARN" != "None" ] && [ -n "$CLUSTER_ARN" ]; then
      echo "Detaching ECS capacity providers..."
      aws ecs put-cluster-capacity-providers --cluster "$CLUSTER_ARN" --capacity-providers '[]' --default-capacity-provider-strategy '[]' --region "$REGION" 2>/dev/null || true
      sleep 5
    fi
    aws cloudformation delete-stack --stack-name "$APP_STACK_NAME" --region "$REGION"
    echo "Stack deletion initiated. CodeBuild infrastructure preserved."
    echo "Run './scripts/run_codebuild.sh cleanup' to remove everything."
    ;;

  cleanup)
    echo "Destroying ComfyUI application stack..."
    aws cloudformation delete-stack --stack-name "$APP_STACK_NAME" --region "$REGION" 2>/dev/null || true
    echo "Emptying S3 bucket..."
    aws s3 rm "s3://${BUCKET_NAME}" --recursive --region "$REGION" 2>/dev/null || true
    echo "Destroying CodeBuild stack..."
    aws cloudformation delete-stack --stack-name "$CODEBUILD_STACK_NAME" --region "$REGION"
    echo "Cleanup initiated. All stacks will be deleted."
    ;;

  *)
    echo "Usage: $0 [setup|deploy|synth|status|logs|destroy|cleanup]"
    echo ""
    echo "  setup    - One-time: bootstrap CDK + create CodeBuild infrastructure"
    echo "  deploy   - Zip source + start full deploy (synth → deploy)"
    echo "  synth    - Zip source + synth-only verification"
    echo "  status   - Check latest build"
    echo "  logs     - Print last 40 lines of build logs"
    echo "  destroy  - Delete ComfyUI app stack (keep CodeBuild)"
    echo "  cleanup  - Delete everything (app + CodeBuild + S3)"
    exit 1
    ;;
esac
