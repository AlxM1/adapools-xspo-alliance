#!/bin/bash
# ============================================================
# Newsletter Video Pipeline - Linux VM Setup Script
# ============================================================
# This script sets up the Linux VM for running:
# - API Gateway
# - Video Processor
# - Social Publisher
# - Script Generator
# ============================================================

set -e

echo "========================================================"
echo "Newsletter Video Pipeline - Linux VM Setup"
echo "========================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}Warning: Not running as root. Some commands may fail.${NC}"
    SUDO="sudo"
else
    SUDO=""
fi

# ============================================================
# 1. Install System Dependencies
# ============================================================
echo -e "\n${GREEN}[1/6] Installing system dependencies...${NC}"

# Detect package manager
if command -v apt-get &> /dev/null; then
    $SUDO apt-get update
    $SUDO apt-get install -y \
        docker.io \
        docker-compose \
        ffmpeg \
        git \
        curl \
        wget \
        python3 \
        python3-pip \
        python3-venv
elif command -v dnf &> /dev/null; then
    $SUDO dnf install -y \
        docker \
        docker-compose \
        ffmpeg \
        git \
        curl \
        wget \
        python3 \
        python3-pip
else
    echo -e "${RED}Unsupported package manager. Please install dependencies manually.${NC}"
    exit 1
fi

# ============================================================
# 2. Configure Docker
# ============================================================
echo -e "\n${GREEN}[2/6] Configuring Docker...${NC}"

# Start and enable Docker
$SUDO systemctl start docker
$SUDO systemctl enable docker

# Add current user to docker group
$SUDO usermod -aG docker $USER

echo -e "${YELLOW}Note: You may need to log out and back in for docker group changes to take effect.${NC}"

# ============================================================
# 3. Create Directory Structure
# ============================================================
echo -e "\n${GREEN}[3/6] Creating directory structure...${NC}"

# Create base directories
$SUDO mkdir -p /opt/nvp/{data,configs,logs}
$SUDO mkdir -p /opt/nvp/data/{videos/output,voices,avatars,credentials}

# Set permissions
$SUDO chown -R $USER:$USER /opt/nvp

echo "Created directories:"
echo "  /opt/nvp/data         - Data storage"
echo "  /opt/nvp/configs      - Configuration files"
echo "  /opt/nvp/logs         - Log files"

# ============================================================
# 4. Create Environment File
# ============================================================
echo -e "\n${GREEN}[4/6] Creating environment configuration...${NC}"

ENV_FILE="/opt/nvp/.env"

if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" << 'EOF'
# ============================================================
# Newsletter Video Pipeline - Environment Configuration
# ============================================================

# GPU Server Configuration (Windows machine with RTX 5090)
GPU_HOST=192.168.1.100

# Data directories
DATA_DIR=/opt/nvp/data
CONFIG_DIR=/opt/nvp/configs

# LLM Configuration (for script generation)
# Options: local (Ollama), openai, anthropic
LLM_PROVIDER=local
LLM_MODEL=qwen2.5:7b
OLLAMA_URL=http://localhost:11434

# OpenAI (optional)
OPENAI_API_KEY=

# Anthropic (optional)
ANTHROPIC_API_KEY=

# TikTok API (get from https://developers.tiktok.com/)
TIKTOK_CLIENT_KEY=
TIKTOK_CLIENT_SECRET=
TIKTOK_REDIRECT_URI=http://localhost:8000/auth/tiktok/callback

# X/Twitter API (get from https://developer.twitter.com/)
X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
X_BEARER_TOKEN=
EOF
    echo "Created environment file: $ENV_FILE"
    echo -e "${YELLOW}Please edit $ENV_FILE with your configuration.${NC}"
else
    echo "Environment file already exists: $ENV_FILE"
fi

# ============================================================
# 5. Install Ollama (Optional - for local LLM)
# ============================================================
echo -e "\n${GREEN}[5/6] Installing Ollama (optional, for local LLM)...${NC}"

if ! command -v ollama &> /dev/null; then
    read -p "Install Ollama for local LLM support? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        curl -fsSL https://ollama.com/install.sh | sh

        # Start Ollama service
        $SUDO systemctl start ollama
        $SUDO systemctl enable ollama

        # Pull recommended model
        echo "Pulling Qwen 2.5 7B model..."
        ollama pull qwen2.5:7b

        echo -e "${GREEN}Ollama installed and configured.${NC}"
    else
        echo "Skipping Ollama installation."
    fi
else
    echo "Ollama already installed."
fi

# ============================================================
# 6. Build and Start Services
# ============================================================
echo -e "\n${GREEN}[6/6] Building and starting services...${NC}"

# Navigate to project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR/docker/linux-vm"

# Build images
echo "Building Docker images..."
docker-compose build

# Start services
echo "Starting services..."
docker-compose up -d

# ============================================================
# Summary
# ============================================================
echo -e "\n${GREEN}========================================================"
echo "Setup Complete!"
echo "========================================================${NC}"
echo ""
echo "Services running:"
echo "  - API Gateway:      http://localhost:8000"
echo "  - Video Processor:  http://localhost:5005"
echo "  - Social Publisher: http://localhost:5006"
echo "  - Script Generator: http://localhost:5007"
echo ""
echo "Next steps:"
echo "  1. Edit /opt/nvp/.env with your GPU server IP and API keys"
echo "  2. Set up the Windows GPU server (run setup-windows-gpu.ps1)"
echo "  3. Configure social media OAuth (visit http://localhost:8000/docs)"
echo "  4. Create your voice clone and avatar"
echo ""
echo "API Documentation: http://localhost:8000/docs"
echo ""
echo "Check service status: docker-compose ps"
echo "View logs: docker-compose logs -f"
