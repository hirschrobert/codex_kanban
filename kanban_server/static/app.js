(() => {
  "use strict";

const {
  api,
  state,
  priorities,
  discardMessage,
  text,
  normalizeNewlines,
  timeAgo,
  dateTimeLabel,
  participantName,
  participantKind,
  commentAuthorName,
  cardById,
  archiveSelectionKey,
  archiveSelection,
  archiveActionTargets,
  clearArchiveSelections,
  visibleCards,
  formList,
  normalText,
  localCommentAuthorName,
  coordinationWarningsForCard,
  potentialConflicts,
  conflictText,
  coordinationConfirmationNeeded,
  assigneeChipText,
  cardOwnerText,
  cardCreatorText,
  confirmCoordination,
} = window.Kanban;

const boardEl = document.querySelector("#board");
const participantsEl = document.querySelector("#participants");
const activityEl = document.querySelector("#activity");
const liveStateEl = document.querySelector("#live-state");
const projectSelectEl = document.querySelector("#project-select");
const showArchivedToggleEl = document.querySelector("#show-archived-toggle");
const archiveActionButton = document.querySelector("#archive-action-button");
const cardDialog = document.querySelector("#card-dialog");
const cardForm = document.querySelector("#card-form");
const deleteCardButton = document.querySelector("#delete-card-button");
const runCardNowButton = document.querySelector("#run-card-now-button");
const cardCommentsSectionEl = document.querySelector("#card-comments-section");
const cardCommentsEl = document.querySelector("#card-comments");
const addCommentButton = document.querySelector("#add-comment-button");
const participantDialog = document.querySelector("#participant-dialog");
const participantForm = document.querySelector("#participant-form");
const settingsDialog = document.querySelector("#settings-dialog");
const settingsLimitsEl = document.querySelector("#settings-agent-limits");
const settingsProjectListEl = document.querySelector("#settings-project-list");

function setLiveState(label, className) {
  liveStateEl.textContent = label;
  liveStateEl.className = `live-pill ${className || ""}`.trim();
}


function render(snapshot) {
  state.snapshot = snapshot;
  const activeBoardSlugs = new Set((snapshot.projects || []).map((project) => project.board_slug));
  if (
    snapshot.board?.slug &&
    (!state.board || (state.board !== snapshot.board.slug && !activeBoardSlugs.has(state.board)))
  ) {
    state.board = snapshot.board.slug;
    localStorage.setItem("codex-kanban-board", state.board);
  }
  renderProjectSelect();
  showArchivedToggleEl.checked = state.showArchived;
  renderBoard();
  renderArchiveAction();
  renderParticipants();
  renderActivity();
}

function renderProjectSelect() {
  const projects = state.snapshot?.projects || [];
  projectSelectEl.innerHTML = "";
  projects.forEach((project) => {
    const option = document.createElement("option");
    option.value = project.board_slug;
    option.textContent = project.display_name;
    projectSelectEl.appendChild(option);
  });
  if (state.snapshot?.board && !projects.some((project) => project.board_slug === state.snapshot.board.slug)) {
    const option = document.createElement("option");
    option.value = state.snapshot.board.slug;
    option.textContent = state.snapshot.board.title;
    projectSelectEl.appendChild(option);
  }
  projectSelectEl.value = state.snapshot?.board?.slug || state.board;
}

function renderBoard() {
  const lanes = state.snapshot?.lanes || [];
  const cards = visibleCards();
  boardEl.innerHTML = "";

  lanes.forEach((lane) => {
    const laneCards = cards.filter((card) => card.status === lane.status);
    const laneEl = document.createElement("section");
    laneEl.className = "lane";
    laneEl.dataset.status = lane.status;
    laneEl.innerHTML = `
      <div class="lane-header">
        <h2 class="lane-title">${lane.title}</h2>
        <span class="lane-count">${laneCards.length}</span>
      </div>
      <div class="card-stack"></div>
    `;

    laneEl.addEventListener("dragover", (event) => {
      event.preventDefault();
      laneEl.classList.add("drop-target");
    });
    laneEl.addEventListener("dragleave", () => laneEl.classList.remove("drop-target"));
    laneEl.addEventListener("drop", async (event) => {
      event.preventDefault();
      laneEl.classList.remove("drop-target");
      const draggedCard = cardById(state.draggedCardId);
      if (draggedCard && draggedCard.status !== lane.status) {
        const proposedCard = Object.assign({}, draggedCard, { status: lane.status });
        if (!confirmCoordination(proposedCard)) {
          return;
        }
        await updateCard(state.draggedCardId, { status: lane.status });
      }
    });

    const stack = laneEl.querySelector(".card-stack");
    laneCards.forEach((card) => stack.appendChild(renderCard(card)));
    boardEl.appendChild(laneEl);
  });
}

function renderArchiveAction() {
  const count = archiveActionTargets().length;
  const baseLabel = state.showArchived ? "Unarchive" : "Archive";
  archiveActionButton.textContent = count ? `${baseLabel} ${count}` : baseLabel;
  archiveActionButton.disabled = count === 0;
}

function cardNoticeHtml(card) {
  const conflicts = Array.isArray(card.conflicts) ? card.conflicts : potentialConflicts(card);
  const warnings = Array.isArray(card.coordination_warnings)
    ? card.coordination_warnings
    : coordinationWarningsForCard(card);
  const notices = [];
  if (conflicts.length) {
    notices.push(`Conflict risk: ${conflictText(conflicts[0])}`);
  }
  if (warnings.length) {
    notices.push(warnings[0]);
  }
  if (Array.isArray(card.dependency_warnings) && card.dependency_warnings.length) {
    const dependencyWarning = card.dependency_warnings[0];
    if (!notices.includes(dependencyWarning)) {
      notices.push(dependencyWarning);
    }
  }
  return notices
    .map((notice) => `<p class="card-warning">${escapeHtml(normalizeNewlines(notice))}</p>`)
    .join("");
}

function renderCard(card) {
  const cardEl = document.createElement("article");
  cardEl.draggable = true;
  const hasConflicts = Array.isArray(card.conflicts) && card.conflicts.length > 0;
  const hasWarnings =
    Array.isArray(card.coordination_warnings) && card.coordination_warnings.length > 0;
  cardEl.className = `kanban-card ${card.blocker_reason ? "blocker" : ""} ${hasConflicts || hasWarnings ? "conflict" : ""} ${card.assignee_is_stale ? "stale" : ""} ${card.archived ? "archived-card" : ""}`;
  cardEl.dataset.cardId = card.id;
  const priorityClass = priorities.has(card.priority) ? `priority-${card.priority}` : "";
  const parentCount = Array.isArray(card.parent_external_ids) ? card.parent_external_ids.length : 0;
  const childCount = Array.isArray(card.child_external_ids) ? card.child_external_ids.length : 0;
  const repeatCadence = normalText(card.repeat_cadence || "none");
  const stagedArchive = archiveSelection(card);
  const archiveDisabled = state.showArchived && !card.archived;
  const archiveLabel = state.showArchived
    ? `${card.archived ? "Keep archived" : "Already active"} ${text(card.external_id, card.title)}`
    : `Select ${text(card.external_id, card.title)} for archive`;
  cardEl.innerHTML = `
    <div class="card-topline">
      <button class="card-open" type="button">
        <span class="card-id">${text(card.external_id, `#${card.id}`)}</span>
      </button>
      <div class="card-actions">
        ${repeatCadence !== "none" && !card.archived ? `<button class="mini-button run-card-now" type="button">Run</button>` : ""}
        <label class="archive-card-toggle">
          <input type="checkbox" ${stagedArchive ? "checked" : ""} ${archiveDisabled ? "disabled" : ""} aria-label="${escapeHtml(archiveLabel)}">
          <span></span>
        </label>
      </div>
    </div>
    <button class="card-body-button" type="button">
      <h3 class="card-title">${escapeHtml(card.title)}</h3>
      ${card.description ? `<p class="card-description">${escapeHtml(normalizeNewlines(card.description))}</p>` : ""}
      ${cardNoticeHtml(card)}
      <div class="card-meta">
        <span class="chip ${priorityClass}">${card.priority}</span>
        <span class="chip">Owner: ${escapeHtml(cardOwnerText(card))}</span>
        <span class="chip">Created: ${escapeHtml(cardCreatorText(card))}</span>
        <span class="chip ${card.assignee_is_stale ? "stale-chip" : ""}">Assigned: ${escapeHtml(assigneeChipText(card))}</span>
        ${repeatCadence !== "none" ? `<span class="chip">${escapeHtml(repeatCadence)} ${escapeHtml(card.repeat_time || "01:00")}</span>` : ""}
        ${card.archived ? `<span class="chip archived-chip">archived</span>` : ""}
        ${parentCount ? `<span class="chip">${parentCount} parent${parentCount === 1 ? "" : "s"}</span>` : ""}
        ${childCount ? `<span class="chip">${childCount} child${childCount === 1 ? "" : "ren"}</span>` : ""}
        ${card.target_branch ? `<span class="chip">${escapeHtml(card.target_branch)}</span>` : ""}
        ${card.feature_branch ? `<span class="chip">${escapeHtml(card.feature_branch)}</span>` : ""}
      </div>
    </button>
  `;
  cardEl.querySelectorAll(".card-open, .card-body-button").forEach((button) => {
    button.addEventListener("click", () => openCardDialog(card));
  });
  const runButton = cardEl.querySelector(".run-card-now");
  if (runButton) {
    runButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await runCardNow(card.id);
    });
  }
  cardEl.querySelector(".archive-card-toggle input").addEventListener("change", async (event) => {
    event.stopPropagation();
    state.archiveSelections[archiveSelectionKey(card)] = event.target.checked;
    renderArchiveAction();
  });
  cardEl.addEventListener("dragstart", () => {
    state.draggedCardId = card.id;
    cardEl.classList.add("dragging");
  });
  cardEl.addEventListener("dragend", () => {
    state.draggedCardId = null;
    cardEl.classList.remove("dragging");
  });
  return cardEl;
}

function renderParticipants() {
  const participants = state.snapshot?.participants || [];
  const visibleParticipants = participants.slice(0, state.participantLimit);
  participantsEl.innerHTML = "";
  visibleParticipants.forEach((participant) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `participant-row ghost-button ${participant.is_stale ? "stale" : ""}`;
    const dotClass = participant.is_stale ? "status-stale" : `status-${participant.status}`;
    const liveness = participant.is_stale ? "stale" : participant.is_active ? "active" : participant.status;
    row.innerHTML = `
      <span class="status-dot ${dotClass}"></span>
      <span class="participant-main">
        <span class="participant-name">${escapeHtml(participant.display_name)}</span>
        <span class="participant-role">${escapeHtml(liveness)} · ${escapeHtml(participant.role || participant.kind)} · ${timeAgo(participant.last_seen_at)}</span>
      </span>
    `;
    row.addEventListener("click", () => openParticipantDialog(participant));
    participantsEl.appendChild(row);
  });
}

function renderActivity() {
  const events = (state.snapshot?.events || []).slice().reverse();
  const visibleEvents = events.slice(0, state.activityLimit);
  activityEl.innerHTML = "";
  visibleEvents.forEach((event) => {
    const row = document.createElement("li");
    row.className = "activity-row";
    row.innerHTML = `
      <span class="status-dot"></span>
      <span class="activity-main">
        <span class="activity-message">${escapeHtml(event.event_type)} ${escapeHtml(normalizeNewlines(event.message || ""))}</span>
        <span class="activity-meta">${escapeHtml(normalizeNewlines(event.card_external_id || ""))} ${escapeHtml(event.participant_id || "")} ${timeAgo(event.created_at)}</span>
      </span>
    `;
    activityEl.appendChild(row);
  });
}

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

function populateCardSelects() {
  const statusSelect = cardForm.elements.status;
  statusSelect.innerHTML = "";
  (state.snapshot?.lanes || []).forEach((lane) => {
    appendSelectOption(statusSelect, lane.status, lane.title);
  });

  const ownerSelect = cardForm.elements.owner_id;
  ownerSelect.innerHTML = '<option value="">Default owner</option>';
  (state.snapshot?.participants || []).forEach((participant) => {
    appendSelectOption(ownerSelect, participant.id, participant.display_name);
  });

  const assigneeSelect = cardForm.elements.assignee_id;
  assigneeSelect.innerHTML = '<option value="">Unassigned</option>';
  (state.snapshot?.participants || []).forEach((participant) => {
    appendSelectOption(assigneeSelect, participant.id, participant.display_name);
  });

  const writerSelect = cardForm.elements.comment_writer;
  writerSelect.innerHTML = `<option value="">${localCommentAuthorName}</option>`;
  (state.snapshot?.participants || []).forEach((participant) => {
    appendSelectOption(writerSelect, participant.id, `${participant.display_name} (${participant.kind})`);
  });
}

function appendSelectOption(select, value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  select.appendChild(option);
}

function ensureSelectOption(select, value, label) {
  if (!value) return;
  const options = Array.from(select.options || select.children || []);
  if (options.some((option) => option.value === value)) return;
  appendSelectOption(select, value, label || value);
}

function formSnapshot(form) {
  const ignoredFields = new Set(["comment_body", "comment_writer"]);
  const entries = Array.from(new FormData(form).entries()).filter(
    ([name]) => !ignoredFields.has(name)
  );
  return JSON.stringify(entries);
}

function rememberFormState(form) {
  form.dataset.initialSnapshot = formSnapshot(form);
}

function formIsDirty(form) {
  return formSnapshot(form) !== form.dataset.initialSnapshot;
}

function canDiscardForm(form) {
  return !formIsDirty(form) || window.confirm(discardMessage);
}

function closeDialogWithWarning(dialog, form) {
  if (canDiscardForm(form)) {
    dialog.close();
  }
}

function protectDialogCancel(dialog, form) {
  dialog.addEventListener("cancel", (event) => {
    if (!canDiscardForm(form)) {
      event.preventDefault();
    }
  });
}

function openCardDialog(card = null) {
  populateCardSelects();
  cardForm.reset();
  cardForm.elements.id.value = card?.id || "";
  cardForm.elements.title.value = card?.title || "";
  cardForm.elements.description.value = normalizeNewlines(card?.description || "");
  cardForm.elements.status.value = card?.status || "backlog";
  cardForm.elements.priority.value = card?.priority || "normal";
  ensureSelectOption(cardForm.elements.owner_id, card?.owner_id, cardOwnerText(card));
  cardForm.elements.owner_id.value = card?.owner_id || "";
  cardForm.elements.assignee_id.value = card?.assignee_id || "";
  cardForm.elements.repeat_cadence.value = card?.repeat_cadence || "none";
  cardForm.elements.repeat_time.value = card?.repeat_time || "01:00";
  cardForm.elements.parent_external_ids.value = Array.isArray(card?.parent_external_ids)
    ? card.parent_external_ids.join("\n")
    : "";
  cardForm.elements.child_external_ids.value = Array.isArray(card?.child_external_ids)
    ? card.child_external_ids.join("\n")
    : "";
  cardForm.elements.target_repo.value = card?.target_repo || "";
  cardForm.elements.target_branch.value = card?.target_branch || "";
  cardForm.elements.feature_branch.value = card?.feature_branch || "";
  cardForm.elements.worktree_path.value = card?.worktree_path || "";
  cardForm.elements.starting_target_sha.value = card?.starting_target_sha || "";
  cardForm.elements.handoff_target_sha.value = card?.handoff_target_sha || "";
  cardForm.elements.blocker_reason.value = normalizeNewlines(card?.blocker_reason || "");
  cardForm.elements.checks.value = Array.isArray(card?.checks)
    ? card.checks.map(normalizeNewlines).join("\n")
    : "";
  cardForm.elements.archived.checked = Boolean(card?.archived);
  renderComments(card);
  const canRunNow = Boolean(card && card.repeat_cadence && card.repeat_cadence !== "none" && !card.archived);
  runCardNowButton.hidden = !canRunNow;
  runCardNowButton.disabled = !canRunNow;
  deleteCardButton.hidden = !card?.archived;
  deleteCardButton.disabled = !card?.archived;
  document.querySelector("#card-dialog-title").textContent = card ? text(card.external_id, "Card") : "New Card";
  rememberFormState(cardForm);
  cardDialog.showModal();
}

function renderComments(card) {
  cardCommentsSectionEl.hidden = !card;
  cardCommentsEl.innerHTML = "";
  cardForm.elements.comment_body.value = "";
  if (!card) {
    return;
  }
  const comments = Array.isArray(card.comments) ? card.comments : [];
  if (!comments.length) {
    const empty = document.createElement("li");
    empty.className = "comment-row empty";
    empty.textContent = "No notes";
    cardCommentsEl.appendChild(empty);
    return;
  }
  comments.forEach((comment) => {
    const row = document.createElement("li");
    row.className = "comment-row";
    const authorName = commentAuthorName(comment);
    const authorKind = comment.author_kind || "human";
    row.innerHTML = `
      <span class="comment-body">${escapeHtml(normalizeNewlines(comment.body || ""))}</span>
      <span class="comment-meta">${escapeHtml(authorName)} · ${escapeHtml(authorKind)} · ${escapeHtml(dateTimeLabel(comment.created_at))}</span>
    `;
    cardCommentsEl.appendChild(row);
  });
}

function mergeCommentIntoCard(card, comment) {
  if (!card || !comment) return null;
  const comments = Array.isArray(card.comments) ? card.comments.slice() : [];
  const commentId = comment.id == null ? "" : String(comment.id);
  const exists = comments.some((item) => commentId && String(item.id) === commentId);
  if (!exists) {
    comments.push(comment);
  }
  card.comments = comments;
  card.comment_count = comments.length;
  return card;
}

function openParticipantDialog(participant = null) {
  if (participant && participant.kind !== "human") {
    return;
  }
  participantForm.reset();
  participantForm.elements.id.value = participant?.id || "";
  participantForm.elements.display_name.value = participant?.display_name || "";
  participantForm.elements.status.value = participant?.status || "idle";
  rememberFormState(participantForm);
  participantDialog.showModal();
}

async function saveCard(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    cardDialog.close();
    return;
  }
  const form = new FormData(cardForm);
  const id = form.get("id");
  const payload = Object.fromEntries(form.entries());
  delete payload.id;
  delete payload.comment_body;
  delete payload.comment_writer;
  payload.board_slug = state.board;
  payload.checks = payload.checks
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
  payload.parent_external_ids = formList(payload.parent_external_ids);
  payload.child_external_ids = formList(payload.child_external_ids);
  payload.archived = form.get("archived") === "on";
  payload.repeat_timezone = "Europe/Berlin";
  if (!payload.assignee_id) {
    payload.assignee_id = null;
  }
  if (!payload.owner_id) {
    payload.owner_id = null;
  }
  const proposedCard = Object.assign({}, id ? cardById(id) : {}, payload, {
    id: id || `new-${Date.now()}`,
  });
  const currentCard = id ? cardById(id) : null;
  if (
    coordinationConfirmationNeeded(currentCard, proposedCard) &&
    !confirmCoordination(proposedCard)
  ) {
    return;
  }
  if (id) {
    await updateCard(id, payload);
  } else {
    await api("/api/cards", { method: "POST", body: JSON.stringify(payload) });
  }
  cardDialog.close();
  await refresh();
}

async function updateCard(id, payload) {
  await api(`/api/cards/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

async function deleteCurrentCard() {
  const id = cardForm.elements.id.value;
  if (!id) return;
  const card = cardById(id);
  const label = card?.external_id || `#${id}`;
  if (!window.confirm(`Delete archived card ${label}?`)) return;
  await api(`/api/cards/${id}`, { method: "DELETE" });
  cardDialog.close();
  await refresh();
}

async function runCardNow(cardId = null) {
  const id = cardId || cardForm.elements.id.value;
  if (!id) return;
  await api(`/api/cards/${id}/run-now`, {
    method: "POST",
    body: JSON.stringify({ board_slug: state.board }),
  });
  await refresh();
}

async function addCurrentComment() {
  const id = cardForm.elements.id.value;
  if (!id) return;
  const body = normalText(cardForm.elements.comment_body.value);
  if (!body) return;
  const writerId = normalText(cardForm.elements.comment_writer.value);
  const payload = { board_slug: state.board, body };
  if (writerId) {
    payload.participant_id = writerId;
  } else {
    payload.author_name = localCommentAuthorName;
    payload.author_kind = "human";
  }
  addCommentButton.disabled = true;
  try {
    const response = await api(`/api/cards/${id}/comments`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const comment = Object.assign({}, response);
    comment.body = comment.body || body;
    comment.author_name =
      comment.author_name || (writerId ? participantName(writerId) : localCommentAuthorName);
    comment.author_kind =
      comment.author_kind || (writerId ? participantKind(writerId) : "human");
    comment.created_at = comment.created_at || new Date().toISOString();
    const localCard = mergeCommentIntoCard(cardById(id), comment) || {
      id,
      comments: [comment],
      comment_count: 1,
    };
    renderComments(localCard);
    try {
      await refresh();
      const updated = cardById(id);
      if (updated) {
        renderComments(updated);
      }
    } catch (refreshError) {
      console.warn("Could not refresh after adding note.", refreshError);
    }
  } catch (error) {
    window.alert(error.message || "Could not add note.");
  } finally {
    addCommentButton.disabled = false;
  }
}

async function saveParticipant(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    participantDialog.close();
    return;
  }
  const payload = Object.fromEntries(new FormData(participantForm).entries());
  if (!payload.id) {
    delete payload.id;
  }
  payload.board_slug = state.board;
  await api("/api/participants", { method: "POST", body: JSON.stringify(payload) });
  participantDialog.close();
  await refresh();
}

function resetBoardIfCurrent(boardSlug) {
  if (state.board === boardSlug) {
    state.board = "";
    localStorage.removeItem("codex-kanban-board");
  }
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

async function refresh() {
  const params = new URLSearchParams();
  if (state.board) params.set("board", state.board);
  if (state.showArchived) params.set("archived_only", "1");
  const suffix = params.toString();
  const path = suffix ? `/api/snapshot?${suffix}` : "/api/snapshot";
  const snapshot = await api(path);
  render(snapshot);
}

function connectEvents() {
  if (state.eventSource) {
    state.eventSource.close();
  }
  const params = new URLSearchParams();
  if (state.board) params.set("board", state.board);
  if (state.showArchived) params.set("archived_only", "1");
  const suffix = params.toString();
  const path = suffix ? `/api/events/stream?${suffix}` : "/api/events/stream";
  const events = new EventSource(path);
  state.eventSource = events;
  events.addEventListener("open", () => setLiveState("Live", "connected"));
  events.addEventListener("snapshot", (event) => render(JSON.parse(event.data)));
  events.addEventListener("error", () => setLiveState("Reconnecting", "offline"));
}

async function switchProject(event) {
  state.board = event.target.value;
  localStorage.setItem("codex-kanban-board", state.board);
  state.participantLimit = 10;
  state.activityLimit = 10;
  clearArchiveSelections();
  setLiveState("Switching", "");
  await refresh();
  connectEvents();
}

async function toggleArchived(event) {
  state.showArchived = event.target.checked;
  localStorage.setItem("codex-kanban-show-archived", state.showArchived ? "1" : "0");
  clearArchiveSelections();
  await refresh();
  connectEvents();
}

async function applyArchiveAction() {
  const targets = archiveActionTargets();
  if (!targets.length) return;
  archiveActionButton.disabled = true;
  const archived = !state.showArchived;
  const failed = [];
  const completedIds = [];
  for (const card of targets) {
    try {
      await updateCard(card.id, { archived });
      completedIds.push(String(card.id));
    } catch (error) {
      failed.push({ card, error });
    }
  }
  clearArchiveSelections();
  if (state.snapshot?.cards) {
    const completedIdSet = new Set(completedIds);
    state.snapshot.cards = state.snapshot.cards.filter(
      (card) => !completedIdSet.has(String(card.id))
    );
    render(state.snapshot);
  }
  await refresh();
  if (failed.length) {
    const labels = failed
      .map(({ card }) => text(card.external_id, `#${card.id}`))
      .join(", ");
    window.alert(`Could not ${archived ? "archive" : "unarchive"} ${labels}.`);
  }
}

function loadMoreOnScroll(element, stateKey, totalGetter, renderFn) {
  element.addEventListener("scroll", () => {
    const nearEnd = element.scrollTop + element.clientHeight >= element.scrollHeight - 12;
    if (!nearEnd) return;
    const total = totalGetter();
    if (state[stateKey] >= total) return;
    state[stateKey] += 10;
    renderFn();
  });
}

function escapeHtml(value) {
  return text(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

document.querySelector("#new-card-button").addEventListener("click", () => openCardDialog());
document.querySelector("#new-participant-button").addEventListener("click", () => openParticipantDialog());
document.querySelector("#settings-button").addEventListener("click", () => openSettingsDialog());
showArchivedToggleEl.addEventListener("change", toggleArchived);
archiveActionButton.addEventListener("click", applyArchiveAction);
deleteCardButton.addEventListener("click", deleteCurrentCard);
runCardNowButton.addEventListener("click", () => runCardNow());
addCommentButton.addEventListener("click", addCurrentComment);
settingsDialog.querySelectorAll(".settings-close").forEach((button) => {
  button.addEventListener("click", () => settingsDialog.close());
});
cardDialog.querySelectorAll(".dialog-cancel").forEach((button) => {
  button.addEventListener("click", () => closeDialogWithWarning(cardDialog, cardForm));
});
participantDialog.querySelectorAll(".dialog-cancel").forEach((button) => {
  button.addEventListener("click", () =>
    closeDialogWithWarning(participantDialog, participantForm)
  );
});
protectDialogCancel(cardDialog, cardForm);
protectDialogCancel(participantDialog, participantForm);
projectSelectEl.addEventListener("change", switchProject);
cardForm.addEventListener("submit", saveCard);
participantForm.addEventListener("submit", saveParticipant);
loadMoreOnScroll(
  participantsEl,
  "participantLimit",
  () => (state.snapshot?.participants || []).length,
  renderParticipants
);
loadMoreOnScroll(
  activityEl,
  "activityLimit",
  () => (state.snapshot?.events || []).length,
  renderActivity
);

refresh().then(connectEvents).catch((error) => {
  setLiveState("Offline", "offline");
  console.error(error);
});

setInterval(refresh, 10000);
})();
