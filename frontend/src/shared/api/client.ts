type ApiClientOptions = {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

type AuthMode = 'required' | 'optional' | 'none';

export type RequestOptions = RequestInit & {
  authMode?: AuthMode;
  retryOnUnauthorized?: boolean;
};

type ApiClientAuthConfig = {
  getAccessToken?: () => string | null;
  refreshAccessToken?: () => Promise<string | null>;
  onUnauthorized?: () => void;
};

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private authConfig: ApiClientAuthConfig = {};

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? import.meta.env.VITE_API_BASE_URL ?? '';
    this.fetchImpl =
      options.fetchImpl ?? (typeof window !== 'undefined' ? window.fetch.bind(window) : fetch);
  }

  configureAuth(config: ApiClientAuthConfig) {
    this.authConfig = config;
  }

  async get<T>(path: string, init?: RequestOptions) {
    return this.request<T>(path, { ...init, method: 'GET' });
  }

  async request<T>(path: string, init: RequestOptions = {}) {
    const response = await this.execute(path, init);

    if (response.status === 401 && init.retryOnUnauthorized !== false) {
      const refreshedToken = await this.authConfig.refreshAccessToken?.();
      if (refreshedToken) {
        const retriedResponse = await this.execute(path, {
          ...init,
          retryOnUnauthorized: false,
        });
        return this.parseResponse<T>(retriedResponse);
      }

      this.authConfig.onUnauthorized?.();
    }

    return this.parseResponse<T>(response);
  }

  private async execute(path: string, init: RequestOptions) {
    const accessToken =
      init.authMode === 'none' ? null : (this.authConfig.getAccessToken?.() ?? null);

    return this.fetchImpl(`${this.baseUrl}${path}`, {
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...init.headers,
      },
      ...init,
    });
  }

  private async parseResponse<T>(response: Response) {
    if (!response.ok) {
      throw new ApiError(`API request failed with status ${response.status}`, response.status);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  }
}

export const apiClient = new ApiClient();
