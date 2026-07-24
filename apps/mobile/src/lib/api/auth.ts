import * as SecureStore from "expo-secure-store";
import { AuthenticationError } from "./errors";

const TOKEN_KEY = "tchuekam_session_token";
const REFRESH_KEY = "tchuekam_refresh_token";

export class AuthService {
  public static async getSessionToken(): Promise<string | null> {
    try {
      return await SecureStore.getItemAsync(TOKEN_KEY);
    } catch {
      return null;
    }
  }

  public static async setSessionToken(token: string): Promise<void> {
    try {
      await SecureStore.setItemAsync(TOKEN_KEY, token);
    } catch (err) {
      console.warn("SecureStore setItem failed:", err);
    }
  }

  public static async getRefreshToken(): Promise<string | null> {
    try {
      return await SecureStore.getItemAsync(REFRESH_KEY);
    } catch {
      return null;
    }
  }

  public static async setRefreshToken(token: string): Promise<void> {
    try {
      await SecureStore.setItemAsync(REFRESH_KEY, token);
    } catch (err) {
      console.warn("SecureStore setRefreshToken failed:", err);
    }
  }

  public static async clearCredentials(): Promise<void> {
    try {
      await SecureStore.deleteItemAsync(TOKEN_KEY);
      await SecureStore.deleteItemAsync(REFRESH_KEY);
    } catch {}
  }

  public static async requireToken(): Promise<string> {
    const token = await this.getSessionToken();
    if (!token) {
      throw new AuthenticationError("No session token found in secure storage");
    }
    return token;
  }
}
