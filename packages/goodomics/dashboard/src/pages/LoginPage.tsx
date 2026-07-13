import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAuth } from "../components/auth/AuthProvider";
import {
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Page,
} from "../components/ui";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  return (
    <Page title="Sign in" subtitle="Use your Goodomics installation account.">
      <Card className="mx-auto max-w-md">
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              setSubmitting(true);
              setError(null);
              void login(email, password)
                .then(() => navigate({ to: "/" }))
                .catch((value) =>
                  setError(
                    value instanceof Error ? value.message : "Login failed",
                  ),
                )
                .finally(() => setSubmitting(false));
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="login-email">Email</Label>
              <Input
                autoComplete="email"
                id="login-email"
                onChange={(event) => setEmail(event.target.value)}
                required
                type="email"
                value={email}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="login-password">Password</Label>
              <Input
                autoComplete="current-password"
                id="login-password"
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </div>
            {error && <p className="text-sm text-[#b42318]">{error}</p>}
            <Button className="w-full" disabled={submitting} type="submit">
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </Page>
  );
}
