/*
 * Adapted from KoljaB/RealtimeVoiceChat (Apache License 2.0)
 * https://github.com/KoljaB/RealtimeVoiceChat
 *
 * Upgraded for TchuekaM JARVIS Core: converts Float32 microphone samples to
 * Int16 PCM and emits lightweight frame RMS energy alongside the transferable
 * buffer for low-latency barge-in and live UI metering.
 */
class PCMWorkletProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length > 0) {
      const int16 = new Int16Array(channel.length);
      let sumSq = 0;
      for (let i = 0; i < channel.length; i++) {
        let s = channel[i];
        if (s < -1) s = -1;
        else if (s > 1) s = 1;
        sumSq += s * s;
        int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      const rms = Math.sqrt(sumSq / channel.length);
      this.port.postMessage({ buffer: int16.buffer, rms }, [int16.buffer]);
    }
    return true;
  }
}

registerProcessor('pcm-worklet-processor', PCMWorkletProcessor);
