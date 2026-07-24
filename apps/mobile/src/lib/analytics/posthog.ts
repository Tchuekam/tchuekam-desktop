import { analyticsQueue } from "./queue";

export type EventName =
  | "mobile_app_launched"
  | "mobile_session_started"
  | "mobile_session_restored"
  | "mobile_connected"
  | "mobile_disconnected"
  | "pty_session_created"
  | "pty_session_closed"
  | "api_request_failed"
  | "api_request_success"
  | "mobile_crash"
  | "mobile_background"
  | "mobile_foreground";

export function trackEvent(eventName: EventName, properties: Record<string, any> = {}): void {
  analyticsQueue.enqueue(eventName, properties);
}
