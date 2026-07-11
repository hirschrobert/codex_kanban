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
  agentInstanceName,
  agentInstanceSummary,
  commentAuthorName,
  cardById,
  relatedCardsForEvent,
  relatedCardLabel,
  relatedCardSummary,
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
  intakeKindText,
  intakeSourceText,
  affectedProjectPathText,
  deploymentDispositionText,
  confirmCoordination,
} = window.Kanban;

const boardEl = document.querySelector("#board");
const participantsEl = document.querySelector("#participants");
const activityEl = document.querySelector("#activity");
const liveStateEl = document.querySelector("#live-state");
const projectSelectEl = document.querySelector("#project-select");
const showArchivedToggleEl = document.querySelector("#show-archived-toggle");
const archiveActionButton = document.querySelector("#archive-action-button");
const archiveOldDoneButton = document.querySelector("#archive-old-done-button");
const versionTagEl = document.querySelector("#version-tag");
const cardDialog = document.querySelector("#card-dialog");
const cardForm = document.querySelector("#card-form");
const deleteCardButton = document.querySelector("#delete-card-button");
const runCardNowButton = document.querySelector("#run-card-now-button");
const cardCommentsSectionEl = document.querySelector("#card-comments-section");
const cardCommentsEl = document.querySelector("#card-comments");
const addCommentButton = document.querySelector("#add-comment-button");
const participantDialog = document.querySelector("#participant-dialog");
const participantForm = document.querySelector("#participant-form");
const eventCardPickerDialog = document.querySelector("#event-card-picker-dialog");
const eventCardPickerListEl = document.querySelector("#event-card-picker-list");
const settingsDialog = document.querySelector("#settings-dialog");
const settingsLimitsEl = document.querySelector("#settings-agent-limits");
const settingsProjectListEl = document.querySelector("#settings-project-list");

const projectSettings = window.KanbanProjectSettings.createProjectSettingsController({
  settingsDialog,
  settingsLimitsEl,
  settingsProjectListEl,
  resetBoardIfCurrent,
  refresh,
  connectEvents,
  escapeHtml,
});
const archiveOld = window.KanbanArchiveOld.createController({
  api, state, button: archiveOldDoneButton, refresh,
});

function setLiveState(label, className) {
  liveStateEl.textContent = label;
  liveStateEl.className = `live-pill ${className || ""}`.trim();
}

function eventSortValue(event) {
  return Number(event?.id || 0);
}

function mergeActivityEvents(...groups) {
  const byId = new Map();
  groups.flat().forEach((event) => {
    if (!event) return;
    const key = event.id == null ? `${event.created_at || ""}-${event.event_type || ""}` : String(event.id);
    byId.set(key, event);
  });
  return [...byId.values()].sort((left, right) => eventSortValue(left) - eventSortValue(right));
}

function resetActivityPaging() {
  state.activityHasMore = false;
  state.activityLoading = false;
  state.activityExtended = false;
}

function prepareActivitySnapshot(snapshot) {
  const previous = state.snapshot;
  const previousBoard = previous?.board?.slug || "";
  const nextBoard = snapshot?.board?.slug || "";
  const sameBoard = previousBoard && previousBoard === nextBoard;
  if (state.activityExtended && sameBoard) {
    snapshot.events = mergeActivityEvents(previous.events || [], snapshot.events || []);
    return snapshot;
  }
  resetActivityPaging();
  state.activityHasMore = Boolean(snapshot?.events_has_more);
  return snapshot;
}

function render(snapshot) {
  state.snapshot = prepareActivitySnapshot(snapshot);
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
  archiveOldDoneButton.disabled = state.showArchived;
  renderVersionTag(snapshot.app);
  renderBoard();
  renderArchiveAction();
  renderParticipants();
  renderActivity();
}

function renderVersionTag(app) {
  const version = normalText(app?.version);
  const sourceHash = normalText(app?.hash);
  if (!version && !sourceHash) {
    versionTagEl.hidden = true;
    return;
  }
  const dirty = app?.dirty ? "*" : "";
  versionTagEl.hidden = false;
  versionTagEl.textContent = `${version ? `v${version}` : "dev"}${sourceHash ? ` ${sourceHash}${dirty}` : ""}`;
  versionTagEl.title = app?.dirty
    ? "Codex Kanban build, local changes present"
    : "Codex Kanban build";
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

function affectedProjectChipsHtml(card) {
  const affectedProjectPaths = Array.isArray(card.affected_project_paths)
    ? card.affected_project_paths
    : [];
  const shown = affectedProjectPaths.slice(0, 3);
  const overflow = affectedProjectPaths.length - shown.length;
  return [
    ...shown.map((item) => {
      const label = affectedProjectPathText(item);
      return `<span class="chip affected-project-chip" title="${escapeHtml(label)}">${escapeHtml(label)}</span>`;
    }),
    overflow > 0 ? `<span class="chip">+${overflow} ecosystem</span>` : "",
  ].join("");
}

function changeSourceChipHtml(card) {
  const source = card.change_source;
  if (!source?.path) return "";
  if (source.kind !== "worktree") return "";
  const name = source.path.split(/[\\/]/).filter(Boolean).pop() || source.path;
  const repository = source.repository_path ? `; origin repository: ${source.repository_path}` : "";
  const title = `Changes sourced from worktree: ${source.path}${repository}`;
  return `<span class="chip worktree-source-chip" title="${escapeHtml(title)}">Worktree: ${escapeHtml(name)}</span>`;
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
  const intakeKind = intakeKindText(card);
  const intakeSource = intakeSourceText(card);
  const affectedCount = Array.isArray(card.affected_paths) ? card.affected_paths.length : 0;
  const affectedProjectCount = Array.isArray(card.affected_project_paths)
    ? card.affected_project_paths.length
    : 0;
  const deploymentCount = Array.isArray(card.deployment_dispositions)
    ? card.deployment_dispositions.length
    : 0;
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
        ${intakeKind ? `<span class="chip">${escapeHtml(intakeKind)}</span>` : ""}
        ${intakeSource ? `<span class="chip">${escapeHtml(intakeSource)}</span>` : ""}
        <span class="chip">Owner: ${escapeHtml(cardOwnerText(card))}</span>
        <span class="chip">Created: ${escapeHtml(cardCreatorText(card))}</span>
        <span class="chip ${card.assignee_is_stale ? "stale-chip" : ""}">Assigned: ${escapeHtml(assigneeChipText(card))}</span>
        ${repeatCadence !== "none" ? `<span class="chip">${escapeHtml(repeatCadence)} ${escapeHtml(card.repeat_time || "01:00")}</span>` : ""}
        ${card.archived ? `<span class="chip archived-chip">archived</span>` : ""}
        ${parentCount ? `<span class="chip">${parentCount} parent${parentCount === 1 ? "" : "s"}</span>` : ""}
        ${childCount ? `<span class="chip">${childCount} child${childCount === 1 ? "" : "ren"}</span>` : ""}
        ${affectedCount ? `<span class="chip">Affected: ${affectedCount}</span>` : ""}
        ${affectedProjectCount ? `<span class="chip">Ecosystem: ${affectedProjectCount}</span>` : ""}
        ${affectedProjectChipsHtml(card)}
        ${changeSourceChipHtml(card)}
        ${deploymentCount ? `<span class="chip">Deploy: ${deploymentCount}</span>` : ""}
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
  participantsEl.innerHTML = "";
  participants.forEach((participant) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `participant-row ghost-button ${participant.is_stale ? "stale" : ""}`;
    const dotClass = participant.is_stale ? "status-stale" : `status-${participant.status}`;
    const instances = Array.isArray(participant.instances) ? participant.instances : [];
    const activeModels = Array.isArray(participant.active_models) ? participant.active_models : [];
    const activeCards = Array.isArray(participant.active_cards) ? participant.active_cards : [];
    const focusedCard = participant.focused_card;
    const liveness = instances.length
      ? `${instances.length} live instance${instances.length === 1 ? "" : "s"}`
      : participant.is_stale
        ? "stale"
        : participant.status;
    const instanceRows = instances
      .map(
        (instance) => `
          <span class="participant-instance">
            <span class="status-dot status-${escapeHtml(instance.status || "idle")}"></span>
            <span><strong>${escapeHtml(agentInstanceName(instance))}</strong> · ${escapeHtml(agentInstanceSummary(instance))}</span>
          </span>
        `
      )
      .join("");
    const activeCardSummary = activeCards
      .map((card) => card.external_id || card.title)
      .filter(Boolean)
      .join(", ");
    row.innerHTML = `
      <span class="status-dot ${dotClass}"></span>
      <span class="participant-main">
        <span class="participant-name">${escapeHtml(participant.display_name)}</span>
        <span class="participant-role">${escapeHtml(liveness)}${activeModels.length ? ` · ${escapeHtml(activeModels.join(", "))}` : ""} · ${escapeHtml(participant.role || participant.kind)}</span>
        ${focusedCard ? `<span class="participant-role">Focused: ${escapeHtml(focusedCard.external_id || focusedCard.title)}</span>` : ""}
        ${activeCardSummary ? `<span class="participant-role">Cards: ${escapeHtml(activeCardSummary)}</span>` : ""}
        ${instanceRows ? `<span class="participant-instances">${instanceRows}</span>` : ""}
      </span>
    `;
    row.addEventListener("click", () => openParticipantDialog(participant));
    participantsEl.appendChild(row);
  });
}

function renderActivity() {
  const events = (state.snapshot?.events || []).slice().reverse();
  activityEl.innerHTML = "";
  activityEl.setAttribute("aria-busy", state.activityLoading ? "true" : "false");
  events.forEach((event) => {
    const item = document.createElement("li");
    item.className = "activity-item";
    const row = document.createElement("button");
    const relatedCards = relatedCardsForEvent(event);
    const cardSummary = relatedCardSummary(relatedCards);
    const runtime = [event.metadata?.model, event.metadata?.turn_id].filter(Boolean).join(" · ");
    row.type = "button";
    row.className = `activity-row ${relatedCards.length ? "activity-row-linked" : ""}`;
    row.disabled = !relatedCards.length;
    row.title = relatedCards.length ? `Open ${cardSummary}` : "";
    row.innerHTML = `
      <span class="status-dot"></span>
      <span class="activity-main">
        <span class="activity-message">${escapeHtml(event.event_type)} ${escapeHtml(normalizeNewlines(event.message || ""))}</span>
        <span class="activity-meta">${escapeHtml(normalizeNewlines(event.card_external_id || ""))} ${escapeHtml(event.participant_id || "")} ${timeAgo(event.created_at)}${runtime ? ` · ${escapeHtml(runtime)}` : ""}${cardSummary ? ` · ${escapeHtml(cardSummary)}` : ""}</span>
      </span>
    `;
    if (relatedCards.length) {
      row.addEventListener("click", () => openEventCards(event));
    }
    item.appendChild(row);
    activityEl.appendChild(item);
  });
}

async function openEventCard(reference) {
  if (!reference?.id) return;
  const visibleCard = cardById(reference?.id);
  if (visibleCard) {
    openCardDialog(visibleCard);
    return;
  }
  try {
    const card = await api(`/api/cards/${encodeURIComponent(reference.id)}`);
    openCardDialog(card);
  } catch (error) {
    window.alert(`Could not open ${text(reference?.external_id, "card")}: ${error.message}`);
  }
}

function openEventCards(event) {
  const relatedCards = relatedCardsForEvent(event);
  if (!relatedCards.length) return;
  if (relatedCards.length === 1) {
    openEventCard(relatedCards[0]);
    return;
  }
  renderEventCardPicker(relatedCards);
  eventCardPickerDialog.showModal();
}

function renderEventCardPicker(cards) {
  eventCardPickerListEl.innerHTML = "";
  cards.forEach((card) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "event-card-picker-option";
    button.title = relatedCardLabel(card);
    button.innerHTML = `
      <span class="event-card-picker-number">${escapeHtml(text(card.external_id, `#${card.id}`))}</span>
      <span class="event-card-picker-main">
        <span class="event-card-picker-title">${escapeHtml(text(card.title, "Untitled"))}</span>
        <span class="event-card-picker-meta">${escapeHtml(text(card.status, "unknown"))}${card.archived ? ` <span class="chip archived-chip">archived</span>` : ""}</span>
      </span>
    `;
    button.addEventListener("click", () => {
      eventCardPickerDialog.close();
      openEventCard(card);
    });
    eventCardPickerListEl.appendChild(button);
  });
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
  cardForm.elements.intake_kind.value = card?.intake_kind || "";
  cardForm.elements.intake_source.value = card ? card?.intake_source || "" : "dashboard";
  cardForm.elements.reported_by.value = card?.reported_by || "";
  cardForm.elements.impact.value = card?.impact || "";
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
  cardForm.elements.affected_paths.value = Array.isArray(card?.affected_paths)
    ? card.affected_paths.map(normalizeNewlines).join("\n")
    : "";
  cardForm.elements.deployment_dispositions.value = Array.isArray(card?.deployment_dispositions)
    ? card.deployment_dispositions.map(deploymentDispositionText).join("\n")
    : "";
  cardForm.elements.evidence.value = normalizeNewlines(card?.evidence || "");
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
  payload.affected_paths = formList(payload.affected_paths);
  payload.deployment_dispositions = formList(payload.deployment_dispositions);
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
  if (state.fallbackPollTimer) {
    clearInterval(state.fallbackPollTimer);
    state.fallbackPollTimer = null;
  }
  const params = new URLSearchParams();
  if (state.board) params.set("board", state.board);
  if (state.showArchived) params.set("archived_only", "1");
  const suffix = params.toString();
  const path = suffix ? `/api/events/stream?${suffix}` : "/api/events/stream";
  const events = new EventSource(path);
  state.eventSource = events;
  events.addEventListener("open", () => {
    if (state.fallbackPollTimer) {
      clearInterval(state.fallbackPollTimer);
      state.fallbackPollTimer = null;
    }
    setLiveState("Live", "connected");
  });
  events.addEventListener("snapshot", (event) => render(JSON.parse(event.data)));
  events.addEventListener("change", () => {
    clearTimeout(state.refreshTimer);
    state.refreshTimer = setTimeout(() => refresh().catch(console.error), 150);
  });
  events.addEventListener("error", () => {
    setLiveState("Reconnecting", "offline");
    if (!state.fallbackPollTimer) {
      state.fallbackPollTimer = setInterval(() => refresh().catch(console.error), 10000);
    }
  });
}

async function loadMoreActivityEvents() {
  if (state.activityLoading || !state.activityHasMore || !state.snapshot) {
    return;
  }
  const events = state.snapshot.events || [];
  const beforeId = events.length ? events[0].id : state.snapshot.events_next_before_id;
  if (!beforeId) {
    state.activityHasMore = false;
    return;
  }
  state.activityLoading = true;
  renderActivity();
  try {
    const params = new URLSearchParams();
    const board = state.snapshot?.board?.slug || state.board;
    if (board) params.set("board", board);
    params.set("limit", String(state.activityPageSize));
    params.set("before_id", String(beforeId));
    const page = await api(`/api/events?${params.toString()}`);
    state.snapshot.events = mergeActivityEvents(page.events || [], state.snapshot.events || []);
    state.snapshot.events_has_more = Boolean(page.has_more);
    state.snapshot.events_next_before_id = page.next_before_id || null;
    state.activityHasMore = Boolean(page.has_more);
    state.activityExtended = true;
  } catch (error) {
    console.error(error);
  } finally {
    state.activityLoading = false;
    renderActivity();
  }
}

function loadActivityOnScroll(element) {
  element.addEventListener("scroll", () => {
    const nearEnd = element.scrollTop + element.clientHeight >= element.scrollHeight - 12;
    if (!nearEnd) return;
    loadMoreActivityEvents();
  });
}

async function switchProject(event) {
  state.board = event.target.value;
  localStorage.setItem("codex-kanban-board", state.board);
  resetActivityPaging();
  clearArchiveSelections();
  setLiveState("Switching", "");
  connectEvents();
}

async function toggleArchived(event) {
  state.showArchived = event.target.checked;
  localStorage.setItem("codex-kanban-show-archived", state.showArchived ? "1" : "0");
  resetActivityPaging();
  clearArchiveSelections();
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
document.querySelector("#settings-button").addEventListener("click", () => projectSettings.openSettingsDialog());
showArchivedToggleEl.addEventListener("change", toggleArchived);
archiveActionButton.addEventListener("click", applyArchiveAction);
archiveOldDoneButton.addEventListener("click", archiveOld.archiveOldDone);
deleteCardButton.addEventListener("click", deleteCurrentCard);
runCardNowButton.addEventListener("click", () => runCardNow());
addCommentButton.addEventListener("click", addCurrentComment);
settingsDialog.querySelectorAll(".settings-close").forEach((button) => {
  button.addEventListener("click", () => settingsDialog.close());
});
eventCardPickerDialog.querySelectorAll(".event-card-picker-close").forEach((button) => {
  button.addEventListener("click", () => eventCardPickerDialog.close());
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
loadActivityOnScroll(activityEl);

connectEvents();
})();
