---
name: multimodal-video-pipeline
description: "Combined visual, acoustic, and textual video intelligence pipeline for video Q&A, chaptering, and timestamped summaries."
version: 1.0.0
author: Hermes Agent + Antigravity
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Multimodal, Video-Pipeline, Video-QA, Summarization, Audio-Visual, Intelligence]
    related_skills: [video-understanding-and-vision, audio-transcription-and-whisper, ffmpeg-video-editor]
---

# Multimodal Video Pipeline — End-to-End Video Intelligence

Combine sight (vision models & keyframe sampling), sound (Whisper transcription & audio analysis), and text (OCR & subtitles) into a unified video understanding pipeline.

## Complete 4-Step Pipeline

```
┌──────────────┐     FFmpeg Audio      ┌─────────────────────────┐
│              ├──────────────────────►│ Whisper Transcription   │──┐
│  Input Video │                       └─────────────────────────┘  │
│    (.mp4)    │                                                    ├──► Combined
│              │     FFmpeg Keyframes  ┌─────────────────────────┐  │    Multimodal Context
│              ├──────────────────────►│ Vision & OCR Analysis   │──┘    & Timestamp Alignment
└──────────────┘                       └─────────────────────────┘
```

### Step 1: Audio Extraction & Transcription
```bash
ffmpeg -i video.mp4 -vn -acodec libmp3lame audio.mp3
```
Run `audio-transcription-and-whisper` to produce timestamped transcript JSON.

### Step 2: Visual Sampling & OCR
```bash
ffmpeg -i video.mp4 -vf "fps=0.5,scale=640:-1" frames/frame_%04d.jpg
```
Run `video-understanding-and-vision` on keyframes to extract visual scene descriptions and on-screen text.

### Step 3: Multimodal Synthesis
Merge transcript timestamps with visual keyframe descriptions to form a unified chronological timeline:
```markdown
Timeline:
[00:00 - 00:15] Audio: "Welcome to the system demo." | Vision: Presenter standing on stage in front of blue title slide.
[00:15 - 00:45] Audio: "Here is how the dashboard works." | Vision: Screen switch to dashboard UI showing analytics charts. OCR: "Total Sales: $45,000".
```

### Step 4: Executive Brief & Video Q&A
Pass the synchronized timeline to LLM to produce:
1. Executive Video Summary & Chapter Markers
2. Action Items & Highlight Clips
3. Precise Timestamped Q&A (e.g. "At 01:23, the speaker highlights the API key configuration.")

## Best Practices
- Cache audio transcripts and keyframe descriptions locally to allow instant sub-second Q&A without re-processing the raw video.
