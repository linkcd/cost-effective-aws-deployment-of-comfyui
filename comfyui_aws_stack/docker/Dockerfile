FROM nvcr.io/nvidia/cuda:12.9.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=America/Los_Angeles

# Install dependencies
RUN apt-get update && apt-get install -y \
    git \
    make build-essential libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm \
    libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev git git-lfs  \
    ffmpeg libsm6 libxext6 cmake libgl1-mesa-glx socat \
    && rm -rf /var/lib/apt/lists/* \
    && git lfs install

# Create and switch to a new user
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    VHS_FORCE_FFMPEG_PATH=/usr/bin/ffmpeg
RUN mkdir -p /home/user/opt/ComfyUI && chown -R user /home/user/opt/ComfyUI

# Pyenv and Python setup
RUN curl https://pyenv.run | bash
ENV PATH=$HOME/.pyenv/shims:$HOME/.pyenv/bin:$PATH
ENV PYTHON_VERSION=3.12.0
RUN pyenv install $PYTHON_VERSION && \
    pyenv global $PYTHON_VERSION && \
    pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu126

# Set the working directory
WORKDIR /home/user/opt/ComfyUI

# Clone ComfyUI and ComfyUI-Manager
RUN git clone --depth 1 https://github.com/Comfy-Org/ComfyUI . && \
    mkdir -p custom_nodes/ComfyUI-Manager && \
    git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager custom_nodes/ComfyUI-Manager

# Install requirements from cloned repositories
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r custom_nodes/ComfyUI-Manager/requirements.txt

# Pre-install the dependencies required by the current ComfyUI-ReActor release.
# The node itself remains installable/updatable through ComfyUI-Manager.
ARG REACTOR_COMMIT=6ad6b35a4df250d14cb2abf0808c9ffedf59f747
RUN git init /tmp/ComfyUI-ReActor && \
    cd /tmp/ComfyUI-ReActor && \
    git remote add origin https://github.com/Gourieff/ComfyUI-ReActor.git && \
    git fetch --depth 1 origin "${REACTOR_COMMIT}" && \
    git checkout --detach FETCH_HEAD && \
    pip install --no-cache-dir "importlib-metadata" "onnxruntime-gpu>=1.20.1" -r requirements.txt && \
    rm -rf /tmp/ComfyUI-ReActor

# Copy the configuration file
COPY comfyui_config/extra_model_paths.yaml ./extra_model_paths.yaml

RUN mkdir -p /home/user/bin
COPY --chown=user:user scripts/configure_comfyui_manager.py /home/user/bin/configure_comfyui_manager.py
COPY --chown=user:user scripts/patch_comfyui_frontend_generated_assets.py /home/user/bin/patch_comfyui_frontend_generated_assets.py
COPY --chown=user:user scripts/patch_comfyui_manager_version_parser.py /home/user/bin/patch_comfyui_manager_version_parser.py
COPY --chown=user:user scripts/start_comfyui.sh /home/user/bin/start_comfyui.sh
RUN python /home/user/bin/patch_comfyui_frontend_generated_assets.py
RUN chmod +x /home/user/bin/start_comfyui.sh

ENTRYPOINT ["/home/user/bin/start_comfyui.sh"]
