#!/usr/bin/env bash
set -euo pipefail

COMFYUI_ROOT="/home/user/opt/ComfyUI"
MANAGER_CONFIG="${COMFYUI_ROOT}/user/__manager/config.ini"
PUBLIC_PORT="8181"
LOOPBACK_PORT="8182"

mkdir -p \
    "${COMFYUI_ROOT}/models/diffusion_models" \
    "${COMFYUI_ROOT}/models/unet_gguf" \
    "${COMFYUI_ROOT}/models/model_gguf" \
    "${COMFYUI_ROOT}/models/ultralytics/bbox" \
    "${COMFYUI_ROOT}/models/ultralytics/segm"

python /home/user/bin/configure_comfyui_manager.py "${MANAGER_CONFIG}"

socat \
    "TCP-LISTEN:${PUBLIC_PORT},bind=0.0.0.0,reuseaddr,fork" \
    "TCP:127.0.0.1:${LOOPBACK_PORT}" &
proxy_pid=$!

python "${COMFYUI_ROOT}/main.py" \
    --listen 127.0.0.1 \
    --port "${LOOPBACK_PORT}" \
    --output-directory "${COMFYUI_ROOT}/output/" \
    "$@" &
comfyui_pid=$!

stop_processes() {
    kill -TERM "${comfyui_pid}" "${proxy_pid}" 2>/dev/null || true
    wait "${comfyui_pid}" 2>/dev/null || true
    wait "${proxy_pid}" 2>/dev/null || true
}

trap 'stop_processes; exit 143' TERM INT

set +e
wait -n "${comfyui_pid}" "${proxy_pid}"
exit_code=$?
set -e

stop_processes
exit "${exit_code}"
