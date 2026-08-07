export const ACCESS_TOKEN_KEY = "goodomics.access_token";
export const AUTH_INVALID_EVENT = "goodomics:auth-invalid";

/** Return the current browser bearer token, if authentication is active. */
export function accessToken() {
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

/** Clear an invalid token and notify the application session provider. */
export function invalidateAuthentication() {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.dispatchEvent(new Event(AUTH_INVALID_EVENT));
}
