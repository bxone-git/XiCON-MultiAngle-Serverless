#!/bin/bash

# Setup network volume with required models for I2I MultiAngle
# Downloads models from Hugging Face if not already present

NETWORK_VOLUME_PATH="${NETWORK_VOLUME_PATH:-/runpod-volume/models}"

echo "Setting up network volume at: $NETWORK_VOLUME_PATH"

# Create directories
mkdir -p "$NETWORK_VOLUME_PATH/diffusion_models"
mkdir -p "$NETWORK_VOLUME_PATH/text_encoders"
mkdir -p "$NETWORK_VOLUME_PATH/vae"
mkdir -p "$NETWORK_VOLUME_PATH/loras"

# Function to download model if it doesn't exist
download_model() {
    local filename=$1
    local url=$2
    local filepath="$NETWORK_VOLUME_PATH/$filename"

    if [ -f "$filepath" ]; then
        echo "✓ Already exists: $filename"
    else
        echo "↓ Downloading: $filename"
        mkdir -p "$(dirname "$filepath")"
        wget -q --show-progress -O "$filepath" "$url"
        if [ $? -eq 0 ]; then
            echo "✓ Downloaded: $filename"
        else
            echo "✗ Failed to download: $filename"
            return 1
        fi
    fi
}

# Download models
echo ""
echo "Downloading Qwen Image Edit models..."
download_model "diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors" \
    "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors"

echo ""
echo "Downloading Qwen Image text encoder..."
download_model "text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
    "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"

echo ""
echo "Downloading Qwen Image VAE..."
download_model "vae/qwen_image_vae.safetensors" \
    "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors"

echo ""
echo "Downloading Qwen Multi-Angle LoRA..."
download_model "loras/Qwen-Edit-2509-Multiple-angles.safetensors" \
    "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/loras/Qwen-Edit-2509-Multiple-angles.safetensors"

echo ""
echo "Downloading Qwen Lightning LoRA..."
download_model "loras/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors" \
    "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Edit-2509/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors"

echo ""
echo "✓ Network volume setup complete!"
