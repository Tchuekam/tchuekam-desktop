---
name: aider-coding-assistant
description: "Git-aware multi-file pair programming and autonomous code refactoring using Aider CLI."
version: 1.0.0
author: Hermes Agent + Antigravity
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Coding-Agent, Aider, Git, Refactoring, Pair-Programming, Automation]
    related_skills: [claude-code, codex, opencode, github-pr-workflow]
---

# Aider Coding Assistant — Git-Aware Pair Programming CLI

Delegate complex code editing, refactoring, and multi-file updates to [Aider CLI](https://aider.chat/). Aider leverages Tree-sitter AST repo maps and Git commits for clean code modifications.

## Core Commands

### 1. Non-Interactive One-Shot Prompt Mode
Run a task non-interactively with auto-commit enabled:
```bash
aider --message "Refactor auth module to use async/await across all handlers" --auto-commits --yes-always src/auth.py src/server.py
```

### 2. Multi-File Refactoring with Specific Files
Explicitly pass relevant files to keep context focused:
```bash
aider --message "Implement dark mode theme toggle logic" src/components/ThemeToggle.tsx src/store/themeStore.ts
```

### 3. Running Automated Tests with Self-Correction
Instruct Aider to run tests and automatically fix failures until tests pass:
```bash
aider --test "pytest tests/test_auth.py" --auto-test src/auth.py
```

### 4. Architect / Editor Dual Model Setup
Pair a strong reasoning model (e.g. Claude 3.7 / GPT-4o) with a fast editor model:
```bash
aider --model architect --editor-model sonnet --message "Design and implement user session caching"
```

## Best Practices
- Pass specific files rather than entire directories to preserve token budget.
- Use `--auto-commits` so every edit produces clean git commit histories.
- Use `--lint-cmd` to automatically lint code before completing a turn.
