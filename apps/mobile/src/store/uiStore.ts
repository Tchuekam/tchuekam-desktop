import { create } from "zustand";

export interface UiState {
  sidebarOpen: boolean;
  currentScreen: string;
  keyboardVisible: boolean;
  modelPickerModalOpen: boolean;
  voiceModeModalOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  setCurrentScreen: (screen: string) => void;
  setKeyboardVisible: (visible: boolean) => void;
  setModelPickerModalOpen: (open: boolean) => void;
  setVoiceModeModalOpen: (open: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: false,
  currentScreen: "assistant",
  keyboardVisible: false,
  modelPickerModalOpen: false,
  voiceModeModalOpen: false,

  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  setCurrentScreen: (currentScreen) => set({ currentScreen }),
  setKeyboardVisible: (keyboardVisible) => set({ keyboardVisible }),
  setModelPickerModalOpen: (modelPickerModalOpen) => set({ modelPickerModalOpen }),
  setVoiceModeModalOpen: (voiceModeModalOpen) => set({ voiceModeModalOpen }),
}));
