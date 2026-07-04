window.Kanban = window.Kanban || {};

function api(path, options = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
  return fetch(path, Object.assign({}, options, { headers })).then(async (response) => {
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.error || response.statusText);
    }
    return body;
  });
}

window.Kanban.api = api;
