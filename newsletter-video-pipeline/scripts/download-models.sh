#!/bin/bash
# ============================================================
# Newsletter Video Pipeline - Model Download Script
# ============================================================
# This script downloads all required AI models for the pipeline.
# Run this on the Windows GPU server or any machine with the models directory.
# ============================================================

set -e

echo "========================================================"
echo "Newsletter Video Pipeline - Model Download"
echo "========================================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Default models directory
MODELS_DIR="${MODELS_DIR:-/opt/nvp/models}"
mkdir -p "$MODELS_DIR"

cd "$MODELS_DIR"

# ============================================================
# 1. MuseTalk
# ============================================================
echo -e "\n${GREEN}[1/4] Downloading MuseTalk...${NC}"

if [ ! -d "musetalk" ]; then
    git clone https://github.com/TMElyralab/MuseTalk.git musetalk
    cd musetalk

    # Download MuseTalk models from Hugging Face
    echo "Downloading MuseTalk model weights..."
    mkdir -p models

    # Download required models (these are placeholders - actual links from MuseTalk repo)
    # pip install huggingface_hub
    python3 -c "
from huggingface_hub import hf_hub_download
import os

# MuseTalk models
models = [
    ('TMElyralab/MuseTalk', 'models/musetalk/musetalk.pt', 'models/'),
    ('TMElyralab/MuseTalk', 'models/dwpose/dw-ll_ucoco_384.onnx', 'models/'),
    ('TMElyralab/MuseTalk', 'models/face-parse-bisent/79999_iter.pth', 'models/'),
    ('TMElyralab/MuseTalk', 'models/sd-vae-ft-mse/config.json', 'models/'),
]

for repo, filename, local_dir in models:
    try:
        hf_hub_download(repo_id=repo, filename=filename, local_dir=local_dir)
        print(f'Downloaded: {filename}')
    except Exception as e:
        print(f'Warning: Could not download {filename}: {e}')
" || echo "Model download may require manual steps - check MuseTalk README"

    cd "$MODELS_DIR"
else
    echo "MuseTalk already exists, skipping..."
fi

# ============================================================
# 2. LivePortrait
# ============================================================
echo -e "\n${GREEN}[2/4] Downloading LivePortrait...${NC}"

if [ ! -d "liveportrait" ]; then
    git clone https://github.com/KwaiVGI/LivePortrait.git liveportrait
    cd liveportrait

    # Download LivePortrait models
    echo "Downloading LivePortrait model weights..."
    mkdir -p pretrained_weights

    # Use their download script if available
    if [ -f "scripts/download_models.sh" ]; then
        bash scripts/download_models.sh
    else
        echo "Please download LivePortrait models manually from their GitHub releases"
    fi

    cd "$MODELS_DIR"
else
    echo "LivePortrait already exists, skipping..."
fi

# ============================================================
# 3. Face Enhancement (GFPGAN/CodeFormer) - Optional
# ============================================================
echo -e "\n${GREEN}[3/4] Downloading Face Enhancement models (optional)...${NC}"

if [ ! -d "gfpgan" ]; then
    mkdir -p gfpgan
    cd gfpgan

    # Download GFPGAN model
    wget -nc https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.3.pth || true
    wget -nc https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth || true

    cd "$MODELS_DIR"
else
    echo "GFPGAN already exists, skipping..."
fi

# ============================================================
# 4. XTTS-v2 (Downloaded automatically by Coqui TTS)
# ============================================================
echo -e "\n${GREEN}[4/4] XTTS-v2 Model...${NC}"
echo "XTTS-v2 will be downloaded automatically on first use by Coqui TTS."
echo "Alternatively, pre-download with:"
echo "  python -c \"from TTS.api import TTS; TTS('tts_models/multilingual/multi-dataset/xtts_v2')\""

# ============================================================
# Summary
# ============================================================
echo -e "\n${GREEN}========================================================"
echo "Model Download Complete!"
echo "========================================================${NC}"

echo ""
echo "Models directory: $MODELS_DIR"
echo ""
ls -la "$MODELS_DIR"

echo ""
echo -e "${YELLOW}Note: Some models may require additional setup steps.${NC}"
echo "Please check each model's GitHub repository for specific instructions."
