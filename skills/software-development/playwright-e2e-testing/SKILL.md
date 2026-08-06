---
name: playwright-e2e-testing
description: "End-to-end web browser automation, visual regression testing, and E2E test suite generation using Playwright."
version: 1.0.0
author: Hermes Agent + Antigravity
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Testing, Playwright, E2E, Browser-Automation, Quality-Assurance, Fullstack]
    related_skills: [fullstack-nextjs-vite, building-data-apps, popular-web-designs]
---

# Playwright E2E Testing — Web QA & Automated Testing

Create, run, and debug end-to-end browser test suites using Playwright across Chromium, Firefox, and WebKit.

## Core Workflows

### 1. Test Suite Creation
Create TypeScript E2E tests:
```typescript
import { test, expect } from '@playwright/test';

test('user login flow', async ({ page }) => {
  await page.goto('http://localhost:3000/login');
  await page.fill('#email-input', 'test@example.com');
  await page.fill('#password-input', 'password123');
  await page.click('button[type="submit"]');

  await expect(page).toHaveURL('http://localhost:3000/dashboard');
  await expect(page.locator('.welcome-banner')).toContainText('Welcome back');
});
```

### 2. Execution & Reporting
Run Playwright tests in headless mode:
```bash
npx playwright test
```

Run tests with HTML report output:
```bash
npx playwright test --reporter=html
```

### 3. Visual Regression Snapshots
Capture and compare visual snapshots:
```typescript
test('visual snapshot comparison', async ({ page }) => {
  await page.goto('http://localhost:3000/');
  await expect(page).toHaveScreenshot('landing-page.png');
});
```

### 4. Code Generation (Codegen)
Automatically record browser interactions to test scripts:
```bash
npx playwright codegen http://localhost:3000
```

## Best Practices
- Use user-facing locators (`getByRole`, `getByText`, `getByTestId`) over fragile CSS selectors.
- Keep tests isolated with clean state between tests.
- Execute tests against local dev servers before pushing commits.
