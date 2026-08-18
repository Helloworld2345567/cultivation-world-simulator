/**
 * HTTP API Client
 * 封装基础的 fetch 请求
 */

// 使用环境变量作为 API 基础路径，如果没有配置则默认为空（相对路径）
const API_BASE = import.meta.env.VITE_API_TARGET || '';
const DEFAULT_TIMEOUT_MS = 30000;
const REQUEST_TIMEOUT_REASON = 'cws-request-timeout';
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
let csrfToken: string | null = null;
let adminAuthRequiredHandler: (() => void) | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

export function setAdminAuthRequiredHandler(handler: (() => void) | null): void {
  adminAuthRequiredHandler = handler;
}

function getApiErrorCode(errorData: unknown): string | null {
  if (!errorData || typeof errorData !== 'object') return null;
  if ('error' in errorData) {
    const error = (errorData as { error?: unknown }).error;
    if (error && typeof error === 'object' && 'code' in error) {
      const code = (error as { code?: unknown }).code;
      if (typeof code === 'string') return code;
    }
  }
  if (!('detail' in errorData)) return null;
  const detail = (errorData as { detail?: unknown }).detail;
  if (!detail || typeof detail !== 'object' || !('code' in detail)) return null;
  const code = (detail as { code?: unknown }).code;
  return typeof code === 'string' ? code : null;
}

function addCsrfHeader(headers: HeadersInit | undefined, method: string): HeadersInit | undefined {
  if (!csrfToken || SAFE_METHODS.has(method)) {
    return headers;
  }

  if (headers instanceof Headers) {
    const nextHeaders = new Headers(headers);
    nextHeaders.set('X-CSRF-Token', csrfToken);
    return nextHeaders;
  }

  if (Array.isArray(headers)) {
    return [...headers, ['X-CSRF-Token', csrfToken]];
  }

  return {
    ...headers,
    'X-CSRF-Token': csrfToken,
  };
}

export interface HttpRequestOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

export class ApiError extends Error {
  public status: number;
  public response: { data: unknown };

  constructor(status: number, message: string, responseData?: unknown) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
    this.response = { data: responseData || {} };
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  requestOptions: HttpRequestOptions = {},
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const method = (options.method ?? 'GET').toUpperCase();
  const controller = new AbortController();
  const timeoutMs = requestOptions.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  let didTimeout = false;
  const callerSignal = requestOptions.signal ?? options.signal;
  const abortFromCaller = () => {
    controller.abort(callerSignal?.reason);
  };
  const timeout = globalThis.setTimeout(() => {
    didTimeout = true;
    controller.abort(REQUEST_TIMEOUT_REASON);
  }, timeoutMs);

  if (callerSignal) {
    if (callerSignal.aborted) {
      abortFromCaller();
    } else {
      callerSignal.addEventListener('abort', abortFromCaller, { once: true });
    }
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      credentials: options.credentials ?? 'include',
      headers: addCsrfHeader(options.headers, method),
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError' && didTimeout) {
      throw new ApiError(408, `Request timed out after ${Math.round(timeoutMs / 1000)}s`);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
    callerSignal?.removeEventListener('abort', abortFromCaller);
  }

  if (!response.ok) {
    // 尝试解析错误响应的 JSON
    let errorData: unknown = null;
    let errorMessage = `Request failed: ${response.statusText}`;
    
    try {
      errorData = await response.json();
      if (errorData && typeof errorData === 'object' && 'error' in errorData) {
        const publicError = (errorData as { error?: unknown }).error;
        if (
          publicError &&
          typeof publicError === 'object' &&
          'message' in publicError &&
          typeof (publicError as { message?: unknown }).message === 'string'
        ) {
          errorMessage = (publicError as { message: string }).message;
        }
      } else if (errorData && typeof errorData === 'object' && 'detail' in errorData) {
        // Keep compatibility with settings and older FastAPI errors.
        const detail = (errorData as { detail?: unknown }).detail;
        if (typeof detail === 'string') {
          errorMessage = detail;
        } else if (
          detail &&
          typeof detail === 'object' &&
          'message' in detail &&
          typeof (detail as { message?: unknown }).message === 'string'
        ) {
          errorMessage = (detail as { message: string }).message;
        }
      }
    } catch {
      // 如果解析失败，使用默认错误消息
    }

    if (response.status === 401 && getApiErrorCode(errorData) === 'ADMIN_AUTH_REQUIRED') {
      adminAuthRequiredHandler?.();
    }
    
    throw new ApiError(response.status, errorMessage, errorData);
  }

  // 假设后端总是返回 JSON
  const data: unknown = await response.json();
  if (
    data &&
    typeof data === 'object' &&
    'ok' in data &&
    data.ok === true &&
    'data' in data
  ) {
    return (data as { data: T }).data;
  }
  return data as T;
}

export const httpClient = {
  get<T>(path: string) {
    return request<T>(path, { method: 'GET' });
  },

  post<T>(path: string, body: unknown, options?: HttpRequestOptions) {
    return request<T>(path, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    }, options);
  },

  patch<T>(path: string, body: unknown, options?: HttpRequestOptions) {
    return request<T>(path, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    }, options);
  },

  put<T>(path: string, body: unknown, options?: HttpRequestOptions) {
    return request<T>(path, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    }, options);
  },

  delete<T>(path: string) {
    return request<T>(path, { method: 'DELETE' });
  }
};

