import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { LogIn, Plus } from "lucide-react";
import { useState } from "react";
import { createProject } from "../../api";
import { queryClient } from "../../lib/queryClient";
import { useAuth } from "../auth/AuthProvider";
import { AppDialog } from "../ui/AppDialog";
import { Button } from "../ui/button";
import { PermissionDialog } from "../ui/PermissionDialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";

/** Button wrapper that opens the project creation dialog. */
export function CreateProjectButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)} type="button">
        <Plus size={16} /> New project
      </Button>
      {open && <CreateProjectModal onClose={() => setOpen(false)} />}
    </>
  );
}

/** Project creation dialog with an anonymous-user permission boundary. */
export function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const { session } = useAuth();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const mutation = useMutation({
    mutationFn: createProject,
    onSuccess: (project) => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      onClose();
      void navigate({
        to: "/project/$projectId",
        params: { projectId: project.project_id },
      });
    },
  });

  if (session?.principal.kind === "anonymous") {
    return (
      <PermissionDialog
        actionIcon={<LogIn size={16} />}
        actionLabel="Sign in"
        description="Anonymous visitors can explore public projects, but creating a new project requires a Goodomics account."
        onAction={() => {
          onClose();
          void navigate({ to: "/login" });
        }}
        onOpenChange={(open) => !open && onClose()}
        open
        title="Sign in to create a project"
      />
    );
  }

  return (
    <AppDialog
      description="Create a workspace for runs, samples, reports, and analytical data."
      error={mutation.error?.message}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} type="button">
            Cancel
          </Button>
          <Button disabled={mutation.isPending} type="submit">
            Create
          </Button>
        </>
      }
      formProps={{
        onSubmit: (event) => {
          event.preventDefault();
          mutation.mutate({
            name,
            slug: slug || undefined,
            description: description || undefined,
          });
        },
      }}
      onOpenChange={(open) => !open && onClose()}
      open
      title="Create project"
    >
      <div className="grid gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="project-name">Name</Label>
          <Input
            id="project-name"
            autoFocus
            onChange={(event) => setName(event.target.value)}
            required
            value={name}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="project-slug">Slug</Label>
          <Input
            id="project-slug"
            onChange={(event) => setSlug(event.target.value)}
            placeholder="rnaseq-core"
            value={slug}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="project-description">Description</Label>
          <Input
            id="project-description"
            onChange={(event) => setDescription(event.target.value)}
            value={description}
          />
        </div>
      </div>
    </AppDialog>
  );
}
