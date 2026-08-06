---
name: fullstack-nextjs-vite
description: "Modern full-stack web application creation (Next.js 15 App Router, React 19, Vite, Server Actions, API routes)."
version: 1.0.0
author: Hermes Agent + Antigravity
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Web-App, Next.js, React, Vite, TypeScript, Fullstack, UI]
    related_skills: [premium-design-intelligence, building-data-apps, playwright-e2e-testing]
---

# Full-Stack Next.js & Vite App Architecture

Scaffold and build modern full-stack web applications using Next.js 15 App Router or Vite + React 19 fast SPAs.

## Core Project Templates

### 1. Next.js 15 App Router Initialization
```bash
npx -y create-next-app@latest ./ --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm
```

### 2. Vite + React Fast SPA
```bash
npx -y create-vite@latest ./ --template react-ts
```

### 3. Next.js Server Actions & API Handlers
Define type-safe Server Actions:
```typescript
'use server';

import { z } from 'zod';

const FormSchema = z.object({
  title: z.string().min(3),
});

export async function createItem(formData: FormData) {
  const data = FormSchema.parse({
    title: formData.get('title'),
  });
  
  // Database mutation logic...
  return { success: true, data };
}
```

### 4. Rich Aesthetic Styling Guidelines
- Apply premium design tokens (dark themes, glassmorphic cards, smooth HSL gradients, Google Fonts like Inter/Outfit).
- Use Nanostores or Zustand for global client-side state.
- Keep route roots thin, delegating views to modular components.

## Best Practices
- Prefer Server Components by default; add `'use client'` only for interactive leaf components.
- Use explicit error boundaries (`error.tsx`) and loading suspense skeletons (`loading.tsx`).
