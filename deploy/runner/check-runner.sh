#!/bin/bash
# Check health of the self-hosted GitHub Actions runner

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

RUNNER_SERVICE="actions.runner.Xveyn-BaluHost.baluhost-nas.service"
RUNNER_DIR="/opt/actions-runner"

echo "BaluHost Runner Health Check"
echo "============================"
echo ""

# Check runner service
echo -n "Runner service: "
if systemctl is-active "$RUNNER_SERVICE" &>/dev/null; then
    echo -e "${GREEN}running${NC}"
else
    STATUS=$(systemctl is-active "$RUNNER_SERVICE" 2>/dev/null || echo "not found")
    echo -e "${RED}$STATUS${NC}"
fi

# Check runner directory
echo -n "Runner directory: "
if [[ -d "$RUNNER_DIR" ]]; then
    echo -e "${GREEN}$RUNNER_DIR${NC}"
else
    echo -e "${RED}not found${NC}"
fi

# Check connectivity
echo -n "GitHub connectivity: "
if curl -sf --max-time 5 https://github.com > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

# Check deploy prerequisites
echo ""
echo "Deploy Prerequisites"
echo "--------------------"

for cmd in git python3 node npm pg_dump pg_isready nginx; do
    echo -n "$cmd: "
    if command -v "$cmd" &>/dev/null; then
        VERSION=$("$cmd" --version 2>&1 | head -1 || echo "installed")
        echo -e "${GREEN}$VERSION${NC}"
    else
        echo -e "${RED}not found${NC}"
    fi
done

# Check BaluHost services
echo ""
echo "BaluHost Services"
echo "-----------------"

for svc in baluhost-backend baluhost-scheduler baluhost-monitoring baluhost-webdav nginx postgresql; do
    echo -n "$svc: "
    STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "not found")
    if [[ "$STATUS" == "active" ]]; then
        echo -e "${GREEN}$STATUS${NC}"
    elif [[ "$STATUS" == "not found" ]]; then
        echo -e "${YELLOW}$STATUS${NC}"
    else
        echo -e "${RED}$STATUS${NC}"
    fi
done

# Check disk space
echo ""
echo -n "Disk space (/opt): "
AVAIL=$(df -h /opt 2>/dev/null | awk 'NR==2{print $4}' || echo "?")
echo "$AVAIL available"

# Check last deploy
echo ""
echo -n "Last deploy: "
DEPLOY_STATE="/opt/baluhost/.deploy-state"
if [[ -f "$DEPLOY_STATE" ]]; then
    DEPLOYED_AT=$(python3 -c "import json; print(json.load(open('$DEPLOY_STATE'))['deployed_at'])" 2>/dev/null || echo "unknown")
    COMMIT=$(python3 -c "import json; print(json.load(open('$DEPLOY_STATE'))['current_commit'][:8])" 2>/dev/null || echo "unknown")
    echo "$DEPLOYED_AT (commit: $COMMIT)"
else
    echo -e "${YELLOW}no deploy state found${NC}"
fi
