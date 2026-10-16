"use strict";

// API binary cells use {hex: "..."}; display/export them as 0x-prefixed hex.
function formatCell(value) {
  if (value && typeof value === "object" && !Array.isArray(value) &&
      Object.keys(value).length === 1 && typeof value.hex === "string" && /^(?:[0-9a-f]{2})*$/i.test(value.hex)) {
    return "0x" + value.hex;
  }
  return String(value);
}

// Quote every cell and neutralize spreadsheet formulas, including whitespace-prefixed ones.
function csvCell(value) {
  let text = value === null || value === undefined ? "" : formatCell(value);
  if (/^[\s\uFEFF]*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text)) text = "'" + text;
  return '"' + text.replace(/"/g, '""') + '"';
}

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { status: null, busy: null, results: null, history: [], edited: false };
  const historyKey = "querycraft.history.v1";
  const question = $("question");
  const sql = $("sql");
  // Collapse only on initial mobile load; subsequent user toggles are preserved.
  if (window.matchMedia("(max-width: 720px)").matches) {
    document.querySelector(".schema-disclosure").open = false;
  }

  function announce(message) { $("announcement").textContent = message; }
  function error(id, message) {
    $(id).textContent = message || "";
    $(id).hidden = !message;
  }
  function updateControls() {
    const busy = Boolean(state.busy);
    const ready = Boolean(state.status);
    question.disabled = !ready;
    question.readOnly = busy;
    sql.disabled = !ready;
    sql.readOnly = busy;
    $("provider").disabled = busy || !ready;
    const selectedMode = $("provider").selectedOptions[0];
    $("generate").disabled = busy || !ready || !selectedMode || selectedMode.disabled;
    $("run").disabled = busy || !ready || !sql.value.trim();
    $("copy").disabled = busy || !sql.value.trim();
    $("download").disabled = busy || !state.results;
    $("reset").disabled = busy;
    document.querySelectorAll(".example-button, .history-item").forEach((button) => { button.disabled = busy; });
    $("generate").textContent = state.busy === "generate" ? "Generating…" : "Generate SQL ↗";
    $("run").textContent = state.busy === "execute" ? "Running…" : "▷ Run query";
    $("question-form").setAttribute("aria-busy", String(state.busy === "generate"));
    $("results-section").setAttribute("aria-busy", String(state.busy === "execute"));
  }
  function emptyResults(title, message) {
    state.results = null;
    $("results-table-wrap").hidden = true;
    $("results-head").replaceChildren();
    $("results-body").replaceChildren();
    $("results-meta").textContent = "";
    $("truncated").hidden = true;
    $("results-empty").hidden = false;
    $("results-empty").querySelector("h3").textContent = title;
    $("results-empty").querySelector("p").textContent = message;
    updateControls();
  }
  function invalidateResults() {
    if (state.results) {
      emptyResults("Your query has changed.", "Run the query again to see current results. Previous results have been cleared.");
      announce("Query changed. Previous results cleared.");
    }
    error("execute-error", "");
    updateControls();
  }
  function hideNotes() { $("generation-notes").hidden = true; }
  function setQuestion(text) {
    question.value = text;
    invalidateResults();
    hideNotes();
    error("generate-error", "");
    $("sql-state").textContent = sql.value.trim() ? "Previous SQL · regenerate to match" : "Editable · SQLite";
    question.focus();
  }
  async function request(path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 65000);
    try {
      const response = await fetch(path, {
        method: body === undefined ? "GET" : "POST",
        headers: body === undefined ? { Accept: "application/json" } : { "Content-Type": "application/json", Accept: "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
        credentials: "same-origin"
      });
      let data;
      try { data = await response.json(); }
      catch (_) { throw new Error("The server returned an unreadable response. Please try again."); }
      if (!response.ok) throw new Error(data.error || "The request failed. Please try again.");
      return data;
    } catch (failure) {
      if (failure.name === "AbortError") throw new Error("The request timed out. Please try again.");
      if (failure instanceof TypeError) throw new Error("Unable to reach the server. Check your connection and try again.");
      throw failure;
    } finally { clearTimeout(timeout); }
  }
  function renderHistory() {
    const root = $("history");
    root.replaceChildren();
    $("history-count").textContent = String(state.history.length);
    if (!state.history.length) {
      const p = document.createElement("p"); p.className = "muted"; p.textContent = "Your queries will appear here."; root.append(p);
    }
    state.history.forEach((entry) => {
      const button = document.createElement("button");
      button.type = "button"; button.className = "history-item";
      button.textContent = entry.question || entry.sql;
      button.title = entry.question || entry.sql;
      button.addEventListener("click", () => {
        if (state.busy) return;
        question.value = entry.question;
        sql.value = entry.sql;
        hideNotes();
        emptyResults("Restored, not yet run.", "Review the restored SQL and select Run query to get fresh results.");
        error("generate-error", ""); error("execute-error", "");
        $("sql-state").textContent = "Restored · review before running";
        sql.focus();
      });
      root.append(button);
    });
  }
  function saveHistory() {
    const entry = { question: question.value.trim(), sql: sql.value.trim() };
    if (!entry.sql) return;
    state.history = [entry, ...state.history.filter((item) => item.sql !== entry.sql || item.question !== entry.question)].slice(0, 10);
    try { sessionStorage.setItem(historyKey, JSON.stringify(state.history)); } catch (_) { /* Storage is optional. */ }
    renderHistory(); updateControls();
  }
  function modeChanged() {
    const ai = $("provider").value === "llm";
    const needsSetup = ai && state.status && !state.status.llm_configured;
    $("mode-help").textContent = needsSetup ? "Configure an AI provider in Connection & settings to generate SQL, or enter a query manually below." : ai ? "AI-generated SQL can be incorrect. Check the query and its assumptions before running." : "Demo mode uses a limited set of templates, not arbitrary natural-language generation.";
    $("mode-caption").textContent = ai ? "AI provider → SQLite" : "Demo templates → SQLite";
    $("question-hint").textContent = ai ? "Be specific about measures, filters, and dates." : "Use a supported example in demo mode.";
    error("generate-error", "");
  }
  async function loadStatus() {
    $("setup-error").hidden = true;
    $("setup-retry").disabled = true;
    $("connection").className = "connection";
    $("connection").textContent = "Connecting…";
    try {
      const data = await request("/api/status");
      if (!data.database || !Array.isArray(data.examples)) throw new Error("The server status is incomplete. Try connecting again.");
      state.status = data;
      $("database-name").textContent = data.database.name;
      $("database-kind").textContent = data.database.kind === "demo" ? "SQLite · sample database" : "SQLite · custom database";
      $("connection").textContent = "Connected · SQLite";
      $("connection").className = "connection connected";
      $("data-notice-text").textContent = data.database.kind === "demo" ? "Synthetic ecommerce demo · Sample data, not a real store. Demo templates support only the example question patterns." : "Your SQLite database · Review table names and relationships before writing queries. Demo templates may not match this schema.";
      $("data-notice").querySelector(".notice-label").textContent = data.database.kind === "demo" ? "SAMPLE DATA" : "CUSTOM DATABASE";
      const llmOption = $("provider").querySelector('[value="llm"]');
      $("provider").querySelector('[value="demo"]').disabled = data.database.kind !== "demo";
      if (data.database.kind !== "demo") $("provider").value = "llm";
      llmOption.disabled = !data.llm_configured;
      llmOption.textContent = data.llm_configured ? "AI provider" : "AI provider · not configured";
      $("model-info").textContent = data.llm_configured ? "Configured model: " + (data.model || "server default") : data.database.kind === "demo" ? "AI provider not configured. Demo templates are available without an API key." : "AI provider not configured. Enter SQL manually or configure a provider to generate it.";
      $("row-limit").textContent = "Read-only queries · up to " + data.max_rows + " rows";
      const examples = $("examples"); examples.replaceChildren();
      data.examples.forEach((example) => {
        const button = document.createElement("button");
        button.type = "button"; button.className = "example-button"; button.textContent = example;
        button.addEventListener("click", () => { if (!state.busy) setQuestion(example); }); examples.append(button);
      });
      if (!data.examples.length) { const text = document.createElement("span"); text.className = "muted"; text.textContent = "No demo examples for this database. Write SQL directly or configure an AI provider."; examples.append(text); }
      modeChanged();
    } catch (failure) {
      $("setup-error-text").textContent = failure.message;
      $("setup-error").hidden = false;
      $("connection").textContent = "Connection unavailable";
      $("connection").className = "connection failed";
      $("database-name").textContent = "Not connected";
      $("data-notice-text").textContent = "Reconnect to load your database and available generation modes.";
    } finally { $("setup-retry").disabled = false; updateControls(); }
  }
  async function loadSchema() {
    $("schema-retry").hidden = true;
    $("schema").textContent = "Loading schema…";
    try {
      const data = await request("/api/schema");
      if (!Array.isArray(data.tables)) throw new Error("The server returned an invalid schema.");
      $("schema").replaceChildren();
      $("table-count").textContent = String(data.tables.length);
      data.tables.forEach((table) => {
        const details = document.createElement("details"); details.className = "schema-table"; details.open = true;
        const summary = document.createElement("summary"); summary.textContent = table.name; details.append(summary);
        const list = document.createElement("ul"); list.className = "schema-columns";
        const foreignKeys = table.foreign_keys || [];
        table.columns.forEach((column) => {
          const li = document.createElement("li");
          const name = document.createElement("span"); name.className = "column-name"; name.textContent = column.name; li.append(name);
          if (column.primary_key) { const pk = document.createElement("span"); pk.className = "key"; pk.textContent = "PK"; pk.title = "Primary key"; li.append(pk); }
          foreignKeys.filter((fk) => fk.from === column.name).forEach((fk) => { const key = document.createElement("span"); key.className = "key"; key.textContent = "↗"; key.title = "Foreign key to " + fk.table + "." + fk.to; key.setAttribute("aria-label", key.title); li.append(key); });
          const type = document.createElement("span"); type.className = "column-type"; type.textContent = column.type || "ANY"; li.append(type); list.append(li);
        });
        details.append(list);
        foreignKeys.forEach((fk) => { const p = document.createElement("p"); p.className = "foreign-key"; p.textContent = fk.from + " → " + fk.table + "." + fk.to; details.append(p); });
        $("schema").append(details);
      });
      if (!data.tables.length) $("schema").textContent = "No tables were found in this database.";
    } catch (failure) { $("schema").textContent = failure.message; $("schema-retry").hidden = false; }
  }
  async function generate(event) {
    event.preventDefault();
    if (state.busy || !state.status) return;
    error("generate-error", "");
    if (!$("provider").selectedOptions[0] || $("provider").selectedOptions[0].disabled) {
      error("generate-error", "Configure an AI provider for this database, or enter SQL manually.");
      return;
    }
    if (!question.value.trim()) { error("generate-error", "Enter a question or choose an example before generating SQL."); question.focus(); return; }
    if (question.value.length > 4000) { error("generate-error", "Keep your question under 4,000 characters."); return; }
    state.busy = "generate";
    hideNotes();
    emptyResults("Preparing your query…", "Generation does not run SQL. You will review the query before executing it.");
    error("execute-error", "");
    updateControls(); announce("Generating SQL. Your database has not been queried.");
    try {
      const data = await request("/api/generate", { question: question.value.trim(), mode: $("provider").value });
      if (typeof data.sql !== "string" || !data.sql.trim()) throw new Error("The provider returned no SQL. Try another question.");
      sql.value = data.sql;
      $("sql-state").textContent = "Generated · review before running";
      $("explanation").textContent = data.explanation || "Review this SQL before running it.";
      $("assumptions").replaceChildren();
      (data.assumptions || []).forEach((assumption) => { const li = document.createElement("li"); li.textContent = assumption; $("assumptions").append(li); });
      $("assumptions-detail").hidden = !(data.assumptions || []).length;
      $("assumptions-detail").open = true;
      $("generated-provider").textContent = "Generated with " + (data.provider || $("provider").value);
      $("generation-notes").hidden = false;
      emptyResults("SQL is ready. Your data is untouched.", "Inspect the query above, then select Run query to see the results.");
      saveHistory(); announce("SQL generated. Review it and select Run query when ready.");
    } catch (failure) {
      error("generate-error", failure.message + " You can edit the question and select Generate SQL to retry.");
      emptyResults("No new query generated.", "Resolve the error above and try again. Any SQL still in the editor is from before this attempt.");
      $("sql-state").textContent = sql.value.trim() ? "Previous SQL · generation failed" : "Editable · SQLite";
    } finally { state.busy = null; updateControls(); }
  }
  function renderResults(data) {
    if (!Array.isArray(data.columns) || !Array.isArray(data.rows)) throw new Error("The server returned invalid query results.");
    state.results = data;
    $("results-head").replaceChildren(); $("results-body").replaceChildren();
    const heading = document.createElement("tr");
    data.columns.forEach((column) => { const th = document.createElement("th"); th.scope = "col"; th.textContent = column; heading.append(th); });
    $("results-head").append(heading);
    const fragment = document.createDocumentFragment();
    data.rows.forEach((row) => {
      const tr = document.createElement("tr");
      data.columns.forEach((_, index) => { const td = document.createElement("td"); const value = row[index]; td.textContent = value === null || value === undefined ? "NULL" : formatCell(value); if (value === null || value === undefined) td.className = "null-value"; tr.append(td); });
      fragment.append(tr);
    });
    $("results-body").append(fragment);
    $("results-table-wrap").hidden = !data.rows.length;
    $("results-empty").hidden = Boolean(data.rows.length);
    if (!data.rows.length) { $("results-empty").querySelector("h3").textContent = "The query returned no rows."; $("results-empty").querySelector("p").textContent = "The query ran successfully. Try adjusting your filters or date range."; }
    const elapsed = Number(data.elapsed_ms);
    $("results-meta").textContent = data.row_count + (data.row_count === 1 ? " row" : " rows") + (Number.isFinite(elapsed) ? " · " + elapsed.toFixed(1) + " ms" : "");
    $("truncated").hidden = !data.truncated;
    $("truncated").title = "Only the first " + state.status.max_rows + " rows are shown and exported.";
    announce("Query complete. " + data.row_count + " rows returned." + (data.truncated ? " Results are truncated." : ""));
  }
  async function execute() {
    if (state.busy || !state.status || !sql.value.trim()) return;
    state.busy = "execute";
    error("execute-error", "");
    emptyResults("Running your query…", "Waiting for the database. Only read-only SQL is allowed.");
    updateControls(); announce("Running query.");
    try {
      const data = await request("/api/execute", { sql: sql.value.trim() });
      renderResults(data); saveHistory();
    } catch (failure) {
      error("execute-error", failure.message + " Review the SQL and select Run query to retry.");
      emptyResults("The query could not be completed.", "No results are available. Review the error above and try again.");
    } finally { state.busy = null; updateControls(); }
  }
  $("question-form").addEventListener("submit", generate);
  $("run").addEventListener("click", execute);
  $("provider").addEventListener("change", modeChanged);
  $("schema-retry").addEventListener("click", loadSchema);
  $("setup-retry").addEventListener("click", () => { loadStatus(); loadSchema(); });
  question.addEventListener("input", () => {
    invalidateResults(); hideNotes(); error("generate-error", "");
    $("sql-state").textContent = sql.value.trim() ? "Previous SQL · regenerate to match" : "Editable · SQLite";
  });
  sql.addEventListener("input", () => { invalidateResults(); hideNotes(); $("sql-state").textContent = "Edited · review before running"; });
  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") { event.preventDefault(); if (!state.busy && state.status) $("question-form").requestSubmit(); }
  });
  $("reset").addEventListener("click", () => {
    if (state.busy) return;
    question.value = ""; sql.value = ""; hideNotes();
    error("generate-error", ""); error("execute-error", "");
    $("sql-state").textContent = "Editable · SQLite";
    emptyResults("Your answer starts with a query.", "Generate SQL above, review it, and select Run query. No data has been queried yet.");
    question.focus(); announce("New query. Editor and results cleared.");
  });
  $("copy").addEventListener("click", async () => {
    try {
      if (!navigator.clipboard) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(sql.value);
      $("copy").textContent = "Copied"; announce("SQL copied to clipboard.");
      setTimeout(() => { $("copy").textContent = "Copy SQL"; }, 1800);
    } catch (_) { sql.focus(); sql.select(); announce("Clipboard access unavailable. SQL is selected; use your keyboard to copy."); }
  });
  $("download").addEventListener("click", () => {
    if (!state.results || state.busy) return;
    const data = state.results;
    const csv = [data.columns, ...data.rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob(["\uFEFF" + csv + "\r\n"], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "querycraft-results.csv"; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    announce("CSV downloaded. Spreadsheet formulas are escaped for safety.");
  });
  try {
    const stored = JSON.parse(sessionStorage.getItem(historyKey) || "[]");
    if (Array.isArray(stored)) state.history = stored.filter((item) => item && typeof item.sql === "string" && typeof item.question === "string").slice(0, 10).map((item) => ({ sql: item.sql, question: item.question }));
  } catch (_) { /* The workbench remains usable with storage blocked. */ }
  renderHistory(); updateControls(); loadStatus(); loadSchema();
})();
