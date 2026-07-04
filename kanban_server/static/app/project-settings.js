window.KanbanProjectSettings = window.KanbanProjectSettings || {};

{
  const { api, state } = window.Kanban;

  function createProjectSettingsController({
    settingsDialog,
    settingsLimitsEl,
    settingsProjectListEl,
    resetBoardIfCurrent,
    refresh,
    connectEvents,
    escapeHtml,
  }) {
    function renderSettingsProjects(projects) {
      const limits = state.snapshot?.agent_limits || {};
      settingsLimitsEl.innerHTML = `
        <span class="settings-limit-title">Agent Concurrency</span>
        <span class="settings-project-meta">
          Project active agents: ${Number(limits.max_active_agents_per_project || 0) || "unlimited"}
          · Active project implementers: ${Number(limits.max_active_implementers_per_project || 0) || "unlimited"}
          · Default implementers: ${Number(limits.default_max_active_implementers_per_project || 0) || "unlimited"}
          · Global active agents: ${Number(limits.max_active_agents_global || 0) || "unlimited"}
          · Stale after: ${Number(limits.stale_after_seconds || 0) || "disabled"}s
        </span>
      `;
      settingsProjectListEl.innerHTML = "";
      if (!projects.length) {
        const row = document.createElement("div");
        row.className = "settings-project-row empty";
        row.textContent = "No registered projects";
        settingsProjectListEl.appendChild(row);
        return;
      }

      projects.forEach((project) => {
        const removed = Boolean(project.removed_at);
        const row = document.createElement("div");
        row.className = `settings-project-row ${removed ? "removed" : ""}`;
        row.innerHTML = `
          <div class="settings-project-main">
            <span class="settings-project-title">${escapeHtml(project.display_name)}</span>
            <span class="settings-project-meta">
              ${escapeHtml(project.slug)} · ${escapeHtml(project.board_slug)} · ${removed ? "removed" : "active"}
            </span>
            <span class="settings-project-meta">
              ${Number(project.card_count || 0)} cards · ${Number(project.participant_count || 0)} participants
            </span>
            <label class="settings-number-field">
              <span>Active Implementers</span>
              <input
                type="number"
                min="0"
                step="1"
                value="${Number(project.max_active_implementers || 0)}"
                data-setting="max_active_implementers"
                ${removed ? "disabled" : ""}
              >
            </label>
          </div>
          <div class="settings-project-actions"></div>
        `;

        const actions = row.querySelector(".settings-project-actions");
        const saveButton = document.createElement("button");
        saveButton.type = "button";
        saveButton.className = "ghost-button";
        saveButton.textContent = "Save";
        saveButton.disabled = removed;
        saveButton.addEventListener("click", () => saveProjectSettings(project, row));

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "ghost-button";
        removeButton.textContent = removed ? "Removed" : "Remove";
        removeButton.disabled = removed;
        removeButton.addEventListener("click", () => removeProject(project));

        const pruneButton = document.createElement("button");
        pruneButton.type = "button";
        pruneButton.className = "ghost-button danger-button";
        pruneButton.textContent = "Prune";
        pruneButton.addEventListener("click", () => pruneProject(project));

        actions.append(saveButton, removeButton, pruneButton);
        settingsProjectListEl.appendChild(row);
      });
    }

    async function loadSettingsProjects() {
      const data = await api("/api/projects");
      renderSettingsProjects(data.all_projects || data.projects || []);
    }

    async function openSettingsDialog() {
      await loadSettingsProjects();
      settingsDialog.showModal();
    }

    async function removeProject(project) {
      const ok = window.confirm(`Remove ${project.display_name} from the project picker?`);
      if (!ok) return;
      await api(`/api/projects/${encodeURIComponent(project.slug)}/remove`, { method: "POST" });
      resetBoardIfCurrent(project.board_slug);
      await refresh();
      connectEvents();
      await loadSettingsProjects();
    }

    async function pruneProject(project) {
      const ok = window.confirm(
        `Prune ${project.display_name} and delete its cards, events, and participants?`
      );
      if (!ok) return;
      await api(`/api/projects/${encodeURIComponent(project.slug)}/prune`, { method: "POST" });
      resetBoardIfCurrent(project.board_slug);
      await refresh();
      connectEvents();
      await loadSettingsProjects();
    }

    async function saveProjectSettings(project, row) {
      const input = row.querySelector('[data-setting="max_active_implementers"]');
      const maxActiveImplementers = Number.parseInt(input.value, 10);
      if (!Number.isInteger(maxActiveImplementers) || maxActiveImplementers < 0) {
        window.alert("Active Implementers must be 0 or greater.");
        return;
      }
      await api(`/api/projects/${encodeURIComponent(project.slug)}/settings`, {
        method: "PATCH",
        body: JSON.stringify({ max_active_implementers: maxActiveImplementers }),
      });
      await refresh();
      await loadSettingsProjects();
    }

    return {
      loadSettingsProjects,
      openSettingsDialog,
      renderSettingsProjects,
    };
  }

  window.KanbanProjectSettings.createProjectSettingsController = createProjectSettingsController;
}
