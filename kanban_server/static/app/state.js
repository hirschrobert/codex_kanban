window.Kanban = window.Kanban || {};

const savedBoard = localStorage.getItem("codex-kanban-board") || "";
const savedShowArchived = localStorage.getItem("codex-kanban-show-archived") === "1";

const state = {
  board: savedBoard,
  snapshot: null,
  draggedCardId: null,
  eventSource: null,
  showArchived: savedShowArchived,
  activityPageSize: 10,
  activityHasMore: false,
  activityLoading: false,
  activityExtended: false,
  archiveSelections: {},
};
const priorities = new Set(["urgent", "high"]);
const activeConflictStatuses = new Set(["in_progress", "blocked"]);
const localCommentAuthorName = "local developer";
const legacyLocalCommentAuthorNames = new Set(["local human"]);
const discardMessage = "Discard unsaved changes?";

Object.assign(window.Kanban, {
  state,
  priorities,
  activeConflictStatuses,
  localCommentAuthorName,
  legacyLocalCommentAuthorNames,
  discardMessage,
});
