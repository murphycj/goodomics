import { Link } from "@tanstack/react-router";
import { LogIn, LogOut, Settings, UserRound, Users } from "lucide-react";
import { useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui";
import { useAuth } from "./AuthProvider";
import { ProfileDialog } from "./ProfileDialog";

/** Header account avatar and actions for anonymous and managed-user modes. */
export function UserMenu() {
  const { logout, session } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);
  const principal = session?.principal;

  if (!principal || principal.kind === "local") return null;

  const initials = accountInitials(principal.display_name, principal.email);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            aria-label={
              principal.kind === "user"
                ? "Open account menu"
                : "Open sign in menu"
            }
            className="inline-flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-full border border-[#3b4541] bg-[#1b1b1b] text-sm font-semibold text-[#e9f7ef] transition-colors hover:border-[#58c98a] hover:bg-[#21332a] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#58c98a]"
            type="button"
          >
            {principal.kind === "user" ? initials : <UserRound size={17} />}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[240px]">
          {principal.kind === "anonymous" ? (
            <DropdownMenuItem asChild>
              <Link to="/login">
                <LogIn size={16} /> Sign in
              </Link>
            </DropdownMenuItem>
          ) : (
            <>
              <DropdownMenuLabel className="normal-case">
                <span className="block truncate text-sm font-semibold normal-case text-[#1d2430]">
                  {principal.display_name}
                </span>
                <span className="block truncate text-xs font-normal normal-case text-[#657082]">
                  {principal.email}
                </span>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setProfileOpen(true)}>
                <Settings size={16} /> Profile
              </DropdownMenuItem>
              {principal.is_admin && (
                <DropdownMenuItem asChild>
                  <Link to="/admin/users">
                    <Users size={16} /> User management
                  </Link>
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={logout}>
                <LogOut size={16} /> Sign out
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      {principal.kind === "user" && (
        <ProfileDialog open={profileOpen} onOpenChange={setProfileOpen} />
      )}
    </>
  );
}

/* Function to compute the initials for a user account based on the display name or email. Returns a two-character string representing the initials. */
function accountInitials(displayName: string | null, email: string | null) {
  const words = (displayName ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length > 1)
    return `${words[0][0]}${words.at(-1)![0]}`.toUpperCase();
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (email?.slice(0, 2) || "U").toUpperCase();
}
