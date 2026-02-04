"""
AI-powered content scoring and segmentation.

Analyzes newsletter content to:
- Score engagement potential (0-100)
- Extract high-value segments for short-form videos
- Identify hooks, quotes, statistics, and insights
"""

import os
import re
from typing import Optional
import httpx


class ContentScorer:
    """AI-powered content analysis for engagement potential."""

    def __init__(self):
        self.llm_url = os.getenv("LLM_URL", "http://localhost:11434")
        self.llm_model = os.getenv("LLM_MODEL", "qwen2.5:7b")

    async def score_content(self, title: str, content: str) -> float:
        """
        Score content for engagement potential (0-100).

        Factors considered:
        - Hook strength (opening line)
        - Emotional resonance
        - Actionable insights
        - Storytelling elements
        - Data/statistics presence
        - Controversy/novelty factor
        """
        # Use heuristics + LLM for scoring
        heuristic_score = self._heuristic_score(title, content)

        try:
            llm_score = await self._llm_score(title, content)
            # Weighted average: 40% heuristics, 60% LLM
            final_score = (heuristic_score * 0.4) + (llm_score * 0.6)
        except Exception:
            final_score = heuristic_score

        return round(min(100, max(0, final_score)), 2)

    def _heuristic_score(self, title: str, content: str) -> float:
        """Calculate heuristic engagement score."""
        score = 50.0  # Base score

        # Title analysis
        title_lower = title.lower()

        # Power words in title
        power_words = [
            "secret", "revealed", "shocking", "breaking", "exclusive",
            "ultimate", "proven", "instant", "guaranteed", "free",
            "new", "discover", "how to", "why", "what", "best",
            "worst", "top", "essential", "critical", "urgent"
        ]
        for word in power_words:
            if word in title_lower:
                score += 3

        # Numbers in title (listicles perform well)
        if re.search(r'\d+', title):
            score += 5

        # Question in title
        if "?" in title:
            score += 3

        # Content analysis
        content_lower = content.lower()
        word_count = len(content.split())

        # Optimal length (500-2000 words)
        if 500 <= word_count <= 2000:
            score += 10
        elif word_count < 200:
            score -= 10

        # Statistics and data
        stat_patterns = [
            r'\d+%',  # Percentages
            r'\$[\d,]+',  # Dollar amounts
            r'\d+x',  # Multipliers
            r'\d+\s*(million|billion|thousand)',  # Large numbers
        ]
        for pattern in stat_patterns:
            if re.search(pattern, content_lower):
                score += 5

        # Quotes (social proof)
        quote_count = content.count('"') // 2
        score += min(quote_count * 2, 10)

        # Emotional words
        emotional_words = [
            "amazing", "incredible", "terrible", "shocking",
            "beautiful", "horrible", "exciting", "scary",
            "love", "hate", "fear", "hope", "dream"
        ]
        for word in emotional_words:
            if word in content_lower:
                score += 2

        # Actionable content indicators
        action_words = [
            "step", "tip", "strategy", "method", "technique",
            "guide", "tutorial", "how-to", "lesson", "hack"
        ]
        for word in action_words:
            if word in content_lower:
                score += 3

        # Storytelling indicators
        story_words = [
            "story", "journey", "experience", "learned",
            "discovered", "realized", "mistake", "failure",
            "success", "transformation"
        ]
        for word in story_words:
            if word in content_lower:
                score += 2

        return score

    async def _llm_score(self, title: str, content: str) -> float:
        """Get LLM-based engagement score."""
        # Truncate content for LLM
        truncated = content[:3000] if len(content) > 3000 else content

        prompt = f"""Analyze this newsletter content for video engagement potential.
Score from 0-100 based on:
- Hook strength (will people stop scrolling?)
- Emotional impact
- Actionable value
- Shareability
- Visual potential for video

Title: {title}

Content:
{truncated}

Respond with ONLY a number between 0 and 100."""

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.llm_url}/api/generate",
                    json={
                        "model": self.llm_model,
                        "prompt": prompt,
                        "stream": False,
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    score_text = result.get("response", "50").strip()
                    # Extract number from response
                    match = re.search(r'(\d+)', score_text)
                    if match:
                        return float(match.group(1))

        except Exception as e:
            print(f"LLM scoring error: {e}")

        return 50.0  # Default fallback

    async def extract_segments(self, content: str) -> list[dict]:
        """
        Extract high-value segments for short-form videos.

        Identifies:
        - Hooks (attention-grabbing openers)
        - Quotes (memorable statements)
        - Statistics (data points)
        - Insights (key takeaways)
        - CTAs (call-to-actions)
        """
        segments = []

        # Split into paragraphs
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

        # Analyze each paragraph
        for i, para in enumerate(paragraphs):
            word_count = len(para.split())

            # Skip very short or very long paragraphs
            if word_count < 10 or word_count > 150:
                continue

            segment_type = self._classify_segment(para, i, len(paragraphs))
            score = self._score_segment(para, segment_type)

            if score >= 40:  # Only include high-quality segments
                segments.append({
                    "text": para,
                    "segment_type": segment_type,
                    "score": score,
                    "word_count": word_count,
                    "estimated_duration_sec": self._estimate_duration(word_count),
                })

        # Sort by score and return top segments
        segments.sort(key=lambda x: x["score"], reverse=True)

        # Ensure variety of segment types
        return self._diversify_segments(segments[:10])

    def _classify_segment(self, text: str, position: int, total: int) -> str:
        """Classify segment type based on content and position."""
        text_lower = text.lower()

        # Position-based hints
        if position == 0:
            return "hook"

        if position >= total - 2:
            # Check for CTA patterns
            cta_patterns = [
                "subscribe", "follow", "share", "comment",
                "click", "sign up", "join", "download",
                "learn more", "get started", "try", "buy"
            ]
            for pattern in cta_patterns:
                if pattern in text_lower:
                    return "cta"

        # Quote detection
        if text.count('"') >= 2 or text.count("'") >= 2:
            return "quote"

        # Statistic detection
        stat_patterns = [
            r'\d+%', r'\$[\d,]+', r'\d+x',
            r'\d+\s*(million|billion|thousand|times)',
            r'(increased|decreased|grew|dropped)\s+by\s+\d+'
        ]
        for pattern in stat_patterns:
            if re.search(pattern, text_lower):
                return "statistic"

        # Insight detection
        insight_indicators = [
            "the key is", "the secret is", "the truth is",
            "here's what", "the reason", "this means",
            "the takeaway", "the lesson", "importantly",
            "the bottom line", "in other words"
        ]
        for indicator in insight_indicators:
            if indicator in text_lower:
                return "insight"

        return "insight"  # Default

    def _score_segment(self, text: str, segment_type: str) -> float:
        """Score individual segment quality."""
        score = 50.0
        text_lower = text.lower()
        word_count = len(text.split())

        # Optimal length for shorts (15-45 words)
        if 15 <= word_count <= 45:
            score += 15
        elif 45 < word_count <= 80:
            score += 10
        elif word_count > 100:
            score -= 10

        # Segment type bonuses
        type_bonuses = {
            "hook": 15,
            "statistic": 12,
            "quote": 10,
            "insight": 8,
            "cta": 5,
        }
        score += type_bonuses.get(segment_type, 0)

        # Strong opening words
        strong_openers = [
            "here's", "this is", "the truth", "nobody",
            "everyone", "stop", "wait", "listen",
            "imagine", "picture this", "what if"
        ]
        for opener in strong_openers:
            if text_lower.startswith(opener):
                score += 10
                break

        # Emotional intensity
        emotional_words = [
            "amazing", "incredible", "shocking", "surprising",
            "never", "always", "must", "critical", "essential"
        ]
        for word in emotional_words:
            if word in text_lower:
                score += 3

        # Numbers boost
        if re.search(r'\d+', text):
            score += 5

        # Question (engagement)
        if "?" in text:
            score += 5

        # Contrast words (creates tension)
        contrast_words = ["but", "however", "yet", "instead", "actually"]
        for word in contrast_words:
            if f" {word} " in text_lower:
                score += 3

        return min(100, score)

    def _estimate_duration(self, word_count: int) -> int:
        """Estimate speaking duration in seconds (150 WPM average)."""
        return max(5, int(word_count / 2.5))

    def _diversify_segments(self, segments: list[dict]) -> list[dict]:
        """Ensure variety in segment types."""
        if len(segments) <= 3:
            return segments

        result = []
        type_counts = {}

        for segment in segments:
            seg_type = segment["segment_type"]
            count = type_counts.get(seg_type, 0)

            # Limit each type to 3
            if count < 3:
                result.append(segment)
                type_counts[seg_type] = count + 1

            if len(result) >= 8:
                break

        return result
