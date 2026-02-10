#!/bin/bash
# NEVER use set -e: handler must start for worker to register as ready

echo "=========================================="
echo "Qwen Image Edit Multi-Angle - Container startup - $(date)"
echo "=========================================="

# Network Volume Setup
NETVOLUME="${NETWORK_VOLUME_PATH:-/runpod-volume}"

echo "Checking Network Volume at $NETVOLUME..."
if [ ! -d "$NETVOLUME" ]; then
    echo "WARNING: Network Volume not found at $NETVOLUME"
    echo "Handler will start but jobs will fail without models"
fi

# Create symlinks (only if volume exists)
if [ -d "$NETVOLUME/models" ]; then
    echo "Creating symlinks..."
    rm -rf /ComfyUI/models/diffusion_models
    rm -rf /ComfyUI/models/text_encoders
    rm -rf /ComfyUI/models/clip
    rm -rf /ComfyUI/models/vae
    rm -rf /ComfyUI/models/loras

    ln -sf $NETVOLUME/models/diffusion_models /ComfyUI/models/diffusion_models
    ln -sf $NETVOLUME/models/text_encoders /ComfyUI/models/text_encoders
    ln -sf $NETVOLUME/models/text_encoders /ComfyUI/models/clip
    ln -sf $NETVOLUME/models/vae /ComfyUI/models/vae
    ln -sf $NETVOLUME/models/loras /ComfyUI/models/loras
    echo "Symlinks created!"
else
    echo "WARNING: $NETVOLUME/models not found, skipping symlinks"
fi

# Auto-download missing models from HuggingFace
download_if_missing() {
    local filepath="$1"
    local url="$2"
    local name="$3"

    if [ -f "$filepath" ]; then
        echo "  [OK] $name"
    else
        echo "  [DOWNLOADING] $name..."
        mkdir -p "$(dirname "$filepath")"
        HF_AUTH=""
        if [ -n "$HF_TOKEN" ]; then
            HF_AUTH="--header=Authorization: Bearer $HF_TOKEN"
        fi
        wget -q --show-progress $HF_AUTH -O "$filepath" "$url"
        if [ $? -eq 0 ]; then
            echo "  [OK] $name (downloaded)"
        else
            echo "  [FAILED] $name - download failed"
            rm -f "$filepath"
        fi
    fi
}

echo "Checking/downloading models..."
mkdir -p "$NETVOLUME/models/diffusion_models" "$NETVOLUME/models/text_encoders" "$NETVOLUME/models/vae" "$NETVOLUME/models/loras"

download_if_missing "$NETVOLUME/models/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors" \
    "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors" \
    "Qwen Image Edit UNET FP8"

download_if_missing "$NETVOLUME/models/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
    "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
    "Qwen 2.5 VL 7B CLIP FP8"

download_if_missing "$NETVOLUME/models/vae/qwen_image_vae.safetensors" \
    "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors" \
    "Qwen Image VAE"

download_if_missing "$NETVOLUME/models/loras/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors" \
    "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Edit-2509/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors" \
    "Lightning 4steps LoRA"

download_if_missing "$NETVOLUME/models/loras/Qwen-Edit-2509-Multiple-angles.safetensors" \
    "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/loras/Qwen-Edit-2509-Multiple-angles.safetensors" \
    "Multiple Angles LoRA"

# GPU Detection
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "Unknown")
echo "Detected GPU: $GPU_NAME"

# Start ComfyUI
echo "Starting ComfyUI..."
python /ComfyUI/main.py --listen &

# Wait for ComfyUI
echo "Waiting for ComfyUI..."
max_wait=180
wait_count=0
while [ $wait_count -lt $max_wait ]; do
    if curl -s http://127.0.0.1:8188/ > /dev/null 2>&1; then
        echo "ComfyUI is ready!"
        break
    fi
    sleep 2
    wait_count=$((wait_count + 2))
done

if [ $wait_count -ge $max_wait ]; then
    echo "WARNING: ComfyUI failed to start within timeout, starting handler anyway"
fi

# CRITICAL: Handler MUST start for worker to register as ready
echo "Starting handler..."
exec python handler.py
