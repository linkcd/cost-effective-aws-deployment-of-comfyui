#!/usr/bin/env bash
set -euo pipefail

COMFYUI_ROOT="/home/user/opt/ComfyUI"

mkdir -p \
    "${COMFYUI_ROOT}/models/diffusion_models" \
    "${COMFYUI_ROOT}/models/unet_gguf" \
    "${COMFYUI_ROOT}/models/model_gguf"

exec python "${COMFYUI_ROOT}/main.py" \
    --listen 0.0.0.0 \
    --port 8181 \
    --output-directory "${COMFYUI_ROOT}/output/" \
    "$@"
