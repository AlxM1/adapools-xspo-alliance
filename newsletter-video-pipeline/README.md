# Newsletter Video Pipeline

A fully self-hosted, automated pipeline that converts newsletters into engaging video content with AI avatars and voice cloning, then publishes to multiple social media platforms.

## Features

- **Newsletter to Script**: AI-powered conversion of newsletter content to engaging video scripts
- **Voice Cloning**: Clone your voice with XTTS-v2 for authentic narration
- **AI Avatar**: Generate talking head videos with MuseTalk + LivePortrait
- **Multi-Platform**: Automatic format optimization for YouTube, TikTok, Instagram, and X
- **Auto-Publishing**: Scheduled publishing to all major platforms
- **Shorts Generation**: Automatically create short-form clips from long-form content
- **Fully Self-Hosted**: No cloud dependencies, runs on your own hardware

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LINUX VM (Orchestration)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ API Gateway  │  │    Video     │  │   Social     │  │   Script     │    │
│  │   :8000      │  │  Processor   │  │  Publisher   │  │  Generator   │    │
│  │              │  │    :5005     │  │    :5006     │  │    :5007     │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                            Network Connection
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                      WINDOWS GPU SERVER (RTX 5090)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────┐  ┌──────────────────────────────┐        │
│  │       Voice Cloner          │  │     Avatar Generator         │        │
│  │     (XTTS-v2) :5002         │  │  (MuseTalk+LivePortrait)     │        │
│  │                             │  │         :5003                 │        │
│  └──────────────────────────────┘  └──────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Requirements

### Linux VM
- Ubuntu 22.04+ or similar
- Docker & Docker Compose
- 8GB+ RAM
- 50GB+ storage
- Network access to Windows GPU server

### Windows GPU Server
- Windows 11 with WSL 2
- Docker Desktop with GPU support
- NVIDIA RTX 5090 (32GB VRAM)
- CUDA 12.1+
- 64GB+ RAM recommended
- 200GB+ storage for models

## Quick Start

### 1. Setup Linux VM

```bash
# Clone the repository
git clone https://github.com/your-repo/newsletter-video-pipeline.git
cd newsletter-video-pipeline

# Run setup script
chmod +x scripts/setup-linux-vm.sh
./scripts/setup-linux-vm.sh

# Edit configuration
nano /opt/nvp/.env  # Set GPU_HOST to your Windows machine IP
```

### 2. Setup Windows GPU Server

```powershell
# Run PowerShell as Administrator
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Run setup script
.\scripts\setup-windows-gpu.ps1

# Start GPU services
cd C:\nvp
docker-compose up -d
```

### 3. Verify Installation

```bash
# Check all services are healthy
curl http://localhost:8000/health
```

## Usage

### Full Pipeline

```bash
curl -X POST http://localhost:8000/pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "newsletter_content": "Your newsletter content here...",
    "newsletter_title": "Weekly Update #42",
    "generate_long_form": true,
    "generate_shorts": true,
    "shorts_count": 3,
    "target_platforms": ["youtube", "tiktok", "instagram", "x"],
    "auto_publish": false
  }'
```

### Create Voice Clone

```bash
# Upload voice samples (30+ seconds of clear speech recommended)
curl -X POST http://GPU_HOST:5002/voices/clone \
  -F "name=MyVoice" \
  -F "language=en" \
  -F "audio_files=@sample1.wav" \
  -F "audio_files=@sample2.wav" \
  -F "set_as_default=true"
```

### Create Avatar

```bash
# Upload a reference video (10-30 seconds with clear face)
curl -X POST http://GPU_HOST:5003/avatars/create \
  -F "name=MyAvatar" \
  -F "set_as_default=true" \
  -F "video_file=@reference_video.mp4"
```

### Connect Social Media

Visit `http://localhost:8000/docs` and use the OAuth endpoints:
- `/auth/youtube` - Connect YouTube
- `/auth/tiktok` - Connect TikTok
- `/auth/instagram` - Connect Instagram
- `/auth/x` - Connect X/Twitter

## API Documentation

Interactive API documentation is available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Main Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/pipeline` | POST | Execute full newsletter-to-video pipeline |
| `/pipeline/{job_id}` | GET | Get pipeline job status |
| `/health` | GET | System health check |
| `/voices` | GET | List cloned voices |
| `/avatars` | GET | List available avatars |
| `/platforms` | GET | List publishing platforms |

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GPU_HOST` | IP address of Windows GPU server | `192.168.1.100` |
| `LLM_PROVIDER` | LLM provider (local/openai/anthropic) | `local` |
| `LLM_MODEL` | LLM model name | `qwen2.5:7b` |
| `OLLAMA_URL` | Ollama server URL | `http://localhost:11434` |

See `.env.example` for full configuration options.

## Platform-Specific Output

| Platform | Resolution | Aspect Ratio | Max Duration |
|----------|------------|--------------|--------------|
| YouTube | 1920x1080 | 16:9 | Unlimited |
| YouTube Shorts | 1080x1920 | 9:16 | 60 seconds |
| TikTok | 1080x1920 | 9:16 | 10 minutes |
| Instagram Reels | 1080x1920 | 9:16 | 90 seconds |
| X/Twitter | 1920x1080 | 16:9 | 2:20 |

## Models Used

| Component | Model | Size | License |
|-----------|-------|------|---------|
| Voice Cloning | XTTS-v2 | ~2GB | Coqui Public License |
| Lip Sync | MuseTalk | ~4GB | MIT |
| Face Animation | LivePortrait | ~3GB | MIT |
| Script Generation | Qwen 2.5 7B (local) | ~4GB | Apache 2.0 |

## Troubleshooting

### GPU Not Detected

```bash
# Check NVIDIA driver
nvidia-smi

# Check Docker GPU support
docker run --rm --gpus all nvidia/cuda:12.1-base nvidia-smi
```

### Services Not Connecting

```bash
# Check network connectivity
ping GPU_HOST_IP

# Check firewall ports (Windows)
netsh advfirewall firewall show rule name="NVP-VoiceCloner"
```

### Model Download Issues

```bash
# Manually download models
./scripts/download-models.sh

# Or pull specific model
python -c "from TTS.api import TTS; TTS('tts_models/multilingual/multi-dataset/xtts_v2')"
```

## Contributing

Contributions are welcome! Please read our contributing guidelines and submit pull requests.

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- [Coqui TTS](https://github.com/coqui-ai/TTS) - Voice cloning
- [MuseTalk](https://github.com/TMElyralab/MuseTalk) - Lip sync
- [LivePortrait](https://github.com/KwaiVGI/LivePortrait) - Face animation
- [FFmpeg](https://ffmpeg.org/) - Video processing
