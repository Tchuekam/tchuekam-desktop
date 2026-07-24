import { PtyFrame } from "./types";

export class PendingFrameQueue {
  private queue: PtyFrame[] = [];
  private maxCapacity = 100;

  public enqueue(frame: PtyFrame): void {
    if (this.queue.length >= this.maxCapacity) {
      this.queue.shift(); // Drop oldest frame when capacity is reached
    }
    this.queue.push(frame);
  }

  public flush(sendFn: (frame: PtyFrame) => void): void {
    while (this.queue.length > 0) {
      const frame = this.queue.shift();
      if (frame) {
        sendFn(frame);
      }
    }
  }

  public clear(): void {
    this.queue = [];
  }

  public size(): number {
    return this.queue.length;
  }
}
