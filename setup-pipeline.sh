#!/bin/bash

# VLAN Manager CI/CD Pipeline Setup Script
# This script helps configure the GitHub Actions pipeline

set -e

echo "🚀 VLAN Manager CI/CD Pipeline Setup"
echo "===================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}❌ Error: Not in a git repository${NC}"
    echo "Please run this script from your VLAN Manager project directory"
    exit 1
fi

echo -e "${BLUE}📋 Checking prerequisites...${NC}"

# Check for required tools
command -v git >/dev/null 2>&1 || { echo -e "${RED}❌ git is required but not installed${NC}"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo -e "${RED}❌ curl is required but not installed${NC}"; exit 1; }

echo -e "${GREEN}✅ Prerequisites check passed${NC}"

# Check if GitHub remote exists
if ! git remote get-url origin >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  No GitHub remote found${NC}"
    read -p "Enter your GitHub repository URL (e.g., https://github.com/username/vlan-manager.git): " REPO_URL
    
    if [[ -n "$REPO_URL" ]]; then
        git remote add origin "$REPO_URL"
        echo -e "${GREEN}✅ GitHub remote added${NC}"
    else
        echo -e "${RED}❌ Repository URL is required${NC}"
        exit 1
    fi
fi

REPO_URL=$(git remote get-url origin)
echo -e "${BLUE}📍 Repository: ${REPO_URL}${NC}"

# Extract username and repo name from URL
if [[ $REPO_URL =~ github\.com[:/]([^/]+)/([^/]+)(\.git)?$ ]]; then
    USERNAME="${BASH_REMATCH[1]}"
    REPONAME="${BASH_REMATCH[2]%.git}"
    echo -e "${BLUE}👤 GitHub Username: ${USERNAME}${NC}"
    echo -e "${BLUE}📦 Repository Name: ${REPONAME}${NC}"
else
    echo -e "${RED}❌ Could not parse GitHub URL${NC}"
    exit 1
fi

# Update Dockerfile labels with correct repository
echo -e "${BLUE}🔧 Updating Dockerfile with repository information...${NC}"
if [[ -f "Dockerfile" ]]; then
    sed -i.bak "s|https://github.com/yourrepo/vlan-manager|https://github.com/${USERNAME}/${REPONAME}|g" Dockerfile
    echo -e "${GREEN}✅ Dockerfile updated${NC}"
else
    echo -e "${YELLOW}⚠️  Dockerfile not found${NC}"
fi

# Update workflow files with username
echo -e "${BLUE}🔧 Updating workflow files...${NC}"
if [[ -f ".github/workflows/docker-build.yml" ]]; then
    # Note: The workflow uses secrets.DOCKER_USERNAME, so no direct replacement needed
    echo -e "${GREEN}✅ Workflow files are ready${NC}"
else
    echo -e "${RED}❌ Workflow files not found. Make sure they exist in .github/workflows/${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}🔐 REQUIRED: GitHub Secrets Configuration${NC}"
echo "You need to configure the following secrets in your GitHub repository:"
echo ""
echo "1. Go to: https://github.com/${USERNAME}/${REPONAME}/settings/secrets/actions"
echo "2. Add these secrets:"
echo "   - DOCKER_USERNAME: Your Docker Hub username"
echo "   - DOCKER_PASSWORD: Your Docker Hub access token"
echo ""
echo -e "${BLUE}💡 To create a Docker Hub access token:${NC}"
echo "1. Go to https://hub.docker.com/settings/security"
echo "2. Click 'New Access Token'"
echo "3. Give it a name (e.g., 'github-actions')"
echo "4. Select 'Read, Write, Delete' permissions"
echo "5. Copy the generated token"
echo ""

read -p "Have you configured the GitHub secrets? (y/N): " SECRETS_CONFIGURED

if [[ $SECRETS_CONFIGURED =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}✅ Secrets configured${NC}"
else
    echo -e "${YELLOW}⚠️  Please configure secrets before pushing to GitHub${NC}"
fi

# Check if main branch exists
CURRENT_BRANCH=$(git branch --show-current)
echo -e "${BLUE}🌿 Current branch: ${CURRENT_BRANCH}${NC}"

if [[ "$CURRENT_BRANCH" != "main" ]]; then
    read -p "Switch to main branch? (y/N): " SWITCH_MAIN
    if [[ $SWITCH_MAIN =~ ^[Yy]$ ]]; then
        git checkout -b main 2>/dev/null || git checkout main
        echo -e "${GREEN}✅ Switched to main branch${NC}"
    fi
fi

# Offer to commit and push
echo ""
echo -e "${BLUE}📤 Ready to push pipeline configuration${NC}"
read -p "Commit and push the pipeline files to GitHub? (y/N): " PUSH_FILES

if [[ $PUSH_FILES =~ ^[Yy]$ ]]; then
    # Stage pipeline files
    git add .github/workflows/ Dockerfile CI-CD-README.md setup-pipeline.sh
    
    # Check if there are changes to commit
    if git diff --cached --quiet; then
        echo -e "${YELLOW}⚠️  No changes to commit${NC}"
    else
        git commit -m "Add GitHub Actions CI/CD pipeline

- Automated Docker builds with version management
- Local Podman image generation
- Multi-architecture support
- Security scanning with Trivy
- Test and validation workflows

🤖 Generated with [Claude Code](https://claude.ai/code)"
        
        git push -u origin "$(git branch --show-current)"
        echo -e "${GREEN}✅ Pipeline files pushed to GitHub${NC}"
        
        echo ""
        echo -e "${GREEN}🎉 Pipeline setup complete!${NC}"
        echo ""
        echo "Next steps:"
        echo "1. Check GitHub Actions: https://github.com/${USERNAME}/${REPONAME}/actions"
        echo "2. View your first build run"
        echo "3. Check Docker Hub for published images"
        echo ""
        echo "Your first version will be v1.0.0"
    fi
else
    echo -e "${YELLOW}⚠️  Files not pushed. Run 'git add . && git commit && git push' when ready${NC}"
fi

echo ""
echo -e "${BLUE}📚 Documentation${NC}"
echo "- Pipeline documentation: CI-CD-README.md"
echo "- GitHub Actions: https://github.com/${USERNAME}/${REPONAME}/actions"
echo "- Docker Hub: https://hub.docker.com/r/${USERNAME}/vlan-manager (after first build)"
echo ""
echo -e "${GREEN}✅ Setup complete!${NC}"

# Show next steps
echo ""
echo -e "${YELLOW}🔄 Workflow Triggers:${NC}"
echo "- Push to main → Auto-increment version build"
echo "- Push to develop → Beta version build"  
echo "- Create release → Multi-registry publish"
echo "- Pull request → Test and validate"
echo ""
echo "Happy coding! 🚀"