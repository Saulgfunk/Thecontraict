import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths };
export type Schemas = components["schemas"];

export interface ApiClientOptions {
  baseUrl: string;
  /** Returns auth headers for each request (bearer token or dev user header). */
  getHeaders: () => Promise<Record<string, string>> | Record<string, string>;
}

export function createApiClient({ baseUrl, getHeaders }: ApiClientOptions) {
  const client = createClient<paths>({ baseUrl });
  client.use({
    async onRequest({ request }) {
      const headers = await getHeaders();
      for (const [key, value] of Object.entries(headers)) {
        request.headers.set(key, value);
      }
      return request;
    },
  });
  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;

/** Error thrown by `unwrap` when the API returns a non-2xx response. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : `API error ${status}`);
  }
}

/** Turn an openapi-fetch result into data or a thrown ApiError. */
export async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await promise;
  if (!response.ok) {
    const detail =
      error && typeof error === "object" && "detail" in error
        ? (error as { detail: unknown }).detail
        : error;
    throw new ApiError(response.status, detail);
  }
  return data as T;
}
