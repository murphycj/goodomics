import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import { createProject } from "../../api";
import { queryClient } from "../../lib/queryClient";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";

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

export function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
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

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate({
              name,
              slug: slug || undefined,
              description: description || undefined,
            });
          }}
          className="contents"
        >
          <DialogHeader>
            <DialogTitle>Create project</DialogTitle>
          </DialogHeader>
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
          {mutation.error && (
            <p className="text-sm text-[#b42318]">{mutation.error.message}</p>
          )}
          <DialogFooter>
            <Button variant="secondary" onClick={onClose} type="button">
              Cancel
            </Button>
            <Button disabled={mutation.isPending} type="submit">
              Create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
