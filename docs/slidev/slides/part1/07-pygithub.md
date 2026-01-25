````markdown
---
layout: section
class: text-center
---

# 7. PyGithub - GitHub API Integration

<div class="text-lg text-secondary mt-4">
Programmatic GitHub access for AI-powered workflows
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">8 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Rate Limited</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Async-Wrapped</span>
  </div>
</div>

<!--
Section 7 covers PyGithub - the library that powers all GitHub API operations in Maverick.

We'll cover:
1. GitHub API overview and basics
2. PyGithub setup and installation
3. Authentication via gh CLI
4. Working with repositories
5. Issues API operations
6. Pull Requests API operations
7. Rate limiting with aiolimiter
8. Async wrapper patterns for TUI responsiveness
-->

---

## layout: two-cols

# 7.1 GitHub API Overview

<div class="pr-4">

**The GitHub REST API** provides programmatic access to all GitHub features

<div v-click class="mt-4">

## Key Concepts

<div class="space-y-3 text-sm mt-3">

<div class="flex items-start gap-2">
  <span class="text-teal font-bold">◆</span>
  <div>
    <strong>REST Architecture</strong>
    <div class="text-muted">JSON request/response, HTTP verbs</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-teal font-bold">◆</span>
  <div>
    <strong>Token Authentication</strong>
    <div class="text-muted">Personal access tokens or OAuth apps</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-teal font-bold">◆</span>
  <div>
    <strong>Rate Limiting</strong>
    <div class="text-muted">5,000 requests/hour for authenticated users</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-teal font-bold">◆</span>
  <div>
    <strong>Pagination</strong>
    <div class="text-muted">Large result sets paginated by default</div>
  </div>
</div>

</div>

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## API Resources

```text
/repos/{owner}/{repo}
├── /issues
│   ├── GET     - List issues
│   ├── POST    - Create issue
│   └── /{number}
│       ├── GET   - Get issue
│       ├── PATCH - Update issue
│       └── /comments
├── /pulls
│   ├── GET     - List PRs
│   ├── POST    - Create PR
│   └── /{number}
│       ├── GET   - Get PR
│       └── /merge
└── /commits
    └── /{sha}/check-runs
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Why PyGithub?</strong> Type-safe Python objects instead of raw JSON dictionaries. Full IDE support and autocompletion.
</div>

</div>

<!--
Before diving into PyGithub, let's understand the GitHub REST API.

**REST Architecture**: The API uses standard HTTP verbs - GET to retrieve, POST to create, PATCH to update, DELETE to remove. All data is JSON.

**Authentication**: You need a token to access the API. Authenticated users get 5,000 requests per hour (vs 60 for unauthenticated).

**Rate Limiting**: This is crucial! If you hit the rate limit, GitHub returns 403 errors. Maverick uses aiolimiter to prevent this.

**Why PyGithub over raw requests?**
1. Type-safe Python objects instead of dictionaries
2. Pagination handled automatically
3. Authentication built-in
4. Error handling with specific exceptions
-->

---

## layout: default

# 7.2 PyGithub Setup

<div class="text-secondary text-sm mb-4">
Installing and configuring PyGithub
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Installation

```bash
# PyGithub is in Maverick's dependencies
uv sync

# Or install directly
pip install PyGithub

# For rate limiting (also included)
pip install aiolimiter
```

</div>

<div v-click class="mt-4">

### Basic Client Creation

```python
from github import Github, Auth

# Create with personal access token
auth = Auth.Token("ghp_xxxxx...")
github = Github(auth=auth)

# Access authenticated user
user = github.get_user()
print(f"Logged in as: {user.login}")

# List your repos
for repo in user.get_repos():
    print(f"  - {repo.full_name}")
```

</div>

</div>

<div>

<div v-click>

### Key Classes

<div class="space-y-2 text-sm">

<div class="p-2 rounded border border-slate-300 dark:border-slate-700">
  <code class="text-teal">Github</code>
  <div class="text-muted text-xs mt-1">Main entry point, holds authentication</div>
</div>

<div class="p-2 rounded border border-slate-300 dark:border-slate-700">
  <code class="text-teal">Repository</code>
  <div class="text-muted text-xs mt-1">Repo info, issues, PRs, commits</div>
</div>

<div class="p-2 rounded border border-slate-300 dark:border-slate-700">
  <code class="text-teal">Issue</code>
  <div class="text-muted text-xs mt-1">Issue details, labels, assignees, comments</div>
</div>

<div class="p-2 rounded border border-slate-300 dark:border-slate-700">
  <code class="text-teal">PullRequest</code>
  <div class="text-muted text-xs mt-1">PR details, reviews, merge, commits</div>
</div>

<div class="p-2 rounded border border-slate-300 dark:border-slate-700">
  <code class="text-teal">GithubException</code>
  <div class="text-muted text-xs mt-1">API errors with status codes</div>
</div>

</div>

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Maverick Rule:</strong> Use <code>maverick.utils.github_client</code> for all GitHub operations. Never create raw <code>Github()</code> instances directly.
</div>

</div>

</div>

<!--
Let's set up PyGithub. It's already included in Maverick's dependencies.

**Basic Usage**: Create a `Github` instance with an auth token. From there, you can access users, repositories, issues, and PRs.

**Key Classes**:
- `Github`: The client itself, holds auth and makes API calls
- `Repository`: Everything about a repo - issues, PRs, commits, branches
- `Issue`: Issue details with methods to comment, update, close
- `PullRequest`: PR details with merge, review, and commit access
- `GithubException`: Raised on API errors, includes HTTP status

**Important**: In Maverick, always use our `GitHubClient` wrapper. It handles authentication via gh CLI and provides async methods.
-->

---

## layout: default

# 7.3 Auth via gh CLI

<div class="text-secondary text-sm mb-4">
Leveraging the GitHub CLI for secure authentication
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Why gh CLI?

<div class="space-y-3 text-sm mt-3">

<div class="flex items-start gap-2">
  <span class="text-teal font-bold">✓</span>
  <div>
    <strong>No Token Management</strong>
    <div class="text-muted">User already authenticated via <code>gh auth login</code></div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-teal font-bold">✓</span>
  <div>
    <strong>Secure Storage</strong>
    <div class="text-muted">Token stored in OS keychain, not config files</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-teal font-bold">✓</span>
  <div>
    <strong>Token Refresh</strong>
    <div class="text-muted">gh handles OAuth token refresh automatically</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-teal font-bold">✓</span>
  <div>
    <strong>Consistent Auth</strong>
    <div class="text-muted">Same credentials as <code>gh pr create</code></div>
  </div>
</div>

</div>

</div>

<div v-click class="mt-4">

### Getting the Token

```python
def get_github_token() -> str:
    """Get GitHub token from gh CLI."""
    result = subprocess.run(
        ["gh", "auth", "token"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return result.stdout.strip()
```

</div>

</div>

<div>

<div v-click>

### Maverick's Implementation

```python {1-4|6-13|15-20|all}
from github import Auth, Github
from maverick.exceptions import (
    GitHubCLINotFoundError, GitHubAuthError
)

def get_github_client() -> Github:
    """Create PyGithub client via gh CLI auth."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        token = result.stdout.strip()
        if not token:
            raise GitHubAuthError()
        return Github(auth=Auth.Token(token))
    except FileNotFoundError:
        raise GitHubCLINotFoundError()
    except subprocess.CalledProcessError:
        raise GitHubAuthError()
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Prerequisite:</strong> Users must run <code>gh auth login</code> before using Maverick. The CLI checks this and provides helpful error messages.
</div>

</div>

</div>

<!--
Maverick uses an elegant approach to authentication - we leverage the gh CLI.

**Why Not Environment Variables?**
- Users have to manage GITHUB_TOKEN themselves
- Tokens end up in shell history, dotfiles, CI logs
- Token rotation is manual

**Why gh CLI?**
1. **No Token Management**: Users already authenticate once with `gh auth login`
2. **Secure Storage**: Token stored in macOS Keychain or Linux secret-service
3. **Token Refresh**: OAuth tokens expire; gh handles refresh
4. **Consistency**: Same auth as `gh pr create`, `gh issue list`

**Error Handling**: We catch specific exceptions:
- `FileNotFoundError`: gh not installed
- `CalledProcessError`: gh not authenticated

This gives users actionable error messages rather than cryptic API failures.
-->

---

## layout: default

# 7.4 Working with Repos

<div class="text-secondary text-sm mb-4">
Repository information and operations
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Getting a Repository

```python
from maverick.utils.github_client import GitHubClient

client = GitHubClient()

# Get repository by full name
repo = await client.get_repo_info("owner/repo-name")

# Repository properties
print(repo.full_name)       # "owner/repo-name"
print(repo.description)     # "A great project"
print(repo.default_branch)  # "main"
print(repo.private)         # False
print(repo.stargazers_count) # 1234
```

</div>

<div v-click class="mt-4">

### Repository Objects

```python
# Direct PyGithub access (internal)
from github import Github

github = get_github_client()
repo = github.get_repo("owner/repo")

# Rich object with methods
print(repo.clone_url)
print(repo.permissions.push)
branches = repo.get_branches()
commits = repo.get_commits()
```

</div>

</div>

<div>

<div v-click>

### Common Operations

```python
# Check if repo exists and accessible
try:
    repo = await client.get_repo_info("owner/repo")
except GitHubError as e:
    if "not found" in str(e).lower():
        print("Repo doesn't exist or no access")

# Get default branch
default = repo.default_branch

# Check permissions
can_push = repo.permissions.push
is_admin = repo.permissions.admin
```

</div>

<div v-click class="mt-4">

### Repository Structure

<div class="text-xs font-mono p-3 bg-slate-100 dark:bg-slate-800 rounded">

```text
Repository
├── .full_name      → "owner/repo"
├── .description    → str | None
├── .default_branch → "main"
├── .private        → bool
├── .permissions
│   ├── .pull       → bool
│   ├── .push       → bool
│   └── .admin      → bool
├── .get_issues()   → PaginatedList[Issue]
├── .get_pulls()    → PaginatedList[PR]
└── .create_issue() → Issue
```

</div>

</div>

</div>

</div>

<!--
Repository is the central object in PyGithub. Everything flows from getting a repo.

**Getting a Repo**: Use `github.get_repo("owner/repo")` with the full name format. This makes a single API call.

**Key Properties**:
- `full_name`: The canonical "owner/repo" format
- `default_branch`: Usually "main" or "master"
- `private`: Is this repo private?
- `permissions`: What can the authenticated user do?

**Permissions Check**: Before attempting operations like push or merge, check permissions. This provides better error messages than letting the API fail.

**Paginated Lists**: Methods like `get_issues()` return `PaginatedList` objects. PyGithub handles pagination automatically - just iterate and it fetches more pages as needed.
-->

---

## layout: two-cols

# 7.5 Issues API

<div class="pr-4">

Creating, listing, and managing issues

<div v-click class="mt-4">

### Listing Issues

```python
client = GitHubClient()

# List open issues
issues = await client.list_issues(
    "owner/repo",
    state="open",
    labels=["bug", "help wanted"],
    limit=30
)

for issue in issues:
    print(f"#{issue.number}: {issue.title}")
    print(f"  Labels: {[l.name for l in issue.labels]}")
    print(f"  Assignees: {[a.login for a in issue.assignees]}")
```

</div>

<div v-click class="mt-4">

### Getting a Single Issue

```python
# Get specific issue by number
issue = await client.get_issue("owner/repo", 42)

print(issue.title)
print(issue.body)          # Markdown content
print(issue.state)         # "open" or "closed"
print(issue.created_at)    # datetime
print(issue.user.login)    # Author
```

</div>

</div>

::right::

<div class="pl-4">

<div v-click>

### Creating Issues

```python
# Create a new issue
issue = await client.create_issue(
    repo_name="owner/repo",
    title="Bug: Login fails with SSO",
    body="""
## Description
Login fails when using SSO provider.

## Steps to Reproduce
1. Click "Login with SSO"
2. Enter credentials
3. Observe error

## Expected Behavior
User should be logged in.
""",
    labels=["bug", "priority:high"]
)

print(f"Created issue #{issue.number}")
```

</div>

<div v-click class="mt-4">

### Adding Comments

```python
# Comment on an issue
await client.add_issue_comment(
    repo_name="owner/repo",
    issue_number=42,
    body="Thanks for reporting! Looking into it."
)
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-xs">
  <strong class="text-teal">Markdown Support:</strong> Issue bodies and comments support full GitHub-Flavored Markdown including task lists, code blocks, and mentions.
</div>

</div>

<!--
The Issues API is one of the most-used GitHub features. Maverick uses it extensively for workflow tracking.

**Listing Issues**: Filter by state (open/closed/all) and labels. The `limit` parameter prevents fetching thousands of issues.

**Getting Issues**: Fetch a single issue by number. Returns full details including body, labels, assignees, and timestamps.

**Creating Issues**: Provide title, body, and optional labels. The body supports full GitHub-Flavored Markdown - use it for structured bug reports and feature requests.

**Commenting**: Add comments to issues for updates. Maverick uses this to post automated status updates during workflow execution.

Note: Issues and PRs share the same numbering system in GitHub. Issue #42 and PR #42 cannot both exist.
-->

---

## layout: two-cols

# 7.6 Pull Requests API

<div class="pr-4">

Creating and managing pull requests

<div v-click class="mt-4">

### Creating a PR

```python
client = GitHubClient()

pr = await client.create_pr(
    repo_name="owner/repo",
    title="feat: add user authentication",
    body="""
## Summary
Implements user authentication with OAuth.

## Changes
- Add OAuth provider configuration
- Implement login/logout endpoints
- Add session management

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing complete
""",
    head="feature/auth",  # Source branch
    base="main",          # Target branch
    draft=False
)

print(f"Created PR #{pr.number}")
print(f"URL: {pr.html_url}")
```

</div>

</div>

::right::

<div class="pl-4">

<div v-click>

### Getting PR Details

```python
# Get PR by number
pr = await client.get_pr("owner/repo", 123)

print(pr.title)
print(pr.state)        # "open", "closed", "merged"
print(pr.mergeable)    # bool or None (calculating)
print(pr.head.ref)     # Source branch
print(pr.base.ref)     # Target branch
print(pr.user.login)   # Author
print(pr.additions)    # Lines added
print(pr.deletions)    # Lines removed
```

</div>

<div v-click class="mt-4">

### Updating a PR

```python
# Update PR title and body
pr = await client.update_pr(
    repo_name="owner/repo",
    pr_number=123,
    title="feat: add OAuth authentication",
    body="Updated description..."
)
```

</div>

<div v-click class="mt-4">

### Getting CI Status

```python
# Check CI/CD status
checks = await client.get_pr_checks(
    "owner/repo", pr_number=123
)

for check in checks:
    print(f"{check.name}: {check.conclusion}")
    # "lint: success"
    # "test: failure"
```

</div>

</div>

<!--
Pull Requests are central to Maverick's workflow. The fly workflow creates PRs automatically.

**Creating PRs**: Specify source (head) and target (base) branches. The body supports Markdown - use it for good PR descriptions with summaries, change lists, and testing notes.

**Draft PRs**: Set `draft=True` to create a draft PR. Useful when you want feedback before the PR is ready for review.

**PR State**: The `state` can be "open", "closed", or use `merged` property for merged status. `mergeable` may be `None` while GitHub calculates it.

**CI Status**: The `get_pr_checks` method returns CheckRun objects for each CI job. Use this to wait for CI to pass before merging.

**Key Insight**: Creating a PR is just the start. Maverick monitors CI status, handles review feedback, and manages the merge process automatically.
-->

---

## layout: default

# 7.7 Rate Limiting

<div class="text-secondary text-sm mb-4">
Respecting GitHub's API limits with aiolimiter
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### GitHub Rate Limits

<div class="p-4 bg-slate-100 dark:bg-slate-800 rounded-lg">

| Type            | Limit        | Period     |
| --------------- | ------------ | ---------- |
| Authenticated   | **5,000**    | per hour   |
| Unauthenticated | 60           | per hour   |
| Search API      | 30           | per minute |
| GraphQL         | 5,000 points | per hour   |

</div>

</div>

<div v-click class="mt-4">

### Rate Limit Headers

```python
# GitHub returns these headers
X-RateLimit-Limit: 5000
X-RateLimit-Remaining: 4987
X-RateLimit-Reset: 1609459200  # Unix timestamp

# When you hit the limit
HTTP/1.1 403 Forbidden
{
  "message": "API rate limit exceeded",
  "documentation_url": "https://docs.github..."
}
```

</div>

</div>

<div>

<div v-click>

### aiolimiter Integration

```python {1-4|6-15|17-26|all}
from aiolimiter import AsyncLimiter

# 5000 requests per 3600 seconds (1 hour)
rate_limiter = AsyncLimiter(5000, 3600.0)

class GitHubClient:
    def __init__(
        self,
        rate_limit: int | None = None,
        rate_period: float | None = None,
    ):
        if rate_limit:
            self._rate_limiter = AsyncLimiter(
                rate_limit, rate_period or 3600.0
            )
        else:
            self._rate_limiter = None

    async def list_issues(self, repo_name: str, ...):
        def _list_issues():
            # Sync PyGithub call
            return list(repo.get_issues()[:limit])

        if self._rate_limiter:
            async with self._rate_limiter:
                return await asyncio.to_thread(_list_issues)
        return await asyncio.to_thread(_list_issues)
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Smooth Distribution:</strong> aiolimiter spreads requests evenly over time rather than allowing bursts followed by throttling.
</div>

</div>

</div>

<!--
Rate limiting is critical for production applications. Hit the limit and your app stops working.

**GitHub Limits**:
- 5,000 requests per hour for authenticated users
- 60 for unauthenticated (effectively useless)
- Search API has a separate, stricter limit

**aiolimiter**: Instead of tracking remaining requests manually, we use aiolimiter. It's a token bucket algorithm that:
1. Spreads requests evenly over time
2. Is async-native (no blocking)
3. Handles concurrent async tasks correctly

**How It Works**:
1. Create limiter with max requests and time period
2. Use `async with rate_limiter:` before each API call
3. aiolimiter blocks if we're going too fast

**Why Optional?**: Rate limiting is off by default for backward compatibility. Enable it in production with `rate_limit=5000`.
-->

---

## layout: default

# 7.8 Async Wrapper Pattern

<div class="text-secondary text-sm mb-4">
Making synchronous PyGithub work in async Maverick
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### The Problem

<div class="p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm mb-4">
  <strong class="text-coral">PyGithub is synchronous</strong> — API calls block the event loop, freezing the TUI.
</div>

```python
# ❌ DON'T: Blocks the entire app
async def bad_example():
    github = Github(auth=auth)
    # This blocks! TUI freezes.
    issues = github.get_repo("owner/repo").get_issues()
    for issue in issues:
        print(issue.title)
```

</div>

<div v-click class="mt-4">

### The Solution

```python
# ✅ DO: Run sync code in thread pool
import asyncio

async def good_example():
    def _sync_operation():
        # Sync PyGithub code runs in thread
        github = Github(auth=auth)
        repo = github.get_repo("owner/repo")
        return list(repo.get_issues()[:10])

    # Non-blocking! TUI stays responsive
    issues = await asyncio.to_thread(_sync_operation)
    for issue in issues:
        print(issue.title)
```

</div>

</div>

<div>

<div v-click>

### GitHubClient Pattern

```python {1-5|7-17|19-28|all}
class GitHubClient:
    """Async-friendly wrapper around PyGithub."""

    def __init__(self, github: Github | None = None):
        self._github = github

    @property
    def github(self) -> Github:
        """Lazy initialization."""
        if self._github is None:
            self._github = get_github_client()
        return self._github

    def _get_repo(self, repo_name: str) -> Repository:
        """Get a repository by full name."""
        return self.github.get_repo(repo_name)

    async def list_issues(
        self, repo_name: str, state: str = "open", ...
    ) -> list[Issue]:
        """Async wrapper for listing issues."""
        def _list_issues() -> list[Issue]:
            repo = self._get_repo(repo_name)
            return list(repo.get_issues(state=state)[:limit])

        if self._rate_limiter:
            async with self._rate_limiter:
                return await asyncio.to_thread(_list_issues)
        return await asyncio.to_thread(_list_issues)
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Pattern:</strong> Define sync helper function → wrap in <code>asyncio.to_thread()</code> → optionally apply rate limiting.
</div>

</div>

</div>

<!--
This is a critical pattern in Maverick. PyGithub is synchronous, but Maverick is async. How do we bridge the gap?

**The Problem**: Sync API calls block the event loop. In an async TUI app, this means the entire UI freezes during API calls. Users see a hung application.

**The Solution**: `asyncio.to_thread()` runs sync code in a thread pool. The event loop continues, the TUI stays responsive, and we get the result when the API call completes.

**The Pattern**:
1. Define a sync helper function inside the async method
2. Put all PyGithub calls in that sync function
3. Call `await asyncio.to_thread(_sync_func)`
4. Optionally wrap with rate limiter

**Why Lazy Init?**: The `github` property initializes lazily. This means:
- No API call at GitHubClient construction time
- Authentication errors surface at first use, not import time
- Can be tested without gh CLI by passing a mock Github instance

This pattern appears throughout Maverick wherever we use sync libraries.
-->

---

## layout: center

# 7. PyGithub Summary

<div class="grid grid-cols-2 gap-8 mt-8 text-sm">

<div>

### Key Takeaways

<div class="space-y-3 mt-4">

<div class="flex items-start gap-2">
  <span class="w-6 h-6 rounded-full bg-teal/20 text-teal flex items-center justify-center text-xs font-bold">1</span>
  <div>
    <strong>Use GitHubClient</strong>
    <div class="text-muted text-xs">Not raw PyGithub - async-safe, rate-limited</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="w-6 h-6 rounded-full bg-teal/20 text-teal flex items-center justify-center text-xs font-bold">2</span>
  <div>
    <strong>Auth via gh CLI</strong>
    <div class="text-muted text-xs">Secure, no token management</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="w-6 h-6 rounded-full bg-teal/20 text-teal flex items-center justify-center text-xs font-bold">3</span>
  <div>
    <strong>Rate Limiting</strong>
    <div class="text-muted text-xs">5,000/hour limit with aiolimiter</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="w-6 h-6 rounded-full bg-teal/20 text-teal flex items-center justify-center text-xs font-bold">4</span>
  <div>
    <strong>asyncio.to_thread()</strong>
    <div class="text-muted text-xs">Wrap sync calls for async context</div>
  </div>
</div>

</div>

</div>

<div>

### Quick Reference

```python
from maverick.utils.github_client import GitHubClient

client = GitHubClient(
    rate_limit=5000,
    rate_period=3600.0
)

# Issues
issues = await client.list_issues("owner/repo")
issue = await client.get_issue("owner/repo", 42)
await client.create_issue("owner/repo", "Title", "Body")
await client.add_issue_comment("owner/repo", 42, "Comment")

# Pull Requests
pr = await client.create_pr(
    "owner/repo", "Title", "Body",
    head="feature", base="main"
)
pr = await client.get_pr("owner/repo", 123)
checks = await client.get_pr_checks("owner/repo", 123)

# Cleanup
client.close()
```

</div>

</div>

<div class="mt-8 p-4 bg-brass/10 border border-brass/30 rounded-lg">
  <strong class="text-brass">Up Next:</strong> Section 8 covers <strong>Tenacity</strong> - retry logic with exponential backoff for resilient API interactions.
</div>

<!--
Section 7 Summary - PyGithub and GitHub API integration.

**Key Points**:
1. Always use `maverick.utils.github_client.GitHubClient` - never raw PyGithub
2. Authentication flows through gh CLI - secure and user-friendly
3. Enable rate limiting in production to avoid hitting API limits
4. The `asyncio.to_thread()` pattern bridges sync PyGithub with async Maverick

**What We Covered**:
- GitHub API fundamentals
- PyGithub setup and key classes
- gh CLI authentication approach
- Repository, Issues, and PR operations
- Rate limiting with aiolimiter
- Async wrapper pattern for TUI responsiveness

Next up: Tenacity for retry logic - because network calls fail, and we need to handle that gracefully.
-->
````
