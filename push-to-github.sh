#!/bin/bash
# push-to-github.sh
# Run this script after creating the GitHub repository at https://github.com/new
# Repository name: agent-cloud-memory
# Description: Universal cloud memory layer for AI agents - sync memories, sessions, config and skills across frameworks
# Public/Private: your choice
# DO NOT initialize with README, .gitignore, or license (we have our own)

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  agent-cloud-memory - GitHub Push Helper                     ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ] || [ ! -d "agent_cloud_memory" ]; then
    echo -e "${RED}Error: Run this from the agent-cloud-memory root directory${NC}"
    exit 1
fi

# Get GitHub username
echo -e "${YELLOW}Enter your GitHub username:${NC}"
read -r GH_USERNAME

if [ -z "$GH_USERNAME" ]; then
    echo -e "${RED}Error: Username required${NC}"
    exit 1
fi

REPO_NAME="agent-cloud-memory"
REPO_URL="https://github.com/${GH_USERNAME}/${REPO_NAME}.git"

echo ""
echo -e "${BLUE}Repository: ${GH_USERNAME}/${REPO_NAME}${NC}"
echo -e "${BLUE}URL: ${REPO_URL}${NC}"
echo ""

# Check if remote already exists
if git remote get-url origin >/dev/null 2>&1; then
    echo -e "${YELLOW}Remote 'origin' already exists. Updating...${NC}"
    git remote set-url origin "$REPO_URL"
else
    echo -e "${GREEN}Adding remote 'origin'...${NC}"
    git remote add origin "$REPO_URL"
fi

echo ""
echo -e "${YELLOW}Before pushing, make sure you have created the repo at:${NC}"
echo -e "  ${BLUE}https://github.com/new${NC}"
echo ""
echo -e "${YELLOW}Repository settings:${NC}"
echo "  - Name: ${REPO_NAME}"
echo "  - Description: Universal cloud memory layer for AI agents"
echo "  - Public or Private: your choice"
echo "  - DO NOT check: Add README, .gitignore, or license"
echo ""
echo -e "${YELLOW}Press Enter when ready to push...${NC}"
read -r

echo ""
echo -e "${GREEN}Pushing to GitHub...${NC}"
git push -u origin main

echo ""
echo -e "${GREEN}✅ Push complete!${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. Go to: https://github.com/${GH_USERNAME}/${REPO_NAME}"
echo "  2. Add topics: ai-agent, memory, postgresql, sync, cloud, hermes, openclaw, claude-code, codex"
echo "  3. Enable GitHub Actions (Actions tab → I understand my workflows, go ahead and enable them)"
echo "  4. For PyPI publishing, add PYPI_API_TOKEN to Settings → Secrets and variables → Actions"
echo "  5. Create a release tag to trigger publishing:"
echo "     git tag v0.1.0 && git push origin v0.1.0"
echo ""
echo -e "${BLUE}Badges for README (update the 'yourusername' in badge URLs):${NC}"
echo "  - PyPI: [![PyPI](https://img.shields.io/pypi/v/agent-cloud-memory?style=for-the-badge&logo=pypi)](https://pypi.org/project/agent-cloud-memory/)"
echo "  - GitHub Actions: [![Tests](https://img.shields.io/github/actions/workflow/status/${GH_USERNAME}/${REPO_NAME}/test.yml?style=for-the-badge)](https://github.com/${GH_USERNAME}/${REPO_NAME}/actions)"