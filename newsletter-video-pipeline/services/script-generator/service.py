"""
Script Generator Service Implementation.

This service converts newsletter content into video scripts using LLMs.
Supports local (Ollama), OpenAI, and Anthropic backends.
"""

import os
import json
import time
import re
from typing import Optional
import asyncio

from loguru import logger

from .models import (
    GenerateScriptRequest,
    GenerateScriptResponse,
    GeneratedScript,
    ScriptSection,
    ScriptFormat,
    ScriptTone,
    HealthResponse,
)


class ScriptGeneratorService:
    """Newsletter to video script conversion service."""

    VERSION = "1.0.0"

    # Approximate words per minute for speech
    WORDS_PER_MINUTE = 150

    # Tone prompts
    TONE_PROMPTS = {
        ScriptTone.PROFESSIONAL: "professional, authoritative, and clear",
        ScriptTone.CASUAL: "friendly, relaxed, and approachable",
        ScriptTone.ENTHUSIASTIC: "energetic, excited, and passionate",
        ScriptTone.EDUCATIONAL: "informative, patient, and thorough",
        ScriptTone.CONVERSATIONAL: "natural, like talking to a friend",
    }

    def __init__(
        self,
        llm_provider: str = "local",
        llm_model: str = "qwen2.5:7b",
        llm_base_url: str = "http://localhost:11434",
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
    ):
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.llm_base_url = llm_base_url
        self.openai_api_key = openai_api_key
        self.anthropic_api_key = anthropic_api_key

        # LLM client
        self._client = None
        self._llm_available = False

    async def initialize(self):
        """Initialize the LLM client."""
        logger.info(f"Initializing Script Generator with {self.llm_provider}...")

        try:
            if self.llm_provider == "local":
                await self._init_local()
            elif self.llm_provider == "openai":
                await self._init_openai()
            elif self.llm_provider == "anthropic":
                await self._init_anthropic()
            else:
                raise ValueError(f"Unknown LLM provider: {self.llm_provider}")

            self._llm_available = True
            logger.info(f"Script Generator initialized with {self.llm_provider}/{self.llm_model}")

        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            self._llm_available = False

    async def _init_local(self):
        """Initialize local Ollama client."""
        import httpx

        # Check if Ollama is running
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.llm_base_url}/api/tags", timeout=5)
            if response.status_code != 200:
                raise ConnectionError("Ollama not available")

            models = response.json().get("models", [])
            model_names = [m.get("name", "").split(":")[0] for m in models]

            if self.llm_model.split(":")[0] not in model_names:
                logger.warning(
                    f"Model {self.llm_model} not found. "
                    f"Available: {model_names}. Will attempt to pull."
                )

        self._client = {"type": "ollama", "base_url": self.llm_base_url}

    async def _init_openai(self):
        """Initialize OpenAI client."""
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not provided")

        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=self.openai_api_key)

    async def _init_anthropic(self):
        """Initialize Anthropic client."""
        if not self.anthropic_api_key:
            raise ValueError("Anthropic API key not provided")

        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=self.anthropic_api_key)

    async def generate_script(
        self,
        request: GenerateScriptRequest,
    ) -> GenerateScriptResponse:
        """
        Generate video script from newsletter content.

        Args:
            request: Generation request with newsletter content and settings

        Returns:
            GenerateScriptResponse with generated scripts
        """
        if not self._llm_available:
            raise RuntimeError("LLM not available. Call initialize() first.")

        start_time = time.time()
        tokens_used = 0

        long_form = None
        short_form = None
        shorts_clips = []

        # Generate long-form script
        if request.format in [ScriptFormat.LONG_FORM, ScriptFormat.BOTH]:
            logger.info("Generating long-form script...")
            long_form, tokens = await self._generate_long_form(request)
            tokens_used += tokens

        # Generate short-form script
        if request.format in [ScriptFormat.SHORT_FORM, ScriptFormat.BOTH]:
            logger.info("Generating short-form script...")

            if long_form:
                # Extract shorts from long-form
                shorts_clips, tokens = await self._extract_shorts_from_long(
                    long_form, request
                )
                tokens_used += tokens

                # Use first short as main short-form
                if shorts_clips:
                    short_form = shorts_clips[0]
            else:
                short_form, tokens = await self._generate_short_form(request)
                tokens_used += tokens

        processing_time = time.time() - start_time

        logger.info(
            f"Script generation complete: "
            f"long_form={'yes' if long_form else 'no'}, "
            f"short_form={'yes' if short_form else 'no'}, "
            f"shorts={len(shorts_clips)}, "
            f"tokens={tokens_used}, "
            f"time={processing_time:.2f}s"
        )

        return GenerateScriptResponse(
            long_form=long_form,
            short_form=short_form,
            shorts_clips=shorts_clips,
            processing_time_sec=processing_time,
            tokens_used=tokens_used,
            message="Script(s) generated successfully",
        )

    async def _generate_long_form(
        self,
        request: GenerateScriptRequest,
    ) -> tuple[GeneratedScript, int]:
        """Generate long-form video script."""

        target_words = int(request.target_long_duration_sec / 60 * self.WORDS_PER_MINUTE)
        tone_desc = self.TONE_PROMPTS.get(request.tone, "professional")

        prompt = f"""You are an expert video scriptwriter. Convert this newsletter into an engaging video script.

NEWSLETTER CONTENT:
{request.newsletter_title or 'Newsletter'}
---
{request.newsletter_content}
---

REQUIREMENTS:
- Target duration: {request.target_long_duration_sec} seconds (~{target_words} words)
- Tone: {tone_desc}
- Format: Spoken script for a single presenter video
{"- Start with an attention-grabbing hook (first 5-10 seconds)" if request.include_hook else ""}
{"- End with a clear call-to-action" if request.include_cta else ""}
{"- Include timestamps for each section" if request.include_timestamps else ""}

{f"PERSONA: {request.persona_description}" if request.persona_description else ""}
{f"ADDITIONAL INSTRUCTIONS: {request.custom_instructions}" if request.custom_instructions else ""}

OUTPUT FORMAT (JSON):
{{
    "title": "Video title (catchy, under 100 chars)",
    "description": "Video description (2-3 sentences)",
    "hook": "Opening hook line (if requested)",
    "sections": [
        {{
            "title": "Section name",
            "content": "Full spoken script for this section",
            "duration_estimate_sec": 60,
            "timestamp": "0:00"
        }}
    ],
    "cta": "Call to action (if requested)",
    "hashtags": ["relevant", "hashtags"],
    "keywords": ["seo", "keywords"]
}}

Generate the complete video script now:"""

        response, tokens = await self._call_llm(prompt)

        # Parse response
        script_data = self._parse_script_response(response)

        # Calculate full script and metrics
        full_script = self._build_full_script(script_data)
        word_count = len(full_script.split())
        duration_estimate = int(word_count / self.WORDS_PER_MINUTE * 60)

        return GeneratedScript(
            title=script_data.get("title", request.newsletter_title or "Video"),
            description=script_data.get("description", ""),
            hook=script_data.get("hook"),
            sections=[
                ScriptSection(**s) for s in script_data.get("sections", [])
            ],
            cta=script_data.get("cta"),
            full_script=full_script,
            word_count=word_count,
            estimated_duration_sec=duration_estimate,
            hashtags=script_data.get("hashtags", []),
            keywords=script_data.get("keywords", []),
        ), tokens

    async def _generate_short_form(
        self,
        request: GenerateScriptRequest,
    ) -> tuple[GeneratedScript, int]:
        """Generate short-form video script (TikTok/Reels style)."""

        target_words = int(request.target_short_duration_sec / 60 * self.WORDS_PER_MINUTE)
        tone_desc = self.TONE_PROMPTS.get(request.tone, "professional")

        prompt = f"""You are an expert short-form video scriptwriter. Create a viral TikTok/Reels script from this newsletter.

NEWSLETTER CONTENT:
{request.newsletter_content[:2000]}

REQUIREMENTS:
- Duration: {request.target_short_duration_sec} seconds (~{target_words} words MAX)
- Tone: {tone_desc}
- MUST hook viewer in first 2 seconds
- Fast-paced, punchy delivery
- One clear takeaway

OUTPUT FORMAT (JSON):
{{
    "title": "Short catchy title",
    "description": "Brief description",
    "hook": "MUST grab attention immediately",
    "sections": [
        {{
            "title": "Main point",
            "content": "The actual script - short and punchy",
            "duration_estimate_sec": {request.target_short_duration_sec}
        }}
    ],
    "cta": "Quick CTA",
    "hashtags": ["trending", "relevant", "hashtags"]
}}

Generate the short-form script:"""

        response, tokens = await self._call_llm(prompt)
        script_data = self._parse_script_response(response)

        full_script = self._build_full_script(script_data)
        word_count = len(full_script.split())

        return GeneratedScript(
            title=script_data.get("title", ""),
            description=script_data.get("description", ""),
            hook=script_data.get("hook"),
            sections=[
                ScriptSection(**s) for s in script_data.get("sections", [])
            ],
            cta=script_data.get("cta"),
            full_script=full_script,
            word_count=word_count,
            estimated_duration_sec=request.target_short_duration_sec,
            hashtags=script_data.get("hashtags", []),
            keywords=script_data.get("keywords", []),
        ), tokens

    async def _extract_shorts_from_long(
        self,
        long_form: GeneratedScript,
        request: GenerateScriptRequest,
    ) -> tuple[list[GeneratedScript], int]:
        """Extract multiple short clips from long-form script."""

        prompt = f"""Extract 3 viral short-form clips (15-60 seconds each) from this video script.

FULL SCRIPT:
{long_form.full_script}

REQUIREMENTS:
- Each clip must stand alone and make sense without context
- Each must have a strong hook
- Focus on the most interesting/valuable moments
- Target duration: 30-45 seconds each

OUTPUT FORMAT (JSON):
{{
    "clips": [
        {{
            "title": "Clip title",
            "hook": "Attention-grabbing opener",
            "content": "The clip script",
            "hashtags": ["relevant", "hashtags"]
        }}
    ]
}}

Extract the clips:"""

        response, tokens = await self._call_llm(prompt)

        try:
            data = self._parse_script_response(response)
            clips_data = data.get("clips", [])
        except:
            clips_data = []

        shorts = []
        for clip in clips_data[:3]:
            content = clip.get("content", "")
            word_count = len(content.split())

            shorts.append(GeneratedScript(
                title=clip.get("title", ""),
                description="",
                hook=clip.get("hook"),
                sections=[ScriptSection(
                    title="Main",
                    content=content,
                    duration_estimate_sec=int(word_count / self.WORDS_PER_MINUTE * 60),
                )],
                cta=None,
                full_script=f"{clip.get('hook', '')} {content}".strip(),
                word_count=word_count,
                estimated_duration_sec=int(word_count / self.WORDS_PER_MINUTE * 60),
                hashtags=clip.get("hashtags", []),
                keywords=[],
            ))

        return shorts, tokens

    async def _call_llm(self, prompt: str) -> tuple[str, int]:
        """Call the LLM and return response with token count."""

        if self.llm_provider == "local":
            return await self._call_ollama(prompt)
        elif self.llm_provider == "openai":
            return await self._call_openai(prompt)
        elif self.llm_provider == "anthropic":
            return await self._call_anthropic(prompt)
        else:
            raise ValueError(f"Unknown provider: {self.llm_provider}")

    async def _call_ollama(self, prompt: str) -> tuple[str, int]:
        """Call local Ollama API."""
        import httpx

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.llm_base_url}/api/generate",
                json={
                    "model": self.llm_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9,
                    },
                },
            )

            data = response.json()
            return data.get("response", ""), data.get("eval_count", 0)

    async def _call_openai(self, prompt: str) -> tuple[str, int]:
        """Call OpenAI API."""
        response = await self._client.chat.completions.create(
            model=self.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        return (
            response.choices[0].message.content,
            response.usage.total_tokens if response.usage else 0,
        )

    async def _call_anthropic(self, prompt: str) -> tuple[str, int]:
        """Call Anthropic API."""
        response = await self._client.messages.create(
            model=self.llm_model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        return (
            response.content[0].text,
            response.usage.input_tokens + response.usage.output_tokens,
        )

    def _parse_script_response(self, response: str) -> dict:
        """Parse LLM response to extract JSON."""
        # Try to find JSON in response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Fallback: create basic structure from text
        return {
            "title": "Video",
            "description": "",
            "sections": [{
                "title": "Main",
                "content": response,
                "duration_estimate_sec": 300,
            }],
        }

    def _build_full_script(self, script_data: dict) -> str:
        """Build full script text from structured data."""
        parts = []

        if script_data.get("hook"):
            parts.append(script_data["hook"])

        for section in script_data.get("sections", []):
            parts.append(section.get("content", ""))

        if script_data.get("cta"):
            parts.append(script_data["cta"])

        return "\n\n".join(parts)

    async def health_check(self) -> HealthResponse:
        """Check service health."""
        return HealthResponse(
            status="healthy" if self._llm_available else "degraded",
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            llm_available=self._llm_available,
            version=self.VERSION,
        )

    async def cleanup(self):
        """Cleanup resources."""
        logger.info("Script generator service cleaned up")
