import { apiClient } from "./client";

export class ChatApiService {
  public static async sendMessage(sessionId: string, message: string): Promise<any> {
    return apiClient.post(`/sessions/${sessionId}/messages`, { message });
  }

  public static async getHistory(sessionId: string): Promise<any[]> {
    return apiClient.get(`/sessions/${sessionId}/history`);
  }
}
