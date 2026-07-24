import { create } from "zustand";
import { AuthService } from "../lib/api/auth";
import { User } from "../lib/api/types";

export interface AuthState {
  sessionToken: string | null;
  refreshToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  setCredentials: (token: string, refreshToken?: string, user?: User) => Promise<void>;
  logout: () => Promise<void>;
  loadPersistedToken: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  sessionToken: null,
  refreshToken: null,
  user: null,
  isAuthenticated: false,

  setCredentials: async (token, refreshToken, user) => {
    await AuthService.setSessionToken(token);
    if (refreshToken) {
      await AuthService.setRefreshToken(refreshToken);
    }
    set({
      sessionToken: token,
      refreshToken: refreshToken || null,
      user: user || null,
      isAuthenticated: true,
    });
  },

  logout: async () => {
    await AuthService.clearCredentials();
    set({
      sessionToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
    });
  },

  loadPersistedToken: async () => {
    const token = await AuthService.getSessionToken();
    const refresh = await AuthService.getRefreshToken();
    if (token) {
      set({
        sessionToken: token,
        refreshToken: refresh,
        isAuthenticated: true,
      });
    }
  },
}));
