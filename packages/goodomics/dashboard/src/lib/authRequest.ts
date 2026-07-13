export const ACCESS_TOKEN_KEY = "goodomics.access_token";
export const AUTH_INVALID_EVENT = "goodomics:auth-invalid";

export function accessToken() {
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

/**
 * Perform a fetch request with the Authorization header set if an access token is available.
 *
 * @param input - The resource that you wish to fetch.
 * @param init - An object containing any custom settings that you want to apply to the request.
 * @returns The fetch response.
 */
export async function apiFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
) {
  const headers = new Headers(init.headers);
  const token = accessToken();

  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(input, { ...init, headers });

  if (response.status === 401 && token) {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.dispatchEvent(new Event(AUTH_INVALID_EVENT));
  }

  return response;
}
