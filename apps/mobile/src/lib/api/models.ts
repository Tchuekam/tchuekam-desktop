import { apiClient } from "./client";
import { ModelItem, ModelSchema } from "./types";

export class ModelsApiService {
  public static async getAvailableModels(): Promise<ModelItem[]> {
    try {
      const data = await apiClient.get<any[]>("/models");
      return data.map((item) => ModelSchema.parse(item));
    } catch {
      // Static fallback list if backend endpoint is initializing
      return [
        { id: "google/gemini-flash-1.5-8b", name: "Gemini 1.5 Flash 8B", provider: "google" },
        { id: "anthropic/claude-3-5-sonnet", name: "Claude 3.5 Sonnet", provider: "anthropic" },
        { id: "openai/gpt-4o", name: "GPT-4o", provider: "openai" },
      ];
    }
  }
}
