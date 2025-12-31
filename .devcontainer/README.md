# Dev Container Setup

This directory contains the development container configuration for the Maverick project.

## What's Included

### Base Image
- **Node.js 20 LTS** (Debian Bookworm-based)
- Non-root user (`node`) for security

### Tools & Features
- **Git** (latest version with PPA)
- **GitHub CLI** (`gh`) for GitHub operations
- **Common utilities** (zsh, oh-my-zsh, curl, vim, jq, etc.)
- **npm** global packages directory configured for non-root user

### VS Code Extensions
- ESLint
- Prettier (set as default formatter)
- Node.js debugging support
- GitHub Copilot & Copilot Chat

### Configuration
- **Auto-formatting** on save
- **ESLint** auto-fix on save
- **Environment**: Development mode
- **Timezone**: UTC
- **Bash history** persisted across container rebuilds

## Getting Started

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- [VS Code](https://code.visualstudio.com/)
- [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

### Opening the Project

1. Open the project folder in VS Code
2. When prompted, click "Reopen in Container"
   - Or use Command Palette (F1) → "Dev Containers: Reopen in Container"
3. Wait for the container to build (first time only)
4. Dependencies will be installed automatically via `npm install`

### Manual Setup

If you need to rebuild the container:

```bash
# From VS Code Command Palette (F1)
Dev Containers: Rebuild Container
```

### Installing External CLI Tools

This project depends on external CLI tools that need to be installed separately:

```bash
# Install opencode (if available)
npm install -g @opencode/cli

# Install coderabbit (if available)
npm install -g @coderabbit/cli
```

## Customization

### Adding Extensions

Edit `.devcontainer/devcontainer.json` and add extension IDs to the `extensions` array.

### Installing Additional Tools

Add additional features to the `features` section in `devcontainer.json`. Browse available features at [containers.dev/features](https://containers.dev/features).

### Changing Node Version

Update the base image in `devcontainer.json`:

```json
"image": "mcr.microsoft.com/devcontainers/javascript-node:1-22-bookworm"
```

Available versions: 18, 20, 22, 24 (current LTS), 25 (current release)

## Troubleshooting

### Container Won't Start
- Check Docker Desktop is running
- Try rebuilding: F1 → "Dev Containers: Rebuild Container"

### Permission Issues
- The container runs as user `node` (UID 1000)
- Ensure your local files are accessible

### Slow Performance
- Check Docker resource allocation in Docker Desktop settings
- Consider adjusting mount consistency in `devcontainer.json`

## Architecture

```
.devcontainer/
├── devcontainer.json    # Main configuration
└── README.md           # This file
```

The setup uses:
- **devcontainer.json**: Complete configuration including base image, VS Code settings, extensions, and features
- **Features**: Declarative installation of common development tools (Git, GitHub CLI, zsh, etc.)
- **Base Image**: Official Microsoft Node.js devcontainer image with all necessary tools pre-installed
