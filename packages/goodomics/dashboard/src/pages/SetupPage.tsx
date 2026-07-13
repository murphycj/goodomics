import { useNavigate } from "@tanstack/react-router";
import { ShieldCheck } from "lucide-react";
import { useState, useTransition } from "react";
import { useAuth } from "../components/auth/AuthProvider";
import {
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Page,
} from "../components/ui";
import {
  DEFAULT_PASSWORD_POLICY,
  describePasswordPolicy,
} from "../lib/passwordPolicy";

/** First-run installation setup for creating the initial full-access admin. */
export function SetupPage() {
  const { session, setupAdmin } = useAuth();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const passwordPolicy = session?.password_policy ?? DEFAULT_PASSWORD_POLICY;

  return (
    <Page
      title="Set up Goodomics"
      subtitle="Create the installation administrator to finish securing this server."
    >
      <Card className="mx-auto max-w-md">
        <CardContent>
          <div className="mb-5 flex items-start gap-3 rounded-lg border border-[#cce8d8] bg-[#f0faf4] p-3 text-sm text-[#245f3f]">
            <ShieldCheck className="mt-0.5 shrink-0" size={18} />
            <p className="m-0">
              This first account can manage every project, user, role, and
              installation-level operation. Initial setup closes after the
              account is created.
            </p>
          </div>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              setError(null);
              if (password !== passwordConfirmation) {
                setError("Passwords do not match");
                return;
              }
              startTransition(async () => {
                try {
                  await setupAdmin(displayName, email, password);
                  await navigate({ to: "/" });
                } catch (value) {
                  setError(
                    value instanceof Error
                      ? value.message
                      : "Unable to complete setup",
                  );
                }
              });
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="setup-name">Name</Label>
              <Input
                autoComplete="name"
                id="setup-name"
                onChange={(event) => setDisplayName(event.target.value)}
                required
                value={displayName}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="setup-email">Email</Label>
              <Input
                autoComplete="email"
                id="setup-email"
                onChange={(event) => setEmail(event.target.value)}
                required
                type="email"
                value={email}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="setup-password">Password</Label>
              <Input
                autoComplete="new-password"
                id="setup-password"
                maxLength={passwordPolicy.max_length ?? undefined}
                minLength={passwordPolicy.min_length}
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
              <p className="m-0 text-xs text-[#657082]">
                {describePasswordPolicy(passwordPolicy)}
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="setup-password-confirmation">
                Confirm password
              </Label>
              <Input
                autoComplete="new-password"
                id="setup-password-confirmation"
                maxLength={passwordPolicy.max_length ?? undefined}
                minLength={passwordPolicy.min_length}
                onChange={(event) =>
                  setPasswordConfirmation(event.target.value)
                }
                required
                type="password"
                value={passwordConfirmation}
              />
            </div>
            {error && <p className="text-sm text-[#b42318]">{error}</p>}
            <Button className="w-full" disabled={isPending} type="submit">
              {isPending ? "Creating administrator…" : "Create administrator"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </Page>
  );
}
