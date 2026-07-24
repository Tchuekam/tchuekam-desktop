import axios, { AxiosInstance, AxiosRequestConfig } from "axios";
import { EndpointResolver, API_CONFIG } from "./config";
import { AuthService } from "./auth";
import { ApiError, AuthenticationError, NetworkError, TimeoutError } from "./errors";

export class ApiClient {
  private instance: AxiosInstance;

  constructor() {
    this.instance = axios.create({
      baseURL: EndpointResolver.getBaseUrl(),
      timeout: API_CONFIG.timeoutMs,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
    });

    this.setupInterceptors();
  }

  private setupInterceptors(): void {
    // Request Interceptor: Attach Auth Token & BaseURL
    this.instance.interceptors.request.use(async (config) => {
      config.baseURL = EndpointResolver.getBaseUrl();
      const token = await AuthService.getSessionToken();
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Response Interceptor: Normalize Errors & Endpoint Failover
    this.instance.interceptors.response.use(
      (response) => response,
      async (error) => {
        if (!error.response) {
          // Network connection failed or timed out — attempt primary failover
          EndpointResolver.markPrimaryFailed();

          if (error.code === "ECONNABORTED") {
            throw new TimeoutError("API request timed out after " + API_CONFIG.timeoutMs + "ms");
          }
          throw new NetworkError("Unable to reach server. Please check connection.");
        }

        const status = error.response.status;
        const message = error.response.data?.error?.message || error.message;

        if (status === 401 || status === 403) {
          await AuthService.clearCredentials();
          throw new AuthenticationError(message, error.response.data);
        }

        throw new ApiError(message, status, "API_ERROR_" + status, error.response.data);
      }
    );
  }

  public async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.get<T>(url, config);
    return response.data;
  }

  public async post<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.post<T>(url, data, config);
    return response.data;
  }

  public async put<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.put<T>(url, data, config);
    return response.data;
  }

  public async patch<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.patch<T>(url, data, config);
    return response.data;
  }

  public async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.delete<T>(url, config);
    return response.data;
  }
}

export const apiClient = new ApiClient();
