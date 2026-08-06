---
name: video-understanding-and-vision
description: "Multimodal visual analysis of video files, keyframe sampling, action recognition, and on-screen OCR using Gemini Vision API and OpenCV/FFmpeg."
version: 1.0.0
author: Hermes Agent + Antigravity
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Video-Vision, Vision, Multimodal, OCR, Keyframes, OpenCV, Gemini-Vision]
    related_skills: [audio-transcription-and-whisper, multimodal-video-pipeline, ffmpeg-video-editor]
---

# Video Understanding & Vision — Multimodal Visual Video Analysis

Equip the agent to see, sample, and understand visual contents of video files (`.mp4`, `.webm`, `.mov`, `.mkv`), extract keyframe grids, perform on-screen OCR, and answer visual questions about video events.

## Core Workflows

### 1. Direct Multimodal Video Analysis via Gemini API
Upload and process a video file using the Gemini API:
```python
import time
import google.generativeai as genai

# Upload video file to File API
video_file = genai.upload_file(path="input_video.mp4")

# Wait for processing
while video_file.state.name == "PROCESSING":
    time.sleep(2)
    video_file = genai.get_file(video_file.name)

# Analyze with Gemini 1.5/2.5/3.0 Vision model
model = genai.GenerativeModel(model_name="gemini-1.5-pro")
response = model.generate_content([
    video_file,
    "Describe the video in detail. List all major visual actions, on-screen text/OCR, and timestamped events."
])
print(response.text)
```

### 2. Keyframe Extraction & Grid Generation (FFmpeg)
When sending frame samples to Vision models:
```bash
# Extract 1 frame per second
ffmpeg -i input_video.mp4 -vf "fps=1" -q:v 2 frames/frame_%04d.jpg

# Generate a 3x3 uniform preview grid image
ffmpeg -i input_video.mp4 -vf "select='not(mod(n\,30))',scale=320:-1,tile=3x3" -frames:v 1 grid_preview.jpg
```

### 3. On-Screen OCR & Action Identification
Combine keyframe images with vision prompts to extract:
- Text on signs, slides, code editors, or overlays
- Object movements, gesture changes, and UI interactions
- Scene transitions and timestamped cuts

## Best Practices
- Sample keyframes at 1 fps for general action tracking; 2–5 fps for fast motion or rapid text changes.
- Downscale frame grids (`scale=320:-1` or `640:-1`) to optimize vision token usage while keeping text readable.
