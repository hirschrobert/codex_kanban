window.Kanban = window.Kanban || {};

{
  const {
    state,
    activeConflictStatuses,
    localCommentAuthorName,
    legacyLocalCommentAuthorNames,
  } = window.Kanban;

  function text(value, fallback = "") {
    return value == null || value === "" ? fallback : String(value);
  }

  function normalizeNewlines(value) {
    return text(value)
      .replaceAll("\\r\\n", "\n")
      .replaceAll("\\n", "\n")
      .replaceAll("\\r", "\n")
      .replaceAll("\r\n", "\n")
      .replaceAll("\r", "\n");
  }

  function timeAgo(value) {
    if (!value) return "";
    const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(value)) / 1000));
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    if (hours < 48) return `${hours}h`;
    return `${Math.floor(hours / 24)}d`;
  }

  function dateTimeLabel(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return text(value);
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  }

  function participantName(id) {
    const participant = (state.snapshot?.participants || []).find((item) => item.id === id);
    return participant ? participant.display_name : id || "Unassigned";
  }

  function participantKind(id) {
    const participant = (state.snapshot?.participants || []).find((item) => item.id === id);
    return participant ? participant.kind : "human";
  }

  function agentInstanceName(instance) {
    const id = text(instance?.id, "agent");
    return id.length > 18 ? `…${id.slice(-12)}` : id;
  }

  function agentInstanceSummary(instance) {
    return [
      normalText(instance?.agent_type),
      text(instance?.status, "idle"),
      normalText(instance?.model),
      normalText(instance?.current_card_external_id),
      timeAgo(instance?.last_seen_at),
    ]
      .filter(Boolean)
      .join(" · ");
  }

  function commentAuthorName(comment) {
    const authorName = comment.author_name || comment.participant_id || "Unknown";
    if (legacyLocalCommentAuthorNames.has(authorName.toLowerCase())) {
      return localCommentAuthorName;
    }
    return authorName;
  }

  function cardById(id) {
    return (state.snapshot?.cards || []).find((card) => String(card.id) === String(id));
  }

  function relatedCardsForEvent(event) {
    const related = Array.isArray(event?.related_cards) ? event.related_cards : [];
    const cards = [];
    const seen = new Set();
    function add(card) {
      if (!card) return;
      const id = card.id == null ? "" : String(card.id);
      const externalId = text(card.external_id);
      const key = id ? `id:${id}` : externalId ? `external:${externalId}` : "";
      if (!key || seen.has(key)) return;
      cards.push(card);
      seen.add(key);
    }
    related.forEach(add);
    if (!cards.length) {
      add(cardById(event?.card_id));
      if (event?.card_external_id) {
        add(
          (state.snapshot?.cards || []).find(
            (card) => String(card.external_id) === String(event.card_external_id)
          )
        );
      }
    }
    return cards;
  }

  function relatedCardLabel(card) {
    return `${text(card.external_id, card.id ? `#${card.id}` : "Card")} ${text(card.title)}`.trim();
  }

  function relatedCardSummary(cards) {
    if (!cards.length) return "";
    const archivedCount = cards.filter((card) => card.archived).length;
    if (cards.length === 1) {
      const card = cards[0];
      return `${text(card.external_id, card.id ? `#${card.id}` : "Card")}${card.archived ? " archived" : ""}`;
    }
    return `${cards.length} cards${archivedCount ? `, ${archivedCount} archived` : ""}`;
  }

  function archiveSelectionKey(card) {
    return String(card.id);
  }

  function initialArchiveSelection(card) {
    return state.showArchived ? Boolean(card.archived) : false;
  }

  function archiveSelection(card) {
    const key = archiveSelectionKey(card);
    if (!Object.prototype.hasOwnProperty.call(state.archiveSelections, key)) {
      state.archiveSelections[key] = initialArchiveSelection(card);
    }
    return Boolean(state.archiveSelections[key]);
  }

  function archiveActionTargets() {
    const cards = visibleCards();
    if (state.showArchived) {
      return cards.filter((card) => card.archived && !archiveSelection(card));
    }
    return cards.filter((card) => !card.archived && archiveSelection(card));
  }

  function clearArchiveSelections() {
    state.archiveSelections = {};
  }

  function visibleCards() {
    const cards = state.snapshot?.cards || [];
    return cards.filter((card) => (state.showArchived ? card.archived : !card.archived));
  }

  function normalText(value) {
    return text(value).trim();
  }

  function normalPath(value) {
    return normalText(value).replace(/\/+/g, "/").replace(/\/$/, "");
  }

  function listValues(value) {
    return Array.isArray(value) ? value.map(normalPath).filter(Boolean) : [];
  }

  function formList(value) {
    return text(value)
      .split(/\r?\n|,/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function coordinationWarningsForCard(card) {
    if (!activeConflictStatuses.has(card?.status)) return [];
    const warnings = [];
    if (!normalText(card.target_branch)) {
      warnings.push(
        "Target branch is empty. Use or create the current release branch; workflow automation must not target main or master."
      );
    }
    if (normalText(card.feature_branch) && !normalText(card.worktree_path)) {
      warnings.push(
        "Feature branch has no worktree path. Add the worktree path before handing off isolated branch work."
      );
    }
    return warnings;
  }

  function conflictReasons(left, right) {
    if (!activeConflictStatuses.has(left?.status) || !activeConflictStatuses.has(right?.status)) {
      return [];
    }
    const reasons = [];
    const leftRepo = normalPath(left.target_repo);
    const rightRepo = normalPath(right.target_repo);
    const leftBranch = normalText(left.target_branch);
    const rightBranch = normalText(right.target_branch);
    const leftFeature = normalText(left.feature_branch);
    const rightFeature = normalText(right.feature_branch);
    const leftWorktree = normalPath(left.worktree_path);
    const rightWorktree = normalPath(right.worktree_path);
    if (leftRepo && leftRepo === rightRepo) {
      if (!leftBranch || !rightBranch) {
        reasons.push("same target repo with a missing target branch");
      } else if (
        leftBranch === rightBranch &&
        !(leftFeature && rightFeature && leftFeature !== rightFeature)
      ) {
        reasons.push(
          `same target repo and branch without distinct feature branches: ${leftBranch}`
        );
      }
    }

    if (leftFeature && leftFeature === rightFeature) {
      reasons.push(`same feature branch: ${leftFeature}`);
    }

    if (leftWorktree && leftWorktree === rightWorktree) {
      reasons.push(`same worktree path: ${leftWorktree}`);
    }

    const rightFiles = new Set(listValues(right.files_changed));
    const sharedFiles = listValues(left.files_changed).filter((item) => rightFiles.has(item));
    if (sharedFiles.length) {
      const shown = sharedFiles.slice(0, 4).join(", ");
      reasons.push(`same declared files: ${shown}${sharedFiles.length > 4 ? "..." : ""}`);
    }
    return reasons;
  }

  function potentialConflicts(card) {
    return (state.snapshot?.cards || [])
      .filter((other) => String(other.id) !== String(card.id))
      .map((other) => ({
        card_id: other.id,
        external_id: other.external_id,
        title: other.title,
        status: other.status,
        reasons: conflictReasons(card, other),
      }))
      .filter((conflict) => conflict.reasons.length);
  }

  function conflictText(conflict) {
    const label = conflict.external_id || `#${conflict.card_id}`;
    return `${label}: ${conflict.reasons.join("; ")}`;
  }

  const coordinationConfirmationFields = [
    "status",
    "target_repo",
    "target_branch",
    "feature_branch",
    "worktree_path",
    "files_changed",
  ];

  function coordinationFieldValue(card, field) {
    if (field === "files_changed") {
      return JSON.stringify(listValues(card?.[field]));
    }
    return normalText(card?.[field]);
  }

  function coordinationConfirmationNeeded(currentCard, proposedCard) {
    if (!currentCard) return true;
    return coordinationConfirmationFields.some(
      (field) =>
        coordinationFieldValue(currentCard, field) !== coordinationFieldValue(proposedCard, field)
    );
  }

  function assigneeChipText(card) {
    const name = participantName(card.assignee_id);
    if (!card.assignee) return name;
    if (card.assignee.is_stale) return `${name} · stale`;
    if (card.assignee.is_active) return `${name} · active`;
    return `${name} · ${card.assignee.status || "idle"}`;
  }

  function cardOwnerText(card) {
    const ownerName = normalText(card?.owner?.display_name);
    if (ownerName) return ownerName;
    const ownerId = normalText(card?.owner_id);
    if (ownerId) return participantName(ownerId);
    return "Untracked";
  }

  function cardCreatorText(card) {
    const creatorName = normalText(card?.created_by?.display_name || card?.created_by_name);
    if (creatorName) return creatorName;
    const creatorId = normalText(card?.created_by_id);
    if (creatorId) return participantName(creatorId);
    return "Untracked";
  }

  function titleCaseToken(value) {
    return normalText(value)
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function intakeKindText(card) {
    return titleCaseToken(card?.intake_kind);
  }

  function intakeSourceText(card) {
    return titleCaseToken(card?.intake_source);
  }

  function affectedProjectPathText(item) {
    if (!item || typeof item !== "object") return text(item);
    const label = normalText(item.label);
    const path = normalText(item.path);
    return label && path ? `${label}: ${path}` : label || path;
  }

  function deploymentDispositionText(item) {
    if (!item || typeof item !== "object") return text(item);
    const label = normalText(item.label);
    const path = normalText(item.path);
    const status = normalText(item.status) || "pending";
    const note = normalText(item.note);
    const target = label && path ? `${label}|${path}` : label || path;
    return `${target}=${status}${note ? `:${note}` : ""}`;
  }

  function confirmCoordination(card) {
    if (!activeConflictStatuses.has(card?.status)) return true;
    const conflicts = potentialConflicts(card);
    const warnings = coordinationWarningsForCard(card);
    if (!conflicts.length && !warnings.length) return true;

    const lines = [];
    if (conflicts.length) {
      lines.push("Possible active-card conflict:");
      conflicts.forEach((conflict) => lines.push(`- ${conflictText(conflict)}`));
    }
    if (warnings.length) {
      lines.push("Coordination warning:");
      warnings.forEach((warning) => lines.push(`- ${warning}`));
    }
    lines.push("Continue anyway?");
    return window.confirm(lines.join("\n"));
  }

  Object.assign(window.Kanban, {
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
    initialArchiveSelection,
    archiveSelection,
    archiveActionTargets,
    clearArchiveSelections,
    visibleCards,
    normalText,
    normalPath,
    listValues,
    formList,
    coordinationWarningsForCard,
    conflictReasons,
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
  });
}
