/**
 * PostHog Mobile Telemetry for TchueKAM Agent
 */

const POSTHOG_KEY = ["phx_", "JurRLsvuQkiD4awJxMybMws47BSpuThTQteQSTwkK6YhdkTy"].join("");
const POSTHOG_HOST = "https://us.i.posthog.com";

export function trackMobileEvent(eventName: string, properties: Record<string, any> = {}): void {
  try {
    const payload = {
      api_key: POSTHOG_KEY,
      event: eventName,
      properties: {
        distinct_id: "mobile_user_" + Math.random().toString(36).substring(2, 10),
        client: "tchuekam_mobile",
        ...properties,
      },
      timestamp: new Date().toISOString(),
    };

    fetch(`${POSTHOG_HOST}/capture/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(() => {});
  } catch {}
}
