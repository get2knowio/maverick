---
name: maverick-ansible
description: Ansible playbook, role, and security best practices
version: 1.0.0
triggers:
  - ansible
  - playbook
  - "tasks:"
  - "handlers:"
  - "roles:"
  - "hosts:"
  - ansible-playbook
  - ansible-vault
  - become
  - when:
  - notify:
  - register:
  - with_items
  - loop:
  - ansible-lint
  - galaxy.yml
  - requirements.yml
  - inventory
---

# Ansible Skill

Expert guidance for Ansible playbooks, roles, and automation best practices.

## Playbook Structure

### Basic Playbook
```yaml
---
- name: Configure web servers
  hosts: webservers
  become: true
  vars:
    http_port: 80

  tasks:
    - name: Install nginx
      ansible.builtin.apt:
        name: nginx
        state: present
        update_cache: true

    - name: Start nginx service
      ansible.builtin.service:
        name: nginx
        state: started
        enabled: true
```

### Multiple Plays
```yaml
---
- name: Configure database servers
  hosts: databases
  tasks:
    - name: Install PostgreSQL
      ansible.builtin.apt:
        name: postgresql
        state: present

- name: Configure web servers
  hosts: webservers
  tasks:
    - name: Install nginx
      ansible.builtin.apt:
        name: nginx
        state: present
```

## Idempotency (CRITICAL)

**Idempotent tasks can run multiple times without changing the result after the first run.**

### ✅ Idempotent Examples
```yaml
# Good - using built-in modules (always idempotent)
- name: Ensure nginx is installed
  ansible.builtin.apt:
    name: nginx
    state: present

- name: Ensure config file has correct content
  ansible.builtin.copy:
    src: nginx.conf
    dest: /etc/nginx/nginx.conf
    owner: root
    mode: '0644'
```

### ❌ Non-Idempotent Antipatterns
```yaml
# BAD - runs every time, always reports "changed"
- name: Configure system
  ansible.builtin.shell: echo "config" >> /etc/app.conf

# GOOD - idempotent alternative
- name: Ensure config line exists
  ansible.builtin.lineinfile:
    path: /etc/app.conf
    line: "config"
    create: true
```

### Making Shell/Command Idempotent
```yaml
# Use changed_when and creates/removes
- name: Download file
  ansible.builtin.shell: |
    curl -o /tmp/file.tar.gz https://example.com/file.tar.gz
  args:
    creates: /tmp/file.tar.gz
  changed_when: false

# Or check conditions first
- name: Check if configured
  ansible.builtin.stat:
    path: /etc/app/.configured
  register: configured

- name: Run configuration script
  ansible.builtin.shell: /opt/app/configure.sh
  when: not configured.stat.exists

- name: Mark as configured
  ansible.builtin.file:
    path: /etc/app/.configured
    state: touch
  when: not configured.stat.exists
```

## Variables & Jinja2 Templating

### Variable Precedence (low to high)
1. Role defaults (`roles/*/defaults/main.yml`)
2. Inventory vars
3. Playbook vars
4. Extra vars (`-e` / `--extra-vars`)

### Using Variables
```yaml
---
- name: Deploy application
  hosts: app_servers
  vars:
    app_version: "1.2.3"
    app_user: "appuser"

  tasks:
    - name: Download application version {{ app_version }}
      ansible.builtin.get_url:
        url: "https://releases.example.com/app-{{ app_version }}.tar.gz"
        dest: "/opt/app-{{ app_version }}.tar.gz"
        owner: "{{ app_user }}"
```

### Facts
```yaml
# Gather facts automatically (default: true)
- name: Show system facts
  hosts: all
  tasks:
    - name: Display OS family
      ansible.builtin.debug:
        msg: "OS family is {{ ansible_os_family }}"

    - name: Display IP address
      ansible.builtin.debug:
        msg: "IP is {{ ansible_default_ipv4.address }}"
```

### Conditionals
```yaml
- name: Install package on Debian-based systems
  ansible.builtin.apt:
    name: nginx
    state: present
  when: ansible_os_family == "Debian"

- name: Install package on RedHat-based systems
  ansible.builtin.yum:
    name: nginx
    state: present
  when: ansible_os_family == "RedHat"
```

## Handlers

**Handlers run once at the end of a play, after all tasks.**

```yaml
---
- name: Configure web server
  hosts: webservers
  tasks:
    - name: Copy nginx config
      ansible.builtin.copy:
        src: nginx.conf
        dest: /etc/nginx/nginx.conf
      notify: Restart nginx

    - name: Copy site config
      ansible.builtin.template:
        src: site.conf.j2
        dest: /etc/nginx/sites-available/mysite
      notify: Restart nginx

  handlers:
    - name: Restart nginx
      ansible.builtin.service:
        name: nginx
        state: restarted
```

**Key points:**
- Handlers only run if notified
- Handlers run once, even if notified multiple times
- Handlers run at the end of the play
- Use `meta: flush_handlers` to run handlers immediately

## Loops

### Modern Loop Syntax (Ansible 2.5+)
```yaml
# Preferred
- name: Install packages
  ansible.builtin.apt:
    name: "{{ item }}"
    state: present
  loop:
    - nginx
    - postgresql
    - redis

# With dictionary
- name: Create users
  ansible.builtin.user:
    name: "{{ item.name }}"
    groups: "{{ item.groups }}"
  loop:
    - { name: 'alice', groups: 'admin' }
    - { name: 'bob', groups: 'users' }
```

### Legacy Loop Syntax (avoid)
```yaml
# OLD - avoid in new playbooks
- name: Install packages
  ansible.builtin.apt:
    name: "{{ item }}"
    state: present
  with_items:
    - nginx
    - postgresql
```

## Roles

### Role Structure
```
roles/
└── webserver/
    ├── tasks/
    │   └── main.yml          # Main task list
    ├── handlers/
    │   └── main.yml          # Handlers
    ├── templates/
    │   └── nginx.conf.j2     # Jinja2 templates
    ├── files/
    │   └── index.html        # Static files
    ├── vars/
    │   └── main.yml          # Variables
    ├── defaults/
    │   └── main.yml          # Default variables
    ├── meta/
    │   └── main.yml          # Role metadata/dependencies
    └── README.md
```

### Using Roles
```yaml
---
- name: Configure servers
  hosts: webservers
  roles:
    - common
    - webserver
    - monitoring

# Or with parameters
- name: Configure servers
  hosts: webservers
  roles:
    - role: webserver
      vars:
        http_port: 8080
```

### Role Dependencies
```yaml
# roles/webserver/meta/main.yml
---
dependencies:
  - role: common
  - role: firewall
    vars:
      firewall_allowed_ports:
        - 80
        - 443
```

## Security Best Practices

### Ansible Vault (CRITICAL)

**Never commit unencrypted secrets!**

```bash
# Encrypt a file
ansible-vault encrypt secrets.yml

# Edit encrypted file
ansible-vault edit secrets.yml

# Run playbook with vault password
ansible-playbook site.yml --ask-vault-pass
# Or use password file
ansible-playbook site.yml --vault-password-file ~/.vault_pass
```

**Encrypted variables:**
```yaml
# vars/secrets.yml (encrypted with ansible-vault)
---
db_password: !vault |
          $ANSIBLE_VAULT;1.1;AES256
          66386439653361336136343...
api_key: !vault |
          $ANSIBLE_VAULT;1.1;AES256
          35323264353938643261623...
```

### Privilege Escalation

**Use `become` carefully:**
```yaml
# Entire play
- name: Configure system
  hosts: servers
  become: true  # Run all tasks as root
  tasks:
    - name: Install package
      ansible.builtin.apt:
        name: nginx

# Specific task
- name: Configure system
  hosts: servers
  tasks:
    - name: Install package (requires root)
      ansible.builtin.apt:
        name: nginx
      become: true

    - name: Copy user file (no root needed)
      ansible.builtin.copy:
        src: .bashrc
        dest: ~/.bashrc
```

**Become user:**
```yaml
- name: Run as specific user
  ansible.builtin.command: whoami
  become: true
  become_user: appuser
```

### Hiding Sensitive Output

```yaml
# Don't log sensitive data
- name: Set database password
  ansible.builtin.shell: |
    psql -c "ALTER USER postgres PASSWORD '{{ db_password }}'"
  no_log: true

# Register without logging
- name: Get API token
  ansible.builtin.uri:
    url: https://api.example.com/token
    method: POST
  register: token_response
  no_log: true
```

### Inventory Security

```yaml
# Don't commit passwords in inventory
# BAD
[databases]
db1 ansible_host=10.0.1.10 ansible_user=admin ansible_password=secret123

# GOOD - use vault for passwords
[databases]
db1 ansible_host=10.0.1.10 ansible_user=admin

# In encrypted group_vars/databases.yml
ansible_password: !vault |
          $ANSIBLE_VAULT;1.1;AES256
          ...
```

## Module Best Practices

### Prefer Specific Modules Over shell/command

```yaml
# BAD - using shell when module exists
- name: Install package
  ansible.builtin.shell: apt-get install -y nginx

# GOOD - using built-in module
- name: Install package
  ansible.builtin.apt:
    name: nginx
    state: present

# BAD - using shell for file operations
- name: Create directory
  ansible.builtin.shell: mkdir -p /opt/app

# GOOD - using file module
- name: Create directory
  ansible.builtin.file:
    path: /opt/app
    state: directory
    mode: '0755'
```

### Fully Qualified Collection Names (Ansible 2.10+)

```yaml
# GOOD - explicit collection
- name: Install package
  ansible.builtin.apt:
    name: nginx

# Also acceptable for clarity
- name: Manage Docker container
  community.docker.docker_container:
    name: myapp
    image: nginx:latest
```

## Common Pitfalls

### 1. Not Using check_mode
```yaml
# Always test with --check first
# ansible-playbook site.yml --check

- name: Dangerous operation
  ansible.builtin.file:
    path: /etc/important-config
    state: absent
  # Test with --check before running!
```

### 2. Ignoring Return Codes
```yaml
# BAD - ignores failures
- name: Run script
  ansible.builtin.shell: /opt/app/script.sh
  ignore_errors: true

# GOOD - handle failures explicitly
- name: Run script
  ansible.builtin.shell: /opt/app/script.sh
  register: script_result
  failed_when: script_result.rc != 0 and script_result.rc != 2
```

### 3. Not Handling "changed" Status
```yaml
# BAD - always reports changed
- name: Check status
  ansible.builtin.shell: systemctl status nginx

# GOOD - mark as not changed
- name: Check status
  ansible.builtin.shell: systemctl status nginx
  changed_when: false
  check_mode: false
```

### 4. Using shell when command suffices
```yaml
# BAD - unnecessary shell features
- name: List files
  ansible.builtin.shell: ls /tmp

# GOOD - use command (safer, no shell injection)
- name: List files
  ansible.builtin.command: ls /tmp
  changed_when: false
```

## Ansible Lint

### Common Rules

**`yaml[line-length]`** - Keep lines under 160 characters
**`name[missing]`** - All tasks must have names
**`fqcn[action-core]`** - Use fully qualified collection names
**`no-changed-when`** - shell/command should have changed_when
**`risky-shell-pipe`** - Avoid pipes in shell commands

### Configuration
```yaml
# .ansible-lint
---
skip_list:
  - yaml[line-length]  # Skip if you have long lines

warn_list:
  - experimental  # Warn on experimental features

exclude_paths:
  - .cache/
  - test/
```

## Naming Conventions

```yaml
# GOOD - descriptive names in imperative mood
- name: Ensure nginx is installed
- name: Copy nginx configuration
- name: Restart nginx service

# BAD - vague or missing names
- name: nginx
- name: Task 1
- apt: name=nginx  # Missing name entirely
```

## Tags for Selective Execution

```yaml
---
- name: Configure system
  hosts: all
  tasks:
    - name: Install packages
      ansible.builtin.apt:
        name: "{{ item }}"
      loop:
        - nginx
        - postgresql
      tags:
        - packages
        - install

    - name: Configure firewall
      ansible.builtin.ufw:
        rule: allow
        port: 80
      tags:
        - firewall
        - security

# Run only specific tags
# ansible-playbook site.yml --tags "packages"
# ansible-playbook site.yml --skip-tags "firewall"
```

## Review Severity Guidelines

- **CRITICAL**: Unencrypted secrets in files, using `shell` with user input, privilege escalation without justification
- **MAJOR**: Non-idempotent tasks, using shell/command when module exists, missing `no_log` on sensitive tasks, not using ansible-vault
- **MINOR**: Missing task names, not using FQCN, missing `changed_when` on commands, using legacy `with_items`
- **SUGGESTION**: Could use tags for organization, could extract to role, could use handlers instead of multiple restarts

## References

- [Ansible Documentation](https://docs.ansible.com/)
- [Ansible Best Practices](https://docs.ansible.com/ansible/latest/user_guide/playbooks_best_practices.html)
- [Ansible Lint](https://ansible-lint.readthedocs.io/)
- [Ansible Vault](https://docs.ansible.com/ansible/latest/user_guide/vault.html)
