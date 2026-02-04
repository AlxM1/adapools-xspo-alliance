#!/bin/bash
# ============================================================
# Newsletter Video Pipeline - Quick Test Script
# ============================================================
# This script tests the entire pipeline with sample content.
# ============================================================

set -e

echo "========================================================"
echo "Newsletter Video Pipeline - Quick Test"
echo "========================================================"

API_URL="${API_URL:-http://localhost:8000}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ============================================================
# 1. Health Check
# ============================================================
echo -e "\n${GREEN}[1/5] Checking system health...${NC}"

HEALTH=$(curl -s "$API_URL/health")
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"

STATUS=$(echo "$HEALTH" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "unknown")

if [ "$STATUS" != "healthy" ] && [ "$STATUS" != "degraded" ]; then
    echo -e "${RED}System is not healthy. Please check the services.${NC}"
    exit 1
fi

echo -e "${GREEN}System status: $STATUS${NC}"

# ============================================================
# 2. Check Voices
# ============================================================
echo -e "\n${GREEN}[2/5] Checking available voices...${NC}"

VOICES=$(curl -s "$API_URL/voices")
VOICE_COUNT=$(echo "$VOICES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('total_count', 0))" 2>/dev/null || echo "0")

echo "Available voices: $VOICE_COUNT"

if [ "$VOICE_COUNT" -eq "0" ]; then
    echo -e "${YELLOW}No voices found. Please create a voice clone first.${NC}"
    echo "Use: curl -X POST http://GPU_HOST:5002/voices/clone -F 'audio_files=@your_voice.wav' -F 'name=MyVoice'"
fi

# ============================================================
# 3. Check Avatars
# ============================================================
echo -e "\n${GREEN}[3/5] Checking available avatars...${NC}"

AVATARS=$(curl -s "$API_URL/avatars")
AVATAR_COUNT=$(echo "$AVATARS" | python3 -c "import sys, json; print(json.load(sys.stdin).get('total_count', 0))" 2>/dev/null || echo "0")

echo "Available avatars: $AVATAR_COUNT"

if [ "$AVATAR_COUNT" -eq "0" ]; then
    echo -e "${YELLOW}No avatars found. Please create an avatar first.${NC}"
    echo "Use: curl -X POST http://GPU_HOST:5003/avatars/create -F 'video_file=@your_video.mp4' -F 'name=MyAvatar'"
fi

# ============================================================
# 4. Test Script Generation
# ============================================================
echo -e "\n${GREEN}[4/5] Testing script generation...${NC}"

SAMPLE_NEWSLETTER="Welcome to this week's newsletter!

Today we're excited to share some amazing updates with you. Our team has been working hard on new features that will make your experience even better.

Key highlights:
1. Improved performance by 50%
2. New dashboard design
3. Enhanced security features

We can't wait for you to try these out. Stay tuned for more updates next week!

Best regards,
The Team"

echo "Generating script from sample newsletter..."

SCRIPT_RESULT=$(curl -s -X POST "$API_URL/quick/script" \
    --data-urlencode "content=$SAMPLE_NEWSLETTER" \
    --data-urlencode "title=Weekly Update" \
    --data-urlencode "tone=professional")

if echo "$SCRIPT_RESULT" | grep -q "long_form\|short_form"; then
    echo -e "${GREEN}Script generation successful!${NC}"
    echo "$SCRIPT_RESULT" | python3 -m json.tool 2>/dev/null | head -50
else
    echo -e "${YELLOW}Script generation returned:${NC}"
    echo "$SCRIPT_RESULT"
fi

# ============================================================
# 5. Full Pipeline Test (Optional)
# ============================================================
echo -e "\n${GREEN}[5/5] Full pipeline test...${NC}"

if [ "$VOICE_COUNT" -gt "0" ] && [ "$AVATAR_COUNT" -gt "0" ]; then
    read -p "Run full pipeline test? This will generate a video. (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Starting full pipeline..."

        PIPELINE_RESULT=$(curl -s -X POST "$API_URL/pipeline" \
            -H "Content-Type: application/json" \
            -d "{
                \"newsletter_content\": \"$SAMPLE_NEWSLETTER\",
                \"newsletter_title\": \"Test Newsletter\",
                \"generate_long_form\": false,
                \"generate_shorts\": true,
                \"shorts_count\": 1,
                \"target_platforms\": [\"youtube\"],
                \"auto_publish\": false
            }")

        echo "$PIPELINE_RESULT" | python3 -m json.tool 2>/dev/null || echo "$PIPELINE_RESULT"
    fi
else
    echo -e "${YELLOW}Skipping full pipeline test (no voice or avatar available)${NC}"
fi

# ============================================================
# Summary
# ============================================================
echo -e "\n${GREEN}========================================================"
echo "Test Complete!"
echo "========================================================${NC}"
echo ""
echo "API Documentation: $API_URL/docs"
echo ""
echo "Next steps:"
echo "  1. Create a voice clone with your audio samples"
echo "  2. Create an avatar from a video of yourself"
echo "  3. Connect your social media accounts"
echo "  4. Run the full pipeline with your newsletter content"
