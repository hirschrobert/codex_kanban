window.KanbanArchiveOld = (() => {
  "use strict";

  function createController({ api, state, button, refresh }) {
    async function archiveOldDone() {
      const params = new URLSearchParams({ older_than_days: "2" });
      if (state.board) params.set("board", state.board);
      button.disabled = true;
      try {
        const preview = await api(`/api/cards/archive-candidates?${params.toString()}`);
        if (!preview.count) {
          window.alert("No unarchived done cards are older than two days.");
          return;
        }
        const cutoff = new Date(preview.cutoff).toLocaleString();
        const confirmed = window.confirm(
          `Archive ${preview.count} done card(s) last updated before ${cutoff}?`
        );
        if (!confirmed) return;
        await api("/api/cards/archive-old-done", {
          method: "POST",
          body: JSON.stringify({
            board_slug: state.snapshot?.board?.slug || state.board,
            older_than_days: 2,
            card_ids: preview.cards.map((card) => card.id),
          }),
        });
        await refresh();
      } catch (error) {
        window.alert(error.message || "Could not archive old done cards.");
      } finally {
        button.disabled = state.showArchived;
      }
    }

    return { archiveOldDone };
  }

  return { createController };
})();
