import { PtyFrame } from "./types";

export class PtyProtocol {
  public static serialize(frame: PtyFrame): string {
    if (frame.type === "text" && typeof frame.payload === "string") {
      return frame.payload;
    }
    return JSON.stringify({
      type: frame.type,
      payload: frame.payload,
      timestamp: Date.now(),
    });
  }

  public static deserialize(data: string | ArrayBuffer): PtyFrame {
    if (typeof data !== "string") {
      return { type: "binary", payload: data, timestamp: Date.now() };
    }

    try {
      const parsed = JSON.parse(data);
      if (parsed && typeof parsed === "object" && parsed.type) {
        return {
          type: parsed.type,
          payload: parsed.payload,
          timestamp: parsed.timestamp || Date.now(),
        };
      }
    } catch {}

    return { type: "text", payload: data, timestamp: Date.now() };
  }
}
