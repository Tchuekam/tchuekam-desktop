---
name: ai-video-generation
description: "Generative AI Text-to-Video and Image-to-Video creation API integrations (HunyuanVideo, Runway Gen-3, Luma, Kling AI)."
version: 1.0.0
author: Tchuekam Agent + Antigravity
license: MIT
platforms: [linux, macos, windows]
metadata:
  tchuekam:
    tags: [AI-Video, Generative-AI, Replicate, Text-to-Video, Image-to-Video, Creative]
    related_skills: [remotion-video, ffmpeg-video-editor, comfyui]
---

# AI Video Generation — Generative Video API Orchestration

Generate synthetic video sequences, visual B-roll, and character animations from text prompts or reference images using cloud APIs (Replicate, Runway, Luma, HunyuanVideo).

## Workflows & Providers

### 1. Replicate API (HunyuanVideo / CogVideoX / Luma)
Generate video using Replicate python client:
```python
import replicate

output = replicate.run(
    "tencent/hunyuan-video:8540b084c728e83f35d2520aa11d51494645201280001099b22a089d71c4c810",
    input={
        "prompt": "A cinematic close up shot of a futuristic neon city in the rain, 8k resolution",
        "num_frames": 129,
        "fps": 24
    }
)
print("Generated Video URL:", output)
```

### 2. Image-to-Video Motion Synthesis
Animate a static image into a video clip:
```python
output = replicate.run(
    "stability-ai/stable-video-diffusion:3f0457e4619da25d21e6178479b793d49471115f577de7614f31f27d1d931a24",
    input={
        "input_image": open("character.png", "rb"),
        "motion_bucket_id": 127,
        "cond_aug": 0.02
    }
)
```

### 3. Post-Processing Pipeline
Combine generated AI clips with FFmpeg or Remotion to compose full short films or social posts.

## Key Prompting Tips
- Specify camera movements: `slow pan right`, `drone zoom out`, `dolly shot`.
- Include lighting details: `volumetric lighting`, `golden hour`, `cyberpunk neon illumination`.
- Maintain consistent frame rate (24fps / 30fps) across scenes.
