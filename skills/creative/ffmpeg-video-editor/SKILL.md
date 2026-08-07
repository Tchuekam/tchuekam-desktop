---
name: ffmpeg-video-editor
description: "Command-line video editing, concatenation, stream multiplexing, and format conversion with FFmpeg."
version: 1.0.0
author: Tchuekam Agent + Antigravity
license: MIT
platforms: [linux, macos, windows]
metadata:
  tchuekam:
    tags: [Video, FFmpeg, Editing, Transcoding, Subtitles, Audio, GIF]
    related_skills: [remotion-video, ai-video-generation, manim-video]
---

# FFmpeg Video Editor — High Performance CLI Video Processing

Perform non-linear video editing, format conversion, subtitle embedding, audio-video multiplexing, and optimization using FFmpeg.

## Frequently Used Commands

### 1. Trimming & Slicing
Trim video without re-encoding (lightning fast):
```bash
ffmpeg -ss 00:00:10 -to 00:00:30 -i input.mp4 -c copy output.mp4
```

### 2. Video Concatenation
Combine multiple clips listed in `clips.txt`:
```bash
# clips.txt format:
# file 'clip1.mp4'
# file 'clip2.mp4'
ffmpeg -f concat -safe 0 -i clips.txt -c copy merged.mp4
```

### 3. Adding Audio to Video
Combine video track with audio track:
```bash
ffmpeg -i video.mp4 -i audio.mp3 -c:v copy -c:a aac -shortest final.mp4
```

### 4. Subtitle Burn-In
Hardcode subtitles into the video stream:
```bash
ffmpeg -i input.mp4 -vf "subtitles=subtitles.srt:force_style='FontSize=24,PrimaryColour=&H00FFFFFF&'" output.mp4
```

### 5. Generating High Quality GIFs
Convert video snippet to optimized palette GIF:
```bash
ffmpeg -i input.mp4 -vf "fps=15,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" animation.gif
```

## Best Practices
- Use `-c copy` whenever codec modifications aren't necessary.
- Standardize pixel formats with `-pix_fmt yuv420p` for web/mobile compatibility.
