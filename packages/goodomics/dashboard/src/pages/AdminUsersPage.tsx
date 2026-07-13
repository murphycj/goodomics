import { useMutation, useQuery } from "@tanstack/react-query";
import { Navigate } from "@tanstack/react-router";
import { ShieldCheck, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import {
  addProjectMember,
  createInstallationUser,
  deleteProjectMember,
  listProjectRoles,
  listProjects,
  listUserMemberships,
  listUsers,
  patchInstallationUser,
  updateProjectMember,
} from "../api";
import { useAuth } from "../components/auth/AuthProvider";
import {
  AppDialog,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Page,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrap,
} from "../components/ui";
import {
  DEFAULT_PASSWORD_POLICY,
  describePasswordPolicy,
  passwordMeetsPolicy,
} from "../lib/passwordPolicy";
import { queryClient } from "../lib/queryClient";

/** Installation-admin surface for users, account state, and project roles. */
export function AdminUsersPage() {
  const { session } = useAuth();
  const passwordPolicy = session?.password_policy ?? DEFAULT_PASSWORD_POLICY;
  const [selectedUserId, setSelectedUserId] = useState("");
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [projectId, setProjectId] = useState("");
  const [roleId, setRoleId] = useState("");

  const users = useQuery({
    queryKey: ["installation-users"],
    queryFn: listUsers,
    enabled: Boolean(session?.principal.is_admin),
  });
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
    enabled: Boolean(session?.principal.is_admin),
  });
  const selectedUser = (users.data ?? []).find(
    (user) => user.user_id === selectedUserId,
  );
  const memberships = useQuery({
    queryKey: ["admin-user-memberships", selectedUserId],
    queryFn: () => listUserMemberships(selectedUserId),
    enabled: Boolean(selectedUserId),
  });
  const roles = useQuery({
    queryKey: ["project-roles", projectId],
    queryFn: () => listProjectRoles(projectId),
    enabled: Boolean(projectId),
  });
  const selectedMembership = (memberships.data ?? []).find(
    (membership) => membership.project_id === projectId,
  );

  useEffect(() => {
    if (!selectedUser) return;
    setEditName(selectedUser.display_name);
    setEditEmail(selectedUser.email);
    setResetPassword("");
    setProjectId("");
    setRoleId("");
  }, [selectedUser]);

  const invalidateUsers = () =>
    queryClient.invalidateQueries({ queryKey: ["installation-users"] });
  const invalidateMemberships = () =>
    queryClient.invalidateQueries({
      queryKey: ["admin-user-memberships", selectedUserId],
    });

  // Create a new installation user.
  const createUser = useMutation({
    mutationFn: () =>
      createInstallationUser({
        display_name: newName || undefined,
        email: newEmail,
        password: newPassword,
      }),
    onSuccess: (user) => {
      setNewName("");
      setNewEmail("");
      setNewPassword("");
      setCreateOpen(false);
      setSelectedUserId(user.user_id);
      void invalidateUsers();
    },
  });

  const handleCreateOpenChange = (open: boolean) => {
    setCreateOpen(open);
    if (!open) {
      setNewName("");
      setNewEmail("");
      setNewPassword("");
      createUser.reset();
    }
  };

  // Create a new installation user.
  const patchUser = useMutation({
    mutationFn: (payload: Parameters<typeof patchInstallationUser>[1]) =>
      patchInstallationUser(selectedUserId, payload),
    onSuccess: () => {
      setResetPassword("");
      void invalidateUsers();
    },
  });

  // Assign or remove project-level roles for the selected user.
  const assignRole = useMutation({
    mutationFn: () =>
      selectedMembership
        ? updateProjectMember(
            projectId,
            selectedMembership.membership_id,
            roleId,
          )
        : addProjectMember(projectId, selectedUserId, roleId),
    onSuccess: () => {
      setRoleId("");
      void invalidateMemberships();
    },
  });

  // Remove a project-level membership for the selected user.
  const removeMembership = useMutation({
    mutationFn: ({
      membershipId,
      targetProjectId,
    }: {
      membershipId: string;
      targetProjectId: string;
    }) => deleteProjectMember(targetProjectId, membershipId),
    onSuccess: () => void invalidateMemberships(),
  });

  if (!session?.principal.is_admin) return <Navigate replace to="/" />;

  const normalizedSearch = search.trim().toLowerCase();
  const filteredUsers = (users.data ?? []).filter((user) =>
    !normalizedSearch
      ? true
      : `${user.display_name} ${user.email}`
          .toLowerCase()
          .includes(normalizedSearch),
  );
  const isCurrentUser = selectedUser?.user_id === session.principal.user_id;
  const error =
    users.error ||
    projects.error ||
    memberships.error ||
    roles.error ||
    patchUser.error ||
    assignRole.error ||
    removeMembership.error;

  return (
    <Page
      actions={
        <Button onClick={() => handleCreateOpenChange(true)} type="button">
          <UserPlus size={16} /> Create user
        </Button>
      }
      title="User management"
      subtitle="Manage installation accounts and project-level role assignments."
    >
      <AppDialog
        description="Create an installation account with a temporary password."
        error={createUser.error?.message}
        footer={
          <>
            <Button
              onClick={() => handleCreateOpenChange(false)}
              type="button"
              variant="outline"
            >
              Cancel
            </Button>
            <Button
              disabled={
                !newEmail.trim() ||
                !passwordMeetsPolicy(newPassword, passwordPolicy) ||
                createUser.isPending
              }
              type="submit"
            >
              <UserPlus size={16} />
              {createUser.isPending ? "Creating…" : "Create user"}
            </Button>
          </>
        }
        formProps={{
          onSubmit: (event) => {
            event.preventDefault();
            createUser.mutate();
          },
        }}
        onOpenChange={handleCreateOpenChange}
        open={createOpen}
        title="Create user"
      >
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="create-user-name">Name</Label>
            <Input
              autoComplete="name"
              id="create-user-name"
              onChange={(event) => setNewName(event.target.value)}
              value={newName}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="create-user-email">Email</Label>
            <Input
              autoComplete="email"
              id="create-user-email"
              onChange={(event) => setNewEmail(event.target.value)}
              required
              type="email"
              value={newEmail}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="create-user-password">Temporary password</Label>
            <Input
              autoComplete="new-password"
              id="create-user-password"
              maxLength={passwordPolicy.max_length ?? undefined}
              minLength={passwordPolicy.min_length}
              onChange={(event) => setNewPassword(event.target.value)}
              required
              type="password"
              value={newPassword}
            />
            <p className="m-0 text-xs text-[#657082]">
              {describePasswordPolicy(passwordPolicy)} The user must change it
              after signing in.
            </p>
          </div>
        </div>
      </AppDialog>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(320px,0.9fr)_minmax(0,1.4fr)]">
        <Card className="mt-0">
          <CardHeader>
            <CardTitle>Users</CardTitle>
          </CardHeader>
          <CardContent>
            <Input
              className="mb-3"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search users"
              value={search}
            />
            <TableWrap className="mt-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>User</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.isPending && (
                    <TableRow>
                      <TableCell colSpan={2}>Loading users…</TableCell>
                    </TableRow>
                  )}
                  {!users.isPending && filteredUsers.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={2}>
                        No users match this search.
                      </TableCell>
                    </TableRow>
                  )}
                  {filteredUsers.map((user) => (
                    <TableRow
                      className={`cursor-pointer ${
                        user.user_id === selectedUserId ? "bg-[#f3f7f5]" : ""
                      }`}
                      key={user.user_id}
                      onClick={() => setSelectedUserId(user.user_id)}
                    >
                      <TableCell>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <strong>{user.display_name}</strong>
                          {user.is_admin && (
                            <Badge>
                              <ShieldCheck className="mr-1" size={12} /> Admin
                            </Badge>
                          )}
                        </div>
                        <span className="text-xs text-[#657082]">
                          {user.email}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          <Badge
                            variant={user.is_active ? "secondary" : "outline"}
                          >
                            {user.is_active ? "Active" : "Disabled"}
                          </Badge>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableWrap>
          </CardContent>
        </Card>

        <div className="grid gap-4">
          {!selectedUser ? (
            <Card className="mt-0">
              <CardContent className="py-8 text-center text-sm text-[#657082]">
                Select a user to manage their account and project access.
              </CardContent>
            </Card>
          ) : (
            <>
              <Card className="mt-0">
                <CardHeader>
                  <CardTitle>Account</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label>Name</Label>
                      <Input
                        disabled={isCurrentUser}
                        onChange={(event) => setEditName(event.target.value)}
                        value={editName}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label>Email</Label>
                      <Input
                        disabled={isCurrentUser}
                        onChange={(event) => setEditEmail(event.target.value)}
                        type="email"
                        value={editEmail}
                      />
                    </div>
                  </div>
                  {isCurrentUser && (
                    <p className="m-0 text-sm text-[#657082]">
                      Use the Profile option in the account menu to edit your
                      own account.
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      disabled={
                        isCurrentUser ||
                        !editName.trim() ||
                        !editEmail.trim() ||
                        patchUser.isPending
                      }
                      onClick={() =>
                        patchUser.mutate({
                          display_name: editName,
                          email: editEmail,
                        })
                      }
                      type="button"
                    >
                      Save account
                    </Button>
                    <Button
                      disabled={isCurrentUser || patchUser.isPending}
                      onClick={() =>
                        patchUser.mutate({ is_active: !selectedUser.is_active })
                      }
                      type="button"
                      variant="secondary"
                    >
                      {selectedUser.is_active ? "Disable user" : "Enable user"}
                    </Button>
                    <Button
                      disabled={isCurrentUser || patchUser.isPending}
                      onClick={() =>
                        patchUser.mutate({ is_admin: !selectedUser.is_admin })
                      }
                      type="button"
                      variant="outline"
                    >
                      {selectedUser.is_admin ? "Remove admin" : "Make admin"}
                    </Button>
                  </div>
                  <div className="grid gap-3 border-t border-[#e5e9ef] pt-4 md:grid-cols-[1fr_auto]">
                    <div>
                      <Input
                        autoComplete="new-password"
                        maxLength={passwordPolicy.max_length ?? undefined}
                        minLength={passwordPolicy.min_length}
                        onChange={(event) =>
                          setResetPassword(event.target.value)
                        }
                        placeholder="Set temporary password"
                        type="password"
                        value={resetPassword}
                        disabled={isCurrentUser}
                      />
                      <p className="mb-0 mt-1 text-xs text-[#657082]">
                        The user will be required to change it after signing in.
                      </p>
                    </div>
                    <Button
                      disabled={
                        isCurrentUser ||
                        !passwordMeetsPolicy(resetPassword, passwordPolicy) ||
                        patchUser.isPending
                      }
                      onClick={() =>
                        patchUser.mutate({
                          password: resetPassword,
                          must_change_password: true,
                        })
                      }
                      type="button"
                      variant="secondary"
                    >
                      Reset password
                    </Button>
                  </div>
                </CardContent>
              </Card>

              <Card className="mt-0">
                <CardHeader>
                  <div>
                    <CardTitle>Project roles and permissions</CardTitle>
                    <p className="mb-0 mt-1 text-sm text-[#657082]">
                      Assign one role per project. Role permissions are
                      effective immediately.
                    </p>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  {selectedUser.is_admin && (
                    <div className="flex items-start gap-2 rounded-lg border border-[#cce8d8] bg-[#f0faf4] p-3 text-sm text-[#245f3f]">
                      <ShieldCheck className="mt-0.5 shrink-0" size={17} />
                      Installation administrators have every permission in every
                      project, independent of memberships below.
                    </div>
                  )}
                  <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                    <Select
                      value={projectId || undefined}
                      onValueChange={(value) => {
                        setProjectId(value);
                        setRoleId("");
                      }}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Choose project" />
                      </SelectTrigger>
                      <SelectContent>
                        {(projects.data ?? []).map((project) => (
                          <SelectItem
                            key={project.project_id}
                            value={project.project_id}
                          >
                            {project.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select
                      value={roleId || undefined}
                      onValueChange={setRoleId}
                    >
                      <SelectTrigger disabled={!projectId}>
                        <SelectValue
                          placeholder={
                            selectedMembership?.role.name ?? "Choose role"
                          }
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {(roles.data ?? []).map((role) => (
                          <SelectItem key={role.role_id} value={role.role_id}>
                            {role.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      disabled={!projectId || !roleId || assignRole.isPending}
                      onClick={() => assignRole.mutate()}
                      type="button"
                    >
                      {selectedMembership ? "Update role" : "Add project"}
                    </Button>
                  </div>
                  {memberships.isPending ? (
                    <p className="m-0 text-sm text-[#657082]">
                      Loading project roles…
                    </p>
                  ) : (memberships.data ?? []).length === 0 ? (
                    <p className="m-0 text-sm text-[#657082]">
                      This user has no project roles.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      {(memberships.data ?? []).map((membership) => (
                        <div
                          className="rounded-lg border border-[#e1e5ea] p-3"
                          key={membership.membership_id}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <strong>{membership.project_name}</strong>
                              <p className="mb-0 mt-0.5 text-sm text-[#657082]">
                                {membership.role.name}
                              </p>
                            </div>
                            <Button
                              onClick={() =>
                                removeMembership.mutate({
                                  membershipId: membership.membership_id,
                                  targetProjectId: membership.project_id,
                                })
                              }
                              size="sm"
                              type="button"
                              variant="outline"
                            >
                              Remove
                            </Button>
                          </div>
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {membership.role.permissions.map((permission) => (
                              <Badge key={permission} variant="outline">
                                {permission}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </>
          )}
          {error && (
            <p className="m-0 rounded-lg border border-[#f0c8c4] bg-[#fff4f2] p-3 text-sm text-[#b42318]">
              {error.message}
            </p>
          )}
        </div>
      </div>
    </Page>
  );
}
