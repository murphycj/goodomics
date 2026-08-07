import { client } from "./generated/client.gen";
import { accessToken, invalidateAuthentication } from "./auth";
import { toApiError } from "./errors";

client.setConfig({
  baseUrl: "",
  responseStyle: "data",
  throwOnError: true,
});

client.interceptors.request.use((request) => {
  const token = accessToken();
  if (token) request.headers.set("Authorization", `Bearer ${token}`);
  return request;
});

client.interceptors.response.use((response) => {
  if (response.status === 401 && accessToken()) invalidateAuthentication();
  return response;
});

client.interceptors.error.use((error, response) => toApiError(error, response));

export { client as apiClient };
