import { z } from "zod";

export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: any;
  };
}

export const UserSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  name: z.string().optional(),
  role: z.string().default("user"),
});

export type User = z.infer<typeof UserSchema>;

export const AuthResponseSchema = z.object({
  session_token: z.string(),
  refresh_token: z.string().optional(),
  user: UserSchema.optional(),
});

export type AuthResponse = z.infer<typeof AuthResponseSchema>;

export const ModelSchema = z.object({
  id: z.string(),
  name: z.string(),
  provider: z.string(),
  description: z.string().optional(),
  supportsReasoning: z.boolean().optional(),
});

export type ModelItem = z.infer<typeof ModelSchema>;

export const SessionSchema = z.object({
  session_id: z.string(),
  created_at: z.string(),
  model: z.string(),
  title: z.string().optional(),
  status: z.string().default("active"),
});

export type Session = z.infer<typeof SessionSchema>;
