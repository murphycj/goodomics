import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  addProjectMember,
  getProject,
  listProjectMembers,
  listProjectRoles,
  listReports,
  listUsers,
  patchProject,
} from "../api";
import { useAuth } from "../components/auth/AuthProvider";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Detail,
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
import { queryClient } from "../lib/queryClient";

const NO_DEFAULT_REPORT = "__none__";

/** Project settings page for API context and default report selection. */
export function SettingsPage({ projectId }: { projectId: string }) {
  const { can, session } = useAuth();
  const [selectedUser, setSelectedUser] = useState("");
  const [selectedRole, setSelectedRole] = useState("");
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
  });
  const reports = useQuery({
    queryKey: ["reports", projectId],
    queryFn: () => listReports(projectId),
  });
  const defaultReport = useMutation({
    mutationFn: (reportId: string | null) =>
      patchProject(projectId, { default_report_id: reportId }),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
  });
  const mayManageMembers = can("project.members.manage", projectId);
  const mayReadRoles = can("project.roles.read", projectId);
  const users = useQuery({
    queryKey: ["installation-users"],
    queryFn: listUsers,
    enabled: Boolean(session?.principal.is_admin),
  });
  const roles = useQuery({
    queryKey: ["project-roles", projectId],
    queryFn: () => listProjectRoles(projectId),
    enabled: mayReadRoles,
  });
  const members = useQuery({
    queryKey: ["project-members", projectId],
    queryFn: () => listProjectMembers(projectId),
    enabled: mayManageMembers,
  });
  const addMember = useMutation({
    mutationFn: () => addProjectMember(projectId, selectedUser, selectedRole),
    onSuccess: () => {
      setSelectedUser("");
      setSelectedRole("");
      void queryClient.invalidateQueries({
        queryKey: ["project-members", projectId],
      });
    },
  });

  return (
    <Page title="Settings" subtitle="Dashboard and API configuration.">
      <Card>
        <CardContent className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
          <Detail label="Project ref" value={projectId} />
          <Detail label="API namespace" value="/api/v1" />
          <div className="space-y-1.5">
            <Label>Default report</Label>
            <Select
              value={project.data?.default_report_id ?? NO_DEFAULT_REPORT}
              onValueChange={(value) =>
                defaultReport.mutate(value === NO_DEFAULT_REPORT ? null : value)
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="Choose report" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_DEFAULT_REPORT}>
                  No default report
                </SelectItem>
                {(reports.data ?? []).map((report) => (
                  <SelectItem key={report.report_id} value={report.report_id}>
                    {report.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>
      {mayReadRoles && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle>Project roles and permissions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {(roles.data ?? []).map((role) => (
              <div
                className="rounded-lg border border-[#e1e5ea] p-3"
                key={role.role_id}
              >
                <div className="mb-2 flex items-center gap-2">
                  <strong>{role.name}</strong>
                  {role.is_builtin && (
                    <Badge variant="secondary">Built in</Badge>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {role.permissions.map((permission) => (
                    <Badge key={permission} variant="outline">
                      {permission}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
      {mayManageMembers && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle>Project members</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {session?.principal.is_admin && (
              <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                <Select value={selectedUser} onValueChange={setSelectedUser}>
                  <SelectTrigger>
                    <SelectValue placeholder="Choose user" />
                  </SelectTrigger>
                  <SelectContent>
                    {(users.data ?? [])
                      .filter((user) => user.is_active)
                      .map((user) => (
                        <SelectItem key={user.user_id} value={user.user_id}>
                          {user.display_name} · {user.email}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
                <Select value={selectedRole} onValueChange={setSelectedRole}>
                  <SelectTrigger>
                    <SelectValue placeholder="Choose role" />
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
                  disabled={
                    !selectedUser || !selectedRole || addMember.isPending
                  }
                  onClick={() => addMember.mutate()}
                  type="button"
                >
                  Add member
                </Button>
              </div>
            )}
            <TableWrap>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>User</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Role</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(members.data ?? []).map((membership) => (
                    <TableRow key={membership.membership_id}>
                      <TableCell>{membership.user.display_name}</TableCell>
                      <TableCell>{membership.user.email}</TableCell>
                      <TableCell>{membership.role.name}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableWrap>
          </CardContent>
        </Card>
      )}
    </Page>
  );
}
