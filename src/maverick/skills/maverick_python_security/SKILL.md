---
name: maverick-python-security
description: Python security patterns and OWASP vulnerability detection
version: 1.0.0
triggers:
  - SQL
  - execute
  - subprocess
  - shell
  - input(
  - eval(
  - exec(
  - secrets
  - password
  - api_key
  - token
  - XSS
  - injection
  - OWASP
  - security
  - CVE
  - sanitize
  - escape
  - authenticate
---

# Python Security Skill

Expert guidance for identifying and preventing security vulnerabilities in Python code.

## OWASP Top 10 for Python

### 1. SQL Injection (CRITICAL)

**Vulnerability:**
```python
# CRITICAL VULNERABILITY
user_id = request.GET['id']
query = f"SELECT * FROM users WHERE id = {user_id}"
cursor.execute(query)
```

**Safe Alternative:**
```python
# SAFE - parameterized query
user_id = request.GET.get('id')
if not user_id:
    return HttpResponse(status=400)

query = "SELECT * FROM users WHERE id = %s"
cursor.execute(query, (user_id,))
```

**ORM Usage (Safest):**
```python
# Django ORM - safe by default
user = User.objects.get(id=user_id)

# SQLAlchemy - safe by default
user = session.query(User).filter(User.id == user_id).first()
```

**Red Flags:**
- String formatting in SQL queries (`f"..."`, `"...".format()`, `%`)
- Direct variable interpolation in queries
- User input concatenated into SQL

### 2. Command Injection (CRITICAL)

**Vulnerability:**
```python
# CRITICAL VULNERABILITY
filename = request.GET['file']
os.system(f"cat {filename}")  # Command injection!

# CRITICAL VULNERABILITY
subprocess.run(f"git clone {url}", shell=True)  # Shell injection!
```

**Safe Alternative:**
```python
# SAFE - no shell, list arguments
filename = request.GET.get('file')
if not is_safe_path(filename):
    raise ValueError("Invalid filename")

subprocess.run(["cat", filename], shell=False, check=True)

# SAFE - validated input, no shell
subprocess.run(["git", "clone", url], shell=False, check=True)
```

**Rules:**
- **NEVER** use `shell=True` with user input
- **NEVER** use `os.system()` with user input
- **ALWAYS** use list arguments in `subprocess.run()`
- **ALWAYS** validate user input before passing to commands

### 3. Path Traversal (CRITICAL)

**Vulnerability:**
```python
# CRITICAL VULNERABILITY
filename = request.GET['file']
with open(f"/data/{filename}") as f:  # Can access ../../etc/passwd
    return f.read()
```

**Safe Alternative:**
```python
from pathlib import Path

def safe_read(base_dir: Path, filename: str) -> str:
    """Safely read file, preventing path traversal."""
    # Resolve to absolute path
    filepath = (base_dir / filename).resolve()

    # Check it's within base_dir
    if not filepath.is_relative_to(base_dir):
        raise ValueError("Path traversal attempt detected")

    # Additional checks
    if not filepath.exists():
        raise FileNotFoundError()
    if not filepath.is_file():
        raise ValueError("Not a file")

    return filepath.read_text()
```

**Validation Pattern:**
```python
import re

def is_safe_filename(filename: str) -> bool:
    """Validate filename against path traversal."""
    # Reject path separators and special characters
    if re.search(r'[/\\]|\.\.', filename):
        return False

    # Whitelist allowed characters
    if not re.match(r'^[a-zA-Z0-9_.-]+$', filename):
        return False

    return True
```

### 4. Hardcoded Secrets (CRITICAL)

**Vulnerability:**
```python
# CRITICAL - hardcoded secrets
API_KEY = "sk-1234567890abcdef"
DATABASE_PASSWORD = "MyP@ssw0rd123"
AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
```

**Safe Alternative:**
```python
import os
from pathlib import Path

# Environment variables
API_KEY = os.environ["API_KEY"]
DATABASE_PASSWORD = os.environ["DATABASE_PASSWORD"]

# Or use python-dotenv
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("API_KEY")

# Or use secrets management service (best)
from aws_secretsmanager import get_secret
API_KEY = get_secret("api-key")
```

**.gitignore Must Include:**
```
.env
.env.*
secrets.yaml
credentials.json
*.pem
*.key
```

**Detection Patterns:**
- Check for `password=`, `api_key=`, `token=`, `secret=` with string values
- Check for base64-encoded strings (often secrets)
- Check for AWS keys (starts with `AKIA`)
- Check for private keys (`BEGIN PRIVATE KEY`)

### 5. Insecure Deserialization (CRITICAL)

**Vulnerability:**
```python
# CRITICAL - pickle can execute arbitrary code
import pickle
data = pickle.loads(user_input)  # DANGEROUS!

# CRITICAL - eval/exec with user input
result = eval(user_input)  # DANGEROUS!
```

**Safe Alternative:**
```python
import json

# SAFE - JSON can't execute code
data = json.loads(user_input)

# If you need Python objects, validate rigorously
from pydantic import BaseModel

class SafeData(BaseModel):
    name: str
    age: int

# This validates and raises on invalid data
data = SafeData.model_validate_json(user_input)
```

**Rules:**
- **NEVER** use `pickle.loads()` on untrusted data
- **NEVER** use `eval()` or `exec()` on user input
- **ALWAYS** use JSON or validated Pydantic models
- If you must deserialize Python objects, use `__reduce_ex__` restrictions

### 6. XML External Entities (XXE)

**Vulnerability:**
```python
# VULNERABLE - allows XXE attacks
import xml.etree.ElementTree as ET
tree = ET.parse(user_file)  # Can read local files!
```

**Safe Alternative:**
```python
# SAFE - defusedxml prevents XXE
from defusedxml.ElementTree import parse
tree = parse(user_file)

# Or disable DTD processing
import xml.etree.ElementTree as ET
parser = ET.XMLParser()
parser.entity = {}  # Disable entities
tree = ET.parse(user_file, parser=parser)
```

### 7. Cross-Site Scripting (XSS)

**Vulnerability (Web Frameworks):**
```python
# Flask - VULNERABLE if using raw HTML
@app.route('/user/<username>')
def show_user(username):
    return f"<h1>Hello {username}</h1>"  # XSS!

# Django - VULNERABLE if |safe filter used
# template.html
{{ user_input|safe }}  # XSS!
```

**Safe Alternative:**
```python
# Flask - use templates with auto-escaping
from flask import render_template_string

@app.route('/user/<username>')
def show_user(username):
    return render_template_string("<h1>Hello {{ username }}</h1>", username=username)

# Django - templates auto-escape by default
# template.html
{{ user_input }}  # Automatically escaped

# If you must use |safe, sanitize first
from bleach import clean
safe_input = clean(user_input, tags=['b', 'i', 'em'], strip=True)
# template: {{ safe_input|safe }}
```

### 8. Insecure Randomness

**Vulnerability:**
```python
import random

# INSECURE for security purposes
session_token = random.randint(1000, 9999)  # Predictable!
api_key = ''.join(random.choices('0123456789', k=32))  # Predictable!
```

**Safe Alternative:**
```python
import secrets

# SECURE - cryptographically random
session_token = secrets.token_urlsafe(32)
api_key = secrets.token_hex(32)

# For random integers
secure_random = secrets.randbelow(10000)

# For random choices
secure_choice = secrets.choice(['a', 'b', 'c'])
```

**Rules:**
- **NEVER** use `random` module for security (tokens, keys, passwords)
- **ALWAYS** use `secrets` module for security-related randomness
- Use `secrets.token_urlsafe()` for tokens
- Use `secrets.token_hex()` for API keys

### 9. Weak Cryptography

**Vulnerability:**
```python
import hashlib

# INSECURE - MD5/SHA1 are broken
password_hash = hashlib.md5(password.encode()).hexdigest()
signature = hashlib.sha1(data.encode()).digest()
```

**Safe Alternative:**
```python
from argon2 import PasswordHasher
from cryptography.hazmat.primitives import hashes, hmac

# SECURE password hashing
ph = PasswordHasher()
password_hash = ph.hash(password)

# Verification
try:
    ph.verify(password_hash, password)
    print("Password correct")
except:
    print("Password incorrect")

# SECURE HMAC
key = os.urandom(32)
h = hmac.HMAC(key, hashes.SHA256())
h.update(data)
signature = h.finalize()
```

**Approved Algorithms:**
- **Password hashing**: Argon2, bcrypt, scrypt (NOT MD5, SHA1, SHA256)
- **HMAC**: SHA256, SHA384, SHA512 (NOT MD5, SHA1)
- **Encryption**: AES-256-GCM, ChaCha20-Poly1305 (NOT DES, 3DES)

### 10. Insufficient Logging & Monitoring

**Vulnerability:**
```python
def transfer_money(from_account, to_account, amount):
    # No logging!
    from_account.balance -= amount
    to_account.balance += amount
```

**Safe Alternative:**
```python
import logging

logger = logging.getLogger(__name__)

def transfer_money(from_account, to_account, amount):
    logger.info(
        "transfer_initiated",
        from=from_account.id,
        to=to_account.id,
        amount=amount,
    )

    try:
        from_account.balance -= amount
        to_account.balance += amount

        logger.info("transfer_completed", transaction_id=tx_id)

    except Exception as e:
        logger.error(
            "transfer_failed",
            from=from_account.id,
            to=to_account.id,
            error=str(e),
        )
        raise
```

## Security Code Review Checklist

### Authentication & Authorization
- [ ] Passwords never logged or stored in plain text
- [ ] Multi-factor authentication for sensitive operations
- [ ] Session tokens are cryptographically random
- [ ] Authorization checked on every request
- [ ] No hardcoded credentials

### Input Validation
- [ ] All user input validated (type, length, format)
- [ ] Whitelist validation, not blacklist
- [ ] Input sanitized before use in SQL, commands, paths
- [ ] File uploads checked for type and size
- [ ] No `eval()`, `exec()`, or `__import__()` on user input

### Output Encoding
- [ ] HTML output escaped (XSS prevention)
- [ ] SQL parameters use placeholders (injection prevention)
- [ ] JSON output properly encoded
- [ ] HTTP headers validated

### Data Protection
- [ ] Sensitive data encrypted at rest
- [ ] TLS/HTTPS for data in transit
- [ ] Secrets in environment variables or secret manager
- [ ] Passwords hashed with Argon2/bcrypt
- [ ] No secrets in logs

### Error Handling
- [ ] Generic error messages to users (no stack traces)
- [ ] Detailed errors logged server-side
- [ ] No information leakage in error responses

## Review Severity Guidelines

- **CRITICAL**: SQL injection, command injection, hardcoded secrets, path traversal, insecure deserialization
- **MAJOR**: Weak cryptography, missing input validation, `shell=True` without validation, XSS vulnerabilities
- **MINOR**: Missing CSRF protection, insecure randomness for non-security purposes, verbose error messages
- **SUGGESTION**: Could use parameterized queries, could validate input more rigorously

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)
- [PyCQA Bandit](https://bandit.readthedocs.io/) - Security linter for Python
