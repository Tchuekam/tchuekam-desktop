import { create } from "zustand";
import { ModelItem } from "../lib/api/types";

export interface AgentState {
  activeModel: string;
  availableModels: ModelItem[];
  temperature: number;
  reasoningMode: boolean;
  setActiveModel: (model: string) => void;
  setAvailableModels: (models: ModelItem[]) => void;
  setTemperature: (temp: number) => void;
  setReasoningMode: (enabled: boolean) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  activeModel: "google/gemini-flash-1.5-8b",
  availableModels: [
    { id: "google/gemini-flash-1.5-8b", name: "Gemini 1.5 Flash 8B", provider: "google" },
    { id: "anthropic/claude-3-5-sonnet", name: "Claude 3.5 Sonnet", provider: "anthropic" },
    { id: "openai/gpt-4o", name: "GPT-4o", provider: "openai" },
  ],
  temperature: 0.7,
  reasoningMode: true,

  setActiveModel: (activeModel) => set({ activeModel }),
  setAvailableModels: (availableModels) => set({ availableModels }),
  setTemperature: (temperature) => set({ temperature }),
  setReasoningMode: (reasoningMode) => set({ reasoningMode }),
}));
