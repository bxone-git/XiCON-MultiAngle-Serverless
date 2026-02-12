# Qwen Image Edit Multi-Angle - Network Volume
# CUDA 13.0 + PyTorch nightly cu130 (Blackwell/5090 sm_120 support)
# Tag: ghcr.io/bxone-git/xicon-multiangle-serverless:latest

FROM nvidia/cuda:13.0.2-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip python3.10-venv \
    git curl wget \
    libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/bin/python

# PyTorch with CUDA 13.0 nightly (Blackwell sm_120 support)
ENV TORCH_CUDA_ARCH_LIST="12.0"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/cu130

# Python packages
RUN pip install --no-cache-dir -U "huggingface_hub[hf_transfer]" runpod websocket-client
RUN pip install --no-cache-dir triton sageattention --no-build-isolation

WORKDIR /

# ComfyUI
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git && \
    cd /ComfyUI && pip install --no-cache-dir -r requirements.txt

# Custom nodes (minimal for Flux 2 Klein image edit)
RUN cd /ComfyUI/custom_nodes && \
    git clone --depth 1 https://github.com/Comfy-Org/ComfyUI-Manager.git && \
    cd ComfyUI-Manager && pip install --no-cache-dir -r requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone --depth 1 https://github.com/cubiq/ComfyUI_essentials.git && \
    if [ -f ComfyUI_essentials/requirements.txt ]; then \
        cd ComfyUI_essentials && pip install --no-cache-dir -r requirements.txt; \
    fi

# Model directories (symlinked at runtime from network volume)
RUN mkdir -p /ComfyUI/models/diffusion_models \
    /ComfyUI/models/text_encoders \
    /ComfyUI/models/clip \
    /ComfyUI/models/vae \
    /ComfyUI/models/loras \
    /ComfyUI/input \
    /ComfyUI/output

# Cleanup to save space
RUN rm -rf /root/.cache /tmp/* /var/tmp/*

# NO MODEL DOWNLOADS - Network Volume 사용

COPY . .
RUN mkdir -p /ComfyUI/user/default/ComfyUI-Manager
COPY config.ini /ComfyUI/user/default/ComfyUI-Manager/config.ini
RUN chmod +x /entrypoint.sh
RUN chmod +x /setup_netvolume.sh 2>/dev/null || true

CMD ["/entrypoint.sh"]
