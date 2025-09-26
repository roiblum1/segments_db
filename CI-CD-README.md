# 🚀 CI/CD Pipeline Documentation

This document describes the automated CI/CD pipeline setup for the VLAN Manager project.

## 📋 Overview

The pipeline automatically builds Docker images with incremental version numbers for each push and provides both Docker Hub distribution and local Podman image archives.

## 🔄 Workflows

### 1. Docker Build Pipeline (`.github/workflows/docker-build.yml`)

**Triggers:**
- Push to `main` or `develop` branches
- Pull requests to `main`
- Release publications

**Features:**
- ✅ Automatic semantic versioning
- ✅ Multi-architecture builds (amd64, arm64)
- ✅ Docker Hub publishing
- ✅ Automatic Git tagging
- ✅ Build caching
- ✅ Security scanning with Trivy

**Version Strategy:**
- **Main branch:** Auto-increment patch version (v1.0.0 → v1.0.1 → v1.0.2)
- **Develop branch:** Beta versions (v1.0.1-beta.1)
- **Feature branches:** `branch-feature-name-{commit}`
- **Releases:** Use release tag version

### 2. Local Podman Build (`.github/workflows/local-build.yml`)

**Triggers:**
- Push to `main` or `develop` branches
- Manual workflow dispatch

**Features:**
- ✅ Builds images with Podman
- ✅ Saves images as compressed tar archives
- ✅ Creates deployment scripts
- ✅ Uploads as GitHub Actions artifacts
- ✅ Ready-to-deploy packages

### 3. Test & Validation (`.github/workflows/test.yml`)

**Triggers:**
- Push to any branch
- Pull requests

**Features:**
- ✅ Python linting (flake8, black, isort)
- ✅ Type checking (mypy)
- ✅ Unit tests (pytest)
- ✅ Docker image testing
- ✅ Coverage reporting

### 4. Release Pipeline (`.github/workflows/release.yml`)

**Triggers:**
- GitHub release publication

**Features:**
- ✅ Multi-registry publishing (Docker Hub + GHCR)
- ✅ Release asset creation
- ✅ Deployment package generation
- ✅ Automatic release notes enhancement

## 🔧 Setup Instructions

### Prerequisites

1. **GitHub Secrets** (Repository Settings → Secrets and Variables → Actions):
   ```bash
   DOCKER_USERNAME=your-dockerhub-username
   DOCKER_PASSWORD=your-dockerhub-token-or-password
   ```

2. **Docker Hub Account:**
   - Create account at https://hub.docker.com
   - Generate access token in Account Settings

### Repository Setup

1. **Clone and push to GitHub:**
   ```bash
   git remote add origin https://github.com/yourusername/vlan-manager.git
   git push -u origin main
   ```

2. **Configure branch protection** (optional):
   - Go to Settings → Branches
   - Add rule for `main` branch
   - Require status checks to pass

## 📦 Using the Pipeline

### Automatic Builds

1. **Development workflow:**
   ```bash
   # Work on feature branch
   git checkout -b feature/new-functionality
   git commit -am "Add new feature"
   git push origin feature/new-functionality
   
   # Create PR → triggers test workflow
   # Merge to main → triggers build workflow with version increment
   ```

2. **Release workflow:**
   ```bash
   # Create release through GitHub UI or CLI
   gh release create v2.6.0 --title "Version 2.6.0" --notes "Release notes"
   # → triggers release workflow with multi-registry publishing
   ```

### Manual Builds

1. **Trigger local build:**
   - Go to Actions tab → "Build Local Podman Images"
   - Click "Run workflow"
   - Optionally specify custom version

2. **Download artifacts:**
   - Download from Actions run
   - Extract podman-images directory
   - Run `./deploy.sh`

## 🐳 Image Distribution

### Docker Hub Images

**Public images published to:**
- `your-username/vlan-manager:latest` (main branch)
- `your-username/vlan-manager:develop` (develop branch)
- `your-username/vlan-manager:v1.0.0` (version tags)

**Usage:**
```bash
docker pull your-username/vlan-manager:latest
docker run -d -p 8000:8000 --name vlan-manager your-username/vlan-manager:latest
```

### Podman Archive Images

**Artifacts include:**
- `vlan-manager-{version}.tar.gz` - Compressed image
- `deploy.sh` - Automated deployment script
- `manifest.json` - Image metadata
- `README.md` - Deployment instructions

**Usage:**
```bash
# Download artifact from GitHub Actions
cd podman-images
./deploy.sh
```

## 🔍 Version Management

### Automatic Versioning

The pipeline automatically manages versions:

1. **First push to main:** Creates `v1.0.0`
2. **Subsequent pushes:** Increments patch version (`v1.0.1`, `v1.0.2`, etc.)
3. **Develop branch:** Creates beta versions (`v1.0.1-beta.1`)

### Manual Version Control

Override automatic versioning:

```bash
# Create specific version tag
git tag v2.0.0
git push origin v2.0.0

# Or use GitHub CLI
gh release create v2.0.0 --title "Major Release 2.0.0"
```

## 🛡️ Security & Quality

### Automated Checks

- **Trivy vulnerability scanning** on all built images
- **SARIF upload** to GitHub Security tab
- **Multi-architecture builds** for broad compatibility
- **Health check validation** during testing

### Best Practices

- Images built from minimal Python slim base
- Non-root user option available
- Comprehensive health checks
- Proper metadata labeling
- Build argument injection for versioning

## 📊 Monitoring & Status

### Build Status

Add badges to your README:

```markdown
![Docker Build](https://github.com/yourusername/vlan-manager/workflows/Build%20and%20Push%20Docker%20Image/badge.svg)
![Tests](https://github.com/yourusername/vlan-manager/workflows/Test%20and%20Validate/badge.svg)
```

### Checking Builds

- **GitHub Actions tab:** View all workflow runs
- **Docker Hub:** Check published images
- **Releases page:** Download deployment packages
- **Security tab:** Review vulnerability scans

## 🔄 Customization

### Modifying Version Strategy

Edit `.github/workflows/docker-build.yml`:

```yaml
# Change version increment logic
PATCH=$((PATCH + 1))  # Patch increment
MINOR=$((MINOR + 1))  # Minor increment
MAJOR=$((MAJOR + 1))  # Major increment
```

### Adding New Registries

Edit workflows to add registries:

```yaml
- name: Log in to Additional Registry
  uses: docker/login-action@v3
  with:
    registry: your-registry.com
    username: ${{ secrets.REGISTRY_USERNAME }}
    password: ${{ secrets.REGISTRY_PASSWORD }}
```

### Custom Build Arguments

Add build arguments in workflows:

```yaml
build-args: |
  VERSION=${{ steps.meta.outputs.version }}
  CUSTOM_ARG=value
```

## 🆘 Troubleshooting

### Common Issues

1. **Docker Hub authentication fails:**
   - Check `DOCKER_USERNAME` and `DOCKER_PASSWORD` secrets
   - Verify Docker Hub token has write permissions

2. **Version conflicts:**
   - Check for existing tags: `git tag -l`
   - Delete problematic tags: `git tag -d v1.0.0`

3. **Build failures:**
   - Check Actions logs for specific errors
   - Verify Dockerfile syntax
   - Test builds locally first

### Getting Help

- Check GitHub Actions logs for detailed error messages
- Test Docker builds locally before pushing
- Verify all secrets are properly configured
- Review workflow syntax with GitHub's workflow validator

## 📈 Future Enhancements

Potential improvements:

- **Helm chart generation** for Kubernetes deployments
- **Integration testing** with test databases
- **Performance benchmarking** in CI
- **Multi-environment deployments**
- **Slack/Teams notifications**
- **Dependency vulnerability monitoring**