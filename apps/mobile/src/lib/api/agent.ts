import { apiClient } from "./client";
import { Session, SessionSchema } from "./types";

export class AgentApiService {
  public static async getSessions(): Promise<Session[]> {
    const data = await apiClient.get<any[]>("/sessions");
    return data.map((item) => SessionSchema.parse(item));
  }

  public static async createSession(model?: string): Promise<Session> {
    const data = await apiClient.post<any>("/sessions", { model });
    return SessionSchema.parse(data);
  }

  public static async deleteSession(sessionId: string): Promise<void> {
    await apiClient.delete(`/sessions/${sessionId}`);
  }
}
