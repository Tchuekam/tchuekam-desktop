---
name: audio-transcription-and-whisper
description: "Audio track demuxing from video, Whisper speech-to-text transcription with timestamps, and multi-language translation."
version: 1.0.0
author: Tchuekam Agent + Antigravity
license: MIT
platforms: [linux, macos, windows]
metadata:
  tchuekam:
    tags: [Audio, Whisper, Speech-to-Text, Transcription, Demuxing, Translation, STT]
    related_skills: [video-understanding-and-vision, multimodal-video-pipeline, ffmpeg-video-editor]
---

# Audio Transcription & Whisper — Hearing & Speech Processing

Equip the agent to hear, extract, and transcribe spoken audio from video and sound files with word-level timestamps using Whisper (`faster-whisper`, `openai-whisper`, or Groq Audio API).

## Core Workflows

### 1. Audio Track Extraction (Demuxing)
Extract audio stream from video file using FFmpeg:
```bash
ffmpeg -i video.mp4 -vn -acodec libmp3lame -q:a 2 audio.mp3
```

### 2. High-Efficiency Local Transcription (`faster-whisper`)
Transcribe audio with word-level timestamps in Python:
```python
from faster_whisper import WhisperModel

model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe("audio.mp3", word_timestamps=True)

print(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")

for segment in segments:
    print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")
    for word in segment.words:
        print(f"  {word.start:.2f}s - {word.end:.2f}s: {word.word}")
```

### 3. Subtitle Generation (`.srt` / `.vtt`)
Export transcript directly to subtitle formats:
```python
with open("subtitles.srt", "w", encoding="utf-8") as f:
    for i, segment in enumerate(segments, start=1):
        start_time = time.strftime('%H:%M:%S,000', time.gmtime(segment.start))
        end_time = time.strftime('%H:%M:%S,000', time.gmtime(segment.end))
        f.write(f"{i}\n{start_time} --> {end_time}\n{segment.text.strip()}\n\n")
```

### 4. Audio Cloud API (Groq / OpenAI Whisper)
For fast cloud processing:
```python
import openai

client = openai.OpenAI()
with open("audio.mp3", "rb") as audio_file:
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        response_format="verbose_json"
    )
```

## Best Practices
- Extract audio to 16kHz mono MP3 or WAV for optimal STT accuracy.
- Save transcripts as structured JSON and SRT for downstream sync.
