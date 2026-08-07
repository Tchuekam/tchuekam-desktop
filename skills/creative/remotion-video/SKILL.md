---
name: remotion-video
description: "Programmatic video creation and rendering using React, TypeScript, and Remotion CLI."
version: 1.0.0
author: Tchuekam Agent + Antigravity
license: MIT
platforms: [linux, macos, windows]
metadata:
  tchuekam:
    tags: [Video, React, Remotion, Motion-Graphics, Animation, MP4, Creative]
    related_skills: [manim-video, ffmpeg-video-editor, ai-video-generation]
---

# Remotion Video — Programmatic React Video Generation

Use [Remotion](https://www.remotion.dev/) to write videos programmatically in React and TypeScript, rendering high-resolution MP4s, social media shorts, animated lower-thirds, and kinetic typography.

## Core Workflows

### 1. Initialization
Create a Remotion project template:
```bash
npx create-video@latest my-remotion-video --template=helloworld
```

### 2. Composition Definition
Define frame-accurate compositions in React:
```tsx
import { Composition } from 'remotion';
import { MyAnimation } from './MyAnimation';

export const RemotionRoot = () => {
  return (
    <Composition
      id="MyVideo"
      component={MyAnimation}
      durationInFrames={150}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{ titleText: 'Hello World' }}
    />
  );
};
```

### 3. Rendering Video Files
Render to MP4 using the Remotion CLI:
```bash
npx remotion render src/index.ts MyVideo out/output.mp4
```

Render a specific frame range:
```bash
npx remotion render src/index.ts MyVideo out/preview.mp4 --frames=0-60
```

### 4. Audio & Asset Sync
Use Remotion hooks (`useCurrentFrame`, `useVideoConfig`, `interpolate`, `spring`) to synchronize visual motion with audio tracks.

## Best Practices
- Keep components deterministic based on `useCurrentFrame()`.
- Avoid non-deterministic async calls inside render hooks.
- Use H.264 (`--codec=h264`) for maximum compatibility.
