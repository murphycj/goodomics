import { useEffect, useState, useTransition } from "react";
import { changePassword } from "../../api";
import {
  describePasswordPolicy,
  passwordMeetsPolicy,
} from "../../lib/passwordPolicy";
import {
  AppDialog,
  Button,
  DialogFooter,
  Input,
  Label,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../ui";
import { useAuth } from "./AuthProvider";

/** Account profile and password management for the signed-in user. */
export function ProfileDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { logout, session, updateProfile } = useAuth();
  const principal = session?.principal;
  const passwordPolicy = session?.password_policy;
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [profilePending, startProfileTransition] = useTransition();
  const [passwordPending, startPasswordTransition] = useTransition();

  useEffect(() => {
    if (!open) return;
    setDisplayName(principal?.display_name ?? "");
    setEmail(principal?.email ?? "");
    setCurrentPassword("");
    setNewPassword("");
    setConfirmation("");
    setProfileMessage(null);
    setPasswordMessage(null);
  }, [open, principal?.display_name, principal?.email]);

  if (principal?.kind !== "user" || !passwordPolicy) return null;

  return (
    <AppDialog
      description="Manage your account information and password."
      onOpenChange={onOpenChange}
      open={open}
      size="md"
      title="Profile"
    >
        <Tabs defaultValue="account">
          <TabsList className="w-full">
            <TabsTrigger className="flex-1" value="account">
              Account
            </TabsTrigger>
            <TabsTrigger className="flex-1" value="password">
              Password
            </TabsTrigger>
          </TabsList>
          <TabsContent className="mt-4 space-y-4" value="account">
            <div className="space-y-1.5">
              <Label htmlFor="profile-name">Name</Label>
              <Input
                autoComplete="name"
                id="profile-name"
                onChange={(event) => setDisplayName(event.target.value)}
                value={displayName}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="profile-email">Email</Label>
              <Input
                autoComplete="email"
                id="profile-email"
                onChange={(event) => setEmail(event.target.value)}
                type="email"
                value={email}
              />
            </div>
            {profileMessage && (
              <p className="m-0 text-sm text-[#526174]">{profileMessage}</p>
            )}
            <DialogFooter>
              <Button
                disabled={
                  !displayName.trim() || !email.trim() || profilePending
                }
                onClick={() => {
                  setProfileMessage(null);
                  startProfileTransition(async () => {
                    try {
                      await updateProfile(displayName, email);
                      setProfileMessage("Profile updated.");
                    } catch (value) {
                      setProfileMessage(
                        value instanceof Error
                          ? value.message
                          : "Unable to update profile",
                      );
                    }
                  });
                }}
                type="button"
              >
                {profilePending ? "Saving…" : "Save profile"}
              </Button>
            </DialogFooter>
          </TabsContent>
          <TabsContent className="mt-4 space-y-4" value="password">
            <div className="space-y-1.5">
              <Label htmlFor="profile-current-password">Current password</Label>
              <Input
                autoComplete="current-password"
                id="profile-current-password"
                onChange={(event) => setCurrentPassword(event.target.value)}
                type="password"
                value={currentPassword}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="profile-new-password">New password</Label>
              <Input
                autoComplete="new-password"
                id="profile-new-password"
                maxLength={passwordPolicy.max_length ?? undefined}
                minLength={passwordPolicy.min_length}
                onChange={(event) => setNewPassword(event.target.value)}
                type="password"
                value={newPassword}
              />
              <p className="m-0 text-xs text-[#657082]">
                {describePasswordPolicy(passwordPolicy)}
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="profile-confirm-password">Confirm password</Label>
              <Input
                autoComplete="new-password"
                id="profile-confirm-password"
                maxLength={passwordPolicy.max_length ?? undefined}
                minLength={passwordPolicy.min_length}
                onChange={(event) => setConfirmation(event.target.value)}
                type="password"
                value={confirmation}
              />
            </div>
            {passwordMessage && (
              <p className="m-0 text-sm text-[#526174]">{passwordMessage}</p>
            )}
            <DialogFooter>
              <Button
                disabled={
                  !currentPassword ||
                  newPassword !== confirmation ||
                  !passwordMeetsPolicy(newPassword, passwordPolicy) ||
                  passwordPending
                }
                onClick={() => {
                  setPasswordMessage(null);
                  startPasswordTransition(async () => {
                    try {
                      await changePassword(currentPassword, newPassword);
                      onOpenChange(false);
                      logout();
                    } catch (value) {
                      setPasswordMessage(
                        value instanceof Error
                          ? value.message
                          : "Unable to update password",
                      );
                    }
                  });
                }}
                type="button"
              >
                {passwordPending ? "Updating…" : "Update password"}
              </Button>
            </DialogFooter>
          </TabsContent>
        </Tabs>
    </AppDialog>
  );
}
