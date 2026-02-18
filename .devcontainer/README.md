# Dev Container Setup

This directory contains the development container configuration for the Maverick project, based on the [python-agentic](https://github.com/get2knowio/devcontainer-templates/tree/main/src/python-agentic) devcontainer template.

## What's Included

### Base Image
- **Ubuntu** (`mcr.microsoft.com/devcontainers/base:ubuntu`)
- Non-root user (`vscode`) for security

### Platform

| Feature | Description |
|---------|-------------|
| [Docker-in-Docker](https://github.com/devcontainers/features/tree/main/src/docker-in-docker) | Docker CLI and daemon inside the container |
| [AWS CLI](https://github.com/devcontainers/features/tree/main/src/aws-cli) | Amazon Web Services command-line interface |
| [GitHub CLI](https://github.com/devcontainers/features/tree/main/src/github-cli) | GitHub's official CLI (`gh`) |
| [jq-likes](https://github.com/eitsupi/devcontainer-features/tree/main/src/jq-likes) | jq and similar JSON/YAML/TOML processors |
| [Starship](https://github.com/devcontainers-extra/features/tree/main/src/starship) | Cross-shell prompt |

### Languages

| Feature | Description |
|---------|-------------|
| [Python](https://github.com/devcontainers/features/tree/main/src/python) | Python runtime |
| [Node.js](https://github.com/devcontainers/features/tree/main/src/node) | Node.js 22 runtime |

### Development Tools ([get2knowio/devcontainer-features](https://github.com/get2knowio/devcontainer-features))

| Feature | Description |
|---------|-------------|
| [AI CLI Tools](https://github.com/get2knowio/devcontainer-features/tree/main/src/ai-clis) | Claude Code, Gemini CLI, OpenAI Codex, GitHub Copilot, OpenCode, CodeRabbit, Beads, Specify CLI |
| [Modern CLI Tools](https://github.com/get2knowio/devcontainer-features/tree/main/src/modern-cli-tools) | bat, ripgrep, fd, fzf, eza, zoxide, neovim, tmux, lazygit, ast-grep, jujutsu |
| [Python Tools](https://github.com/get2knowio/devcontainer-features/tree/main/src/python-tools) | uv, Poetry, ruff, mypy |
| [GitHub Actions Tools](https://github.com/get2knowio/devcontainer-features/tree/main/src/github-actions-tools) | act (local runner), actionlint (workflow linter) |

### VS Code Extensions
- Python + Pylance
- Ruff (linter/formatter, set as default)
- GitHub Copilot & Copilot Chat

### Maverick-Specific Configuration
- **Mounts**: `~/.claude`, `~/.config/gh`, and `~/projects/sample-maverick-project` bind-mounted into the container
- **Environment**: `GH_PAGER` disabled, `CODEX_HOME` set to workspace
- **ZSH** as default terminal shell

## Getting Started

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- [VS Code](https://code.visualstudio.com/)
- [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

### Opening the Project

1. Open the project folder in VS Code
2. When prompted, click "Reopen in Container"
   - Or use Command Palette (F1) → "Dev Containers: Reopen in Container"
3. Wait for the container to build (first time takes longer as features are installed)
4. Run `uv sync` to install Python dependencies

### Manual Setup

If you need to rebuild the container:

```bash
# From VS Code Command Palette (F1)
Dev Containers: Rebuild Container
```

## Customizing Features

Every feature can be customized by passing options in `devcontainer.json`. For example, to only install specific AI CLIs:

```jsonc
{
  "features": {
    "ghcr.io/get2knowio/devcontainer-features/ai-clis:1": {
      "install": "claudeCode,geminiCli"
    }
  }
}
```

See the [python-agentic template README](https://github.com/get2knowio/devcontainer-templates/tree/main/src/python-agentic) for full feature options.

## Troubleshooting

### Container Won't Start
- Check Docker Desktop is running
- Try rebuilding: F1 → "Dev Containers: Rebuild Container"

### Permission Issues
- The container runs as user `vscode` (UID 1000)
- Ensure your local files are accessible

### Mount Failures
- Ensure `~/.claude`, `~/.config/gh`, and `~/projects/sample-maverick-project` exist on your host
- Create missing directories before opening the container

### Slow Performance
- Check Docker resource allocation in Docker Desktop settings
- To speed up container builds, disable unneeded AI CLIs via feature options
