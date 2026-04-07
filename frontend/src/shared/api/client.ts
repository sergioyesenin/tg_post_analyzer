type ApiClientOptions = {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
};

export class ApiError extends Error {
  status: number;
  payload?: unknown;

  constructor(message: string, status: number, payload?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
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

  async post<T>(path: string, body?: unknown, init?: RequestOptions) {
    return this.request<T>(path, {
      ...init,
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  async put<T>(path: string, body?: unknown, init?: RequestOptions) {
    return this.request<T>(path, {
      ...init,
      method: 'PUT',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  async patch<T>(path: string, body?: unknown, init?: RequestOptions) {
    return this.request<T>(path, {
      ...init,
      method: 'PATCH',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  async delete<T>(path: string, init?: RequestOptions) {
    return this.request<T>(path, {
      ...init,
      method: 'DELETE',
    });
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
      credentials: init.credentials ?? 'same-origin',
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
      const payload = await this.readErrorPayload(response);
      const message = this.resolveErrorMessage(response.status, payload);
      throw new ApiError(message, response.status, payload);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  }

  private async readErrorPayload(response: Response): Promise<unknown> {
    const contentType = response.headers.get('content-type') ?? '';

    if (contentType.includes('application/json')) {
      try {
        return await response.json();
      } catch {
        return null;
      }
    }

    try {
      const text = await response.text();
      return text || null;
    } catch {
      return null;
    }
  }

  private resolveErrorMessage(status: number, payload: unknown): string {
    if (payload && typeof payload === 'object') {
      const message =
        readString((payload as Record<string, unknown>).message) ??
        readString((payload as Record<string, unknown>).detail) ??
        readString((payload as Record<string, unknown>).error);

      if (message) {
        return message;
      }
    }

    if (typeof payload === 'string' && payload.trim()) {
      return payload;
    }

    return `API request failed with status ${status}`;
  }
}

export const apiClient = new ApiClient();

function readString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}
