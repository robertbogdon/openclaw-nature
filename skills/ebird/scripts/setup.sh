#!/usr/bin/env bash
# setup.sh — eBird Skill Setup
# Run this once to configure the eBird API key for this agent.
#
# Usage: source setup.sh
#   or:  ./setup.sh (prints instructions)

echo "=== eBird Skill Setup ==="
echo ""
echo "To use the eBird skill, you need an API key from:"
echo "  https://ebird.org/api/keygen"
echo ""
echo "Once you have your key, set it in one of these ways:"
echo ""
echo "1. In agent env (recommended for testing):"
echo "   export EBIRD_API_KEY=\"your-key-here\""
echo ""
echo "2. In OpenClaw config (openclaw.json):"
echo '   "skills": {'
echo '     "entries": {'
echo '       "ebird": {'
echo '         "enabled": true,'
echo '         "env": {'
echo '           "EBIRD_API_KEY": "your-key-here"'
echo '         }'
echo '       }'
echo '     }'
echo '   }'
echo ""
echo "3. In the agent's env.env file:"
echo "   Echo EBIRD_API_KEY=your-key-here >> /home/openclaw/.openclaw/agents/zookeeper/agent/env.env"
echo ""
echo "Verify the key works:"
echo '   curl -s -H "X-eBird-ApiToken: $EBIRD_API_KEY" \'
echo '     "https://api.ebird.org/v2/ref/taxonomy/versions" | jq .'
