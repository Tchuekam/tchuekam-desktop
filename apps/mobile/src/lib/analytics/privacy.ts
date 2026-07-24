import { useSettingsStore } from "../../store/settingsStore";

export class PrivacyManager {
  public static isTelemetryEnabled(): boolean {
    const { telemetryOptOut, analyticsEnabled } = useSettingsStore.getState();
    return !telemetryOptOut && analyticsEnabled;
  }
}
