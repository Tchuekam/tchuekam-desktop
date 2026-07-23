/**
 * PostHog Product Analytics & Telemetry for Tchuekam Agent.
 * Tracks usage metrics (sessions, active models, gateway connections, tool calls)
 * while respecting user privacy opt-outs.
 */

const POSTHOG_KEY = "phx_JurRLsvuQkiD4awJxMybMws47BSpuThTQteQSTwkK6YhdkTy";
const POSTHOG_HOST = "https://us.i.posthog.com";

let distinctId = "";
let isEnabled = true;

function getDistinctId(): str {
  if (distinctId) return distinctId;
  const storageKey = "tchuekam_posthog_distinct_id";
  try {
    let saved = localStorage.getItem(storageKey);
    if (!saved) {
      saved = "user_" + Math.random().toString(36).substring(2, 15) + Date.now().toString(36);
      localStorage.setItem(storageKey, saved);
    }
    distinctId = saved;
  } catch {
    distinctId = "anon_" + Math.random().toString(36).substring(2, 10);
  }
  return distinctId;
}

export function initPostHog(): void {
  try {
    const optOut = localStorage.getItem("tchuekam_telemetry_opt_out");
    if (optOut === "true") {
      isEnabled = false;
      return;
    }
    getDistinctId();
    trackEvent("app_launched", {
      url: window.location.href,
      path: window.location.pathname,
      referrer: document.referrer,
      user_agent: navigator.userAgent,
      screen_width: window.innerWidth,
      screen_height: window.innerHeight,
    });
  } catch (err) {
    console.warn("PostHog initialization warning:", err);
  }
}

export function trackEvent(eventName: str, properties: Record<string, any> = {}): void {
  if (!isEnabled) return;
  try {
    const payload = {
      api_key: POSTHOG_KEY,
      event: eventName,
      properties: {
        distinct_id: getDistinctId(),
        $current_url: window.location.href,
        $host: window.location.hostname,
        $pathname: window.location.pathname,
        $browser: navigator.userAgent,
        ...properties,
      },
      timestamp: new Date().toISOString(),
    };

    if (navigator.sendBeacon) {
      const blob = new Blob([JSON.stringify(payload)], { type: "application/json" });
      navigator.sendBeacon(`${POSTHOG_HOST}/capture/`, blob);
    } else {
      fetch(`${POSTHOG_HOST}/capture/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        keepalive: true,
      }).catch(() => {});
    }
  } catch (err) {
    // Silent fail for telemetry
  }
}

export function setTelemetryOptOut(optOut: boolean): void {
  isEnabled = !optOut;
  try {
    localStorage.setItem("tchuekam_telemetry_opt_out", String(optOut));
  } catch {}
}
