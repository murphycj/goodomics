import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Plus, X } from "lucide-react";
import { useState } from "react";
import { createProject } from "../../api";
import { queryClient } from "../../lib/queryClient";

export function CreateProjectButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="button" onClick={() => setOpen(true)} type="button">
        <Plus size={16} /> New project
      </button>
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
    <div className="modal-backdrop" role="presentation">
      <form
        className="modal"
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate({
            name,
            slug: slug || undefined,
            description: description || undefined,
          });
        }}
      >
        <div className="modal-heading">
          <h2>Create project</h2>
          <button className="icon-button" onClick={onClose} type="button">
            <X size={18} />
          </button>
        </div>
        <label className="field">
          <span>Name</span>
          <input
            autoFocus
            onChange={(event) => setName(event.target.value)}
            required
            value={name}
          />
        </label>
        <label className="field">
          <span>Slug</span>
          <input
            onChange={(event) => setSlug(event.target.value)}
            placeholder="rnaseq-core"
            value={slug}
          />
        </label>
        <label className="field">
          <span>Description</span>
          <input
            onChange={(event) => setDescription(event.target.value)}
            value={description}
          />
        </label>
        {mutation.error && (
          <p className="error-text">{mutation.error.message}</p>
        )}
        <div className="modal-actions">
          <button className="button secondary" onClick={onClose} type="button">
            Cancel
          </button>
          <button
            className="button"
            disabled={mutation.isPending}
            type="submit"
          >
            Create
          </button>
        </div>
      </form>
    </div>
  );
}
