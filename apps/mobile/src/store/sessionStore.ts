import { create } from "zustand";
import { Session } from "../lib/api/types";

export interface SessionState {
  currentSessionId: string | null;
  sessionHistory: Session[];
  setCurrentSessionId: (id: string | null) => void;
  setSessionHistory: (history: Session[]) => void;
  addSession: (session: Session) => void;
  removeSession: (sessionId: string) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  currentSessionId: null,
  sessionHistory: [],

  setCurrentSessionId: (currentSessionId) => set({ currentSessionId }),
  setSessionHistory: (sessionHistory) => set({ sessionHistory }),

  addSession: (session) =>
    set((state) => ({
      sessionHistory: [session, ...state.sessionHistory.filter((s) => s.session_id !== session.session_id)],
      currentSessionId: session.session_id,
    })),

  removeSession: (sessionId) =>
    set((state) => ({
      sessionHistory: state.sessionHistory.filter((s) => s.session_id !== sessionId),
      currentSessionId: state.currentSessionId === sessionId ? null : state.currentSessionId,
    })),
}));
