# ============================================================
# Newsletter Video Pipeline - Windows GPU Server Setup Script
# ============================================================
# This script sets up the Windows 11 machine with RTX 5090 for:
# - Voice Cloning (XTTS-v2)
# - Avatar Video Generation (MuseTalk + LivePortrait)
# ============================================================

Write-Host "========================================================" -ForegroundColor Green
Write-Host "Newsletter Video Pipeline - Windows GPU Server Setup"
Write-Host "========================================================" -ForegroundColor Green

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Warning: Not running as Administrator. Some commands may fail." -ForegroundColor Yellow
}

# ============================================================
# 1. Check Prerequisites
# ============================================================
Write-Host "`n[1/7] Checking prerequisites..." -ForegroundColor Green

# Check NVIDIA GPU
$gpu = Get-WmiObject Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }
if ($gpu) {
    Write-Host "Found NVIDIA GPU: $($gpu.Name)" -ForegroundColor Cyan
} else {
    Write-Host "ERROR: No NVIDIA GPU found!" -ForegroundColor Red
    exit 1
}

# Check CUDA
$cudaPath = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
if (Test-Path $cudaPath) {
    $cudaVersion = (Get-ChildItem $cudaPath | Sort-Object Name -Descending | Select-Object -First 1).Name
    Write-Host "Found CUDA: $cudaVersion" -ForegroundColor Cyan
} else {
    Write-Host "WARNING: CUDA not found. Please install CUDA Toolkit 12.1+" -ForegroundColor Yellow
    Write-Host "Download from: https://developer.nvidia.com/cuda-downloads" -ForegroundColor Yellow
}

# ============================================================
# 2. Install Docker Desktop
# ============================================================
Write-Host "`n[2/7] Checking Docker Desktop..." -ForegroundColor Green

$dockerInstalled = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerInstalled) {
    Write-Host "Docker Desktop not found. Please install it manually:" -ForegroundColor Yellow
    Write-Host "  1. Download from: https://www.docker.com/products/docker-desktop" -ForegroundColor Yellow
    Write-Host "  2. Enable WSL 2 backend during installation" -ForegroundColor Yellow
    Write-Host "  3. After installation, enable GPU support in Docker Desktop settings" -ForegroundColor Yellow
    Write-Host ""
    $response = Read-Host "Press Enter after installing Docker Desktop, or 'S' to skip"
    if ($response -eq 'S') {
        Write-Host "Skipping Docker check..." -ForegroundColor Yellow
    }
} else {
    Write-Host "Docker is installed." -ForegroundColor Cyan

    # Check if Docker is running
    try {
        docker info | Out-Null
        Write-Host "Docker is running." -ForegroundColor Cyan
    } catch {
        Write-Host "Docker is not running. Please start Docker Desktop." -ForegroundColor Yellow
    }
}

# ============================================================
# 3. Install NVIDIA Container Toolkit
# ============================================================
Write-Host "`n[3/7] Checking NVIDIA Container Toolkit..." -ForegroundColor Green

# For Docker Desktop on Windows, GPU support is built-in with WSL 2
Write-Host "Note: Docker Desktop with WSL 2 includes GPU support automatically." -ForegroundColor Cyan
Write-Host "Make sure 'Use WSL 2 based engine' is enabled in Docker Desktop settings." -ForegroundColor Cyan

# ============================================================
# 4. Create Directory Structure
# ============================================================
Write-Host "`n[4/7] Creating directory structure..." -ForegroundColor Green

$baseDir = "C:\nvp"
$directories = @(
    "$baseDir\data\voices",
    "$baseDir\data\avatars",
    "$baseDir\data\videos\output",
    "$baseDir\models\musetalk",
    "$baseDir\models\liveportrait",
    "$baseDir\configs",
    "$baseDir\logs"
)

foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "Created: $dir" -ForegroundColor Gray
    }
}

Write-Host "Directory structure created at $baseDir" -ForegroundColor Cyan

# ============================================================
# 5. Create Environment File
# ============================================================
Write-Host "`n[5/7] Creating environment configuration..." -ForegroundColor Green

$envFile = "$baseDir\.env"

if (-not (Test-Path $envFile)) {
    $envContent = @"
# ============================================================
# Newsletter Video Pipeline - Windows GPU Server Configuration
# ============================================================

# Data directories (Windows paths)
DATA_DIR=C:/nvp/data
MODELS_DIR=C:/nvp/models

# Voice Cloner settings
VOICE_DEVICE=cuda
VOICE_USE_DEEPSPEED=true

# Avatar Generator settings
AVATAR_DEVICE=cuda

# Network settings (allow connections from Linux VM)
# Make sure Windows Firewall allows ports 5002 and 5003
"@
    $envContent | Out-File -FilePath $envFile -Encoding UTF8
    Write-Host "Created environment file: $envFile" -ForegroundColor Cyan
} else {
    Write-Host "Environment file already exists: $envFile" -ForegroundColor Gray
}

# ============================================================
# 6. Configure Windows Firewall
# ============================================================
Write-Host "`n[6/7] Configuring Windows Firewall..." -ForegroundColor Green

if ($isAdmin) {
    # Allow Voice Cloner port
    $ruleName1 = "NVP-VoiceCloner"
    $existingRule1 = Get-NetFirewallRule -DisplayName $ruleName1 -ErrorAction SilentlyContinue
    if (-not $existingRule1) {
        New-NetFirewallRule -DisplayName $ruleName1 -Direction Inbound -Port 5002 -Protocol TCP -Action Allow | Out-Null
        Write-Host "Created firewall rule for Voice Cloner (port 5002)" -ForegroundColor Cyan
    } else {
        Write-Host "Firewall rule for Voice Cloner already exists" -ForegroundColor Gray
    }

    # Allow Avatar Generator port
    $ruleName2 = "NVP-AvatarGenerator"
    $existingRule2 = Get-NetFirewallRule -DisplayName $ruleName2 -ErrorAction SilentlyContinue
    if (-not $existingRule2) {
        New-NetFirewallRule -DisplayName $ruleName2 -Direction Inbound -Port 5003 -Protocol TCP -Action Allow | Out-Null
        Write-Host "Created firewall rule for Avatar Generator (port 5003)" -ForegroundColor Cyan
    } else {
        Write-Host "Firewall rule for Avatar Generator already exists" -ForegroundColor Gray
    }
} else {
    Write-Host "Skipping firewall configuration (requires Administrator)" -ForegroundColor Yellow
    Write-Host "Please manually allow ports 5002 and 5003 in Windows Firewall" -ForegroundColor Yellow
}

# ============================================================
# 7. Download Models
# ============================================================
Write-Host "`n[7/7] Model download instructions..." -ForegroundColor Green

Write-Host @"

Models will be downloaded automatically on first run, but you can pre-download them:

1. XTTS-v2 Voice Model (~2GB):
   - Downloaded automatically by Coqui TTS on first use
   - Or manually: huggingface-cli download coqui/XTTS-v2 --local-dir C:\nvp\models\xtts

2. MuseTalk Models:
   git clone https://github.com/TMElyralab/MuseTalk.git C:\nvp\models\musetalk
   cd C:\nvp\models\musetalk
   # Follow their model download instructions

3. LivePortrait Models:
   git clone https://github.com/KwaiVGI/LivePortrait.git C:\nvp\models\liveportrait
   cd C:\nvp\models\liveportrait
   # Follow their model download instructions

"@ -ForegroundColor Cyan

# ============================================================
# Build and Start Services
# ============================================================
Write-Host "========================================================" -ForegroundColor Green
Write-Host "Setup Preparation Complete!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green

Write-Host @"

Next steps:

1. Make sure Docker Desktop is running with WSL 2 and GPU support enabled

2. Navigate to the project directory and build the containers:
   cd $baseDir
   # Copy the docker-compose.yml from the project
   docker-compose -f docker-compose.yml build

3. Start the GPU services:
   docker-compose up -d

4. Verify GPU access in containers:
   docker exec nvp-voice-cloner nvidia-smi

5. Update the Linux VM's .env file with this machine's IP address

Services will be available at:
  - Voice Cloner:      http://localhost:5002
  - Avatar Generator:  http://localhost:5003

Find this machine's IP address:
"@ -ForegroundColor White

# Get IP addresses
$ipAddresses = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.*" }
foreach ($ip in $ipAddresses) {
    Write-Host "  $($ip.InterfaceAlias): $($ip.IPAddress)" -ForegroundColor Yellow
}

Write-Host "`nUse one of these IPs as GPU_HOST in the Linux VM's .env file." -ForegroundColor Cyan
