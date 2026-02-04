"""
FastAPI application for Script Generator Service.

This runs on the Linux VM and exposes REST API for:
- Newsletter to video script conversion
- Script generation for multiple formats
"""

import os
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import uvicorn

from .service import ScriptGeneratorService
from .models import (
    GenerateScriptRequest,
    GenerateScriptResponse,
    HealthResponse,
)

# Global service instance
script_service: Optional[ScriptGeneratorService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global script_service

    # Startup
    logger.info("Starting Script Generator Service...")

    script_service = ScriptGeneratorService(
        llm_provider=os.getenv("SCRIPT_LLM_PROVIDER", "local"),
        llm_model=os.getenv("SCRIPT_LLM_MODEL", "qwen2.5:7b"),
        llm_base_url=os.getenv("SCRIPT_LLM_BASE_URL", "http://localhost:11434"),
        openai_api_key=os.getenv("SCRIPT_OPENAI_API_KEY"),
        anthropic_api_key=os.getenv("SCRIPT_ANTHROPIC_API_KEY"),
    )

    await script_service.initialize()
    logger.info("Script Generator Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Script Generator Service...")
    if script_service:
        await script_service.cleanup()
    logger.info("Script Generator Service stopped")


app = FastAPI(
    title="Script Generator Service",
    description="Newsletter to video script conversion using LLMs",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health and LLM availability."""
    if not script_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return await script_service.health_check()


@app.post("/generate", response_model=GenerateScriptResponse)
async def generate_script(request: GenerateScriptRequest):
    """
    Generate video script(s) from newsletter content.

    Supports long-form, short-form, or both formats.
    """
    if not script_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        result = await script_service.generate_script(request)
        return result
    except Exception as e:
        logger.exception(f"Script generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")


@app.post("/generate/quick")
async def generate_quick_script(
    content: str,
    title: str = "Newsletter",
    format: str = "both",
    tone: str = "professional",
):
    """
    Quick script generation with minimal parameters.

    Useful for simple integrations.
    """
    if not script_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    from .models import ScriptFormat, ScriptTone

    request = GenerateScriptRequest(
        newsletter_content=content,
        newsletter_title=title,
        format=ScriptFormat(format),
        tone=ScriptTone(tone),
    )

    try:
        result = await script_service.generate_script(request)
        return result
    except Exception as e:
        logger.exception(f"Script generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")


def main():
    """Run the script generator service."""
    uvicorn.run(
        "services.script_generator.app:app",
        host=os.getenv("SCRIPT_HOST", "0.0.0.0"),
        port=int(os.getenv("SCRIPT_PORT", "5007")),
        reload=os.getenv("SCRIPT_RELOAD", "false").lower() == "true",
        workers=int(os.getenv("SCRIPT_WORKERS", "2")),
    )


if __name__ == "__main__":
    main()
