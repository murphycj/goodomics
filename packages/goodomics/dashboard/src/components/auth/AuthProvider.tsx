import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { z } from "zod";
import { queryClient } from "../../lib/queryClient";
import { passwordPolicySchema } from "../../lib/passwordPolicy";
import {
  ACCESS_TOKEN_KEY,
  AUTH_INVALID_EVENT,
  apiFetch,
} from "../../lib/authRequest";

// Schemas for validating the structure of the principal and session objects returned by the API.
const principalSchema = z.object({
  kind: z.enum(["local", "anonymous", "user"]),
  user_id: z.string().nullable(),
  email: z.string().nullable(),
  display_name: z.string().nullable(),
  is_admin: z.boolean(),
  must_change_password: z.boolean(),
  is_authenticated: z.boolean(),
});

const sessionSchema = z.object({
  principal: principalSchema,
  memberships: z.array(z.record(z.string(), z.unknown())),
  permissions: z.record(z.string(), z.array(z.string())),
  auth_enabled: z.boolean(),
  signup_enabled: z.boolean(),
  setup_required: z.boolean(),
  password_policy: passwordPolicySchema,
});

export type Session = z.infer<typeof sessionSchema>;

// Context value type for authentication-related state and actions.
type AuthContextValue = {
  session: Session | null;
  isLoading: boolean;
  error: Error | null;
  login: (email: string, password: string) => Promise<void>;
  setupAdmin: (
    displayName: string,
    email: string,
    password: string,
  ) => Promise<void>;
  updateProfile: (displayName: string, email: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
  can: (permission: string, projectId?: string) => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  // Function to refresh the session by fetching the current user's session data from the API. Updates the session state and handles loading and error states.
  const refresh = useCallback(async () => {
    setIsLoading(true);

    try {
      const response = await apiFetch("/api/v1/auth/me");
      if (!response.ok)
        throw new Error(`Session request failed: ${response.status}`);
      setSession(sessionSchema.parse(await response.json()));
      setError(null);
    } catch (value) {
      setSession(null);
      setError(
        value instanceof Error ? value : new Error("Unable to load session"),
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Effect to refresh the session on component mount and handle the AUTH_INVALID_EVENT to refresh the session when the access token becomes invalid.
  useEffect(() => {
    void refresh();
    const onInvalid = () => {
      queryClient.clear();
      void refresh();
    };
    window.addEventListener(AUTH_INVALID_EVENT, onInvalid);
    return () => window.removeEventListener(AUTH_INVALID_EVENT, onInvalid);
  }, [refresh]);

  // Function to log in a user by sending credentials to the API, storing the access token, and refreshing the session.
  const login = useCallback(
    async (email: string, password: string) => {
      const response = await apiFetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
          body && typeof body === "object" && "detail" in body
            ? String(body.detail)
            : "Login failed",
        );
      }
      const token = z
        .object({ access_token: z.string() })
        .parse(await response.json());
      queryClient.clear();
      window.localStorage.setItem(ACCESS_TOKEN_KEY, token.access_token);
      await refresh();
    },
    [refresh],
  );

  // Function to set up an admin user by sending the necessary information to the API, storing the access token, and refreshing the session.
  const setupAdmin = useCallback(
    async (displayName: string, email: string, password: string) => {
      const response = await apiFetch("/api/v1/auth/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: displayName, email, password }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
          body && typeof body === "object" && "detail" in body
            ? String(body.detail)
            : "Unable to complete setup",
        );
      }
      const token = z
        .object({ access_token: z.string() })
        .parse(await response.json());
      queryClient.clear();
      window.localStorage.setItem(ACCESS_TOKEN_KEY, token.access_token);
      await refresh();
    },
    [refresh],
  );

  // Function to update the current user's profile by sending the updated display name and email to the API, storing the new access token, and refreshing the session.
  const updateProfile = useCallback(
    async (displayName: string, email: string) => {
      const response = await apiFetch("/api/v1/auth/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: displayName, email }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);

        throw new Error(
          body && typeof body === "object" && "detail" in body
            ? String(body.detail)
            : "Unable to update profile",
        );
      }

      const token = z
        .object({ access_token: z.string() })
        .parse(await response.json());
      queryClient.clear();
      window.localStorage.setItem(ACCESS_TOKEN_KEY, token.access_token);
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(() => {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    queryClient.clear();
    void refresh();
  }, [refresh]);

  // Function to check if the current user has a specific permission for a given project. Returns true if the user has the permission, false otherwise.
  const can = useCallback(
    (permission: string, projectId?: string) => {
      if (!session) return false;
      if (session.principal.kind === "local" || session.principal.is_admin)
        return true;
      if (!projectId) return false;
      return session.permissions[projectId]?.includes(permission) ?? false;
    },
    [session],
  );

  const value = useMemo(
    () => ({
      session,
      isLoading,
      error,
      login,
      setupAdmin,
      updateProfile,
      logout,
      refresh,
      can,
    }),
    [
      session,
      isLoading,
      error,
      login,
      setupAdmin,
      updateProfile,
      logout,
      refresh,
      can,
    ],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}
