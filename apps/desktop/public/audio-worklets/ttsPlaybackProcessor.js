/*
 * Adapted from KoljaB/RealtimeVoiceChat (Apache License 2.0)
 * https://github.com/KoljaB/RealtimeVoiceChat
 *
 * Gapless Int16 PCM playback queue with instant barge-in buffer clearing.
 */
class TTSPlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    this.bufferQueue = [];
    this.readOffset = 0;
    this.samplesRemaining = 0;
    this.isPlaying = false;

    this.port.onmessage = event => {
      if (event.data && typeof event.data === 'object' && !(event.data instanceof Int16Array) && event.data.type === 'clear') {
        const wasPlaying = this.isPlaying;
        this.bufferQueue = [];
        this.readOffset = 0;
        this.samplesRemaining = 0;
        this.isPlaying = false;
        if (wasPlaying) {
          this.port.postMessage({ type: 'ttsPlaybackStopped', cleared: true });
        }
        return;
      }

      const chunk = event.data instanceof Int16Array ? event.data : new Int16Array(event.data);
      if (chunk.length > 0) {
        this.bufferQueue.push(chunk);
        this.samplesRemaining += chunk.length;
      }
    };
  }

  process(_inputs, outputs) {
    const outputChannel = outputs[0][0];
    if (!outputChannel) {
      return true;
    }

    if (this.samplesRemaining === 0) {
      outputChannel.fill(0);
      if (this.isPlaying) {
        this.isPlaying = false;
        this.port.postMessage({ type: 'ttsPlaybackStopped' });
      }
      return true;
    }

    if (!this.isPlaying) {
      this.isPlaying = true;
      this.port.postMessage({ type: 'ttsPlaybackStarted' });
    }

    let outIdx = 0;
    while (outIdx < outputChannel.length && this.bufferQueue.length > 0) {
      const currentBuffer = this.bufferQueue[0];
      const sampleValue = currentBuffer[this.readOffset] / 32768;
      outputChannel[outIdx++] = sampleValue;

      this.readOffset++;
      this.samplesRemaining--;

      if (this.readOffset >= currentBuffer.length) {
        this.bufferQueue.shift();
        this.readOffset = 0;
      }
    }

    while (outIdx < outputChannel.length) {
      outputChannel[outIdx++] = 0;
    }

    return true;
  }
}

registerProcessor('tts-playback-processor', TTSPlaybackProcessor);
