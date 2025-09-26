# 🧪 CI/CD Pipeline Testing Guide

## ⚠️ Security Notice
Never share real credentials in conversations or commit them to repositories.

## 🔧 Safe Testing Steps

### 1. Configure GitHub Secrets Safely
Go to your GitHub repository → Settings → Secrets and Variables → Actions:

```
DOCKER_USERNAME: Roi12345
DOCKER_PASSWORD: [Your Docker Hub access token - NOT password]
```

**Important**: Use a Docker Hub access token, not your password:
1. Go to https://hub.docker.com/settings/security
2. Click "New Access Token"
3. Name it "github-actions"
4. Copy the generated token
5. Use this token as DOCKER_PASSWORD

### 2. Update Repository URLs
Run the setup script to configure your repository:
```bash
./setup-pipeline.sh
```
This will update the Dockerfile and workflows with your actual GitHub repository URL.

### 3. Test the Pipeline
```bash
# Make a small change to trigger the pipeline
echo "# Pipeline test" >> README.md

# Commit and push
git add .
git commit -m "Test CI/CD pipeline

- Test automatic Docker builds
- Verify version incrementing
- Check Podman artifact generation

🤖 Generated with [Claude Code](https://claude.ai/code)"

git push origin main
```

### 4. Monitor the Build
1. Go to your GitHub repository
2. Click the "Actions" tab
3. Watch the workflows run:
   - ✅ Build and Push Docker Image
   - ✅ Build Local Podman Images
   - ✅ Test and Validate

### 5. Verify Results
After successful build:
- **Docker Hub**: Check https://hub.docker.com/r/roi12345/vlan-manager
- **Artifacts**: Download Podman images from Actions tab
- **Version**: Verify auto-incremented version tags

## 🐳 Expected Output
- Docker images published to: `roi12345/vlan-manager:v1.0.0`, `roi12345/vlan-manager:latest`
- Podman artifacts available for download
- All tests passing
- Security scans completed

## 🔍 Troubleshooting
- Check Actions logs for detailed error messages
- Verify Docker Hub token has write permissions
- Ensure repository URL is correctly set in workflows