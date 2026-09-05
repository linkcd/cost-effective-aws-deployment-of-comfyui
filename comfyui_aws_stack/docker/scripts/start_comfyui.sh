#!/usr/bin/env bash
set -euo pipefail

COMFYUI_ROOT="/home/user/opt/ComfyUI"
MANAGER_CONFIG="${COMFYUI_ROOT}/user/__manager/config.ini"
MANAGER_UTIL="${COMFYUI_ROOT}/custom_nodes/ComfyUI-Manager/glob/manager_util.py"
MODEL_CACHE_MANIFEST="/home/user/bin/h3_model_cache_manifest.json"
MODEL_CACHE_CONFIG="/tmp/comfyui-h3-model-paths.yaml"
PUBLIC_PORT="8181"
LOOPBACK_PORT="8182"

mkdir -p \
    "${COMFYUI_ROOT}/models/diffusion_models" \
    "${COMFYUI_ROOT}/models/unet_gguf" \
    "${COMFYUI_ROOT}/models/model_gguf" \
    "${COMFYUI_ROOT}/models/ultralytics/bbox" \
    "${COMFYUI_ROOT}/models/ultralytics/segm"

model_path_args=()
python /home/user/bin/sync_model_cache.py \
    --comfyui-root "${COMFYUI_ROOT}" \
    --cache-root "${COMFYUI_MODEL_CACHE_ROOT:-/mnt/comfy-cache}" \
    --manifest "${MODEL_CACHE_MANIFEST}" \
    --config-output "${MODEL_CACHE_CONFIG}" \
    --enabled "${COMFYUI_MODEL_CACHE_ENABLED:-1}"
if [[ -s "${MODEL_CACHE_CONFIG}" ]]; then
    model_path_args=(
        --extra-model-paths-config
        "${MODEL_CACHE_CONFIG}"
    )
fi

python /home/user/bin/report_runtime.py
python /home/user/bin/patch_comfyui_manager_version_parser.py "${MANAGER_UTIL}"
python /home/user/bin/patch_comfyui_privacy_logging.py "${COMFYUI_ROOT}"
python /home/user/bin/configure_comfyui_manager.py "${MANAGER_CONFIG}"

socat \
    "TCP-LISTEN:${PUBLIC_PORT},bind=0.0.0.0,reuseaddr,fork" \
    "TCP:127.0.0.1:${LOOPBACK_PORT}" &
proxy_pid=$!

python "${COMFYUI_ROOT}/main.py" \
    --listen 127.0.0.1 \
    --port "${LOOPBACK_PORT}" \
    --enable-assets \
    --output-directory "${COMFYUI_ROOT}/output/" \
    "${model_path_args[@]}" \
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
