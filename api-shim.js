/*
 * api-shim.js — lets the dashboard run with NO backend, for the GitHub Pages build.
 *
 * The local app has a thin FastAPI backend (onboarding/server.py) with two drivers:
 * "cached" (replay a frozen real run from demo_cache/*.json) and "live" (drive the real
 * GPT-4o agents). The DEFAULT is cached — instant, deterministic, never calls the API.
 * That default is entirely reproducible in the browser, so this shim mirrors server.py's
 * cached driver exactly and intercepts the four /api/* calls the frontend makes. No
 * server, no Python, no key — just static files on a CDN.
 *
 * Live mode is intentionally NOT available here: it needs the Python backend + an OpenAI
 * key, and a public URL must not carry a key. Run the app locally for the live toggle.
 *
 * Load order matters: this file must run BEFORE app.js so window.fetch is already
 * wrapped by the time the app makes its first call.
 */
(function () {
  // session_id -> { hire_id, cache, step_index, last_view }. Same idea as server.py's
  // in-memory _SESSIONS dict — lives for the page's lifetime, no persistence needed.
  const SESSIONS = new Map();
  let counter = 0;
  const newId = () => "s" + (counter++).toString(36);

  function viewForStep(cache, i) {
    // Mirror _start_cached / _advance_cached: show steps[i], or the final screen once
    // we've walked past the last frozen step.
    const steps = cache.steps || [];
    return i < steps.length ? steps[i] : cache.final;
  }

  // Same readable, never-a-stack-trace shape as server.py's _error_view.
  function errorView(hireId) {
    return {
      session_id: null,
      mode: "error",
      view: {
        ok: false, state: "error", hire: null, orchestrator: null,
        stages: [], pending_gate: null, events: [],
        message:
          "No cached run is available for " + hireId + " in this hosted demo. " +
          "Nothing was provisioned. Pick another hire, or run the app locally for live mode.",
      },
    };
  }

  function expired() {
    return {
      ok: false, state: "expired",
      message: "This session expired. Pick the hire again to restart.",
    };
  }

  async function loadCache(hireId) {
    // Relative path so it resolves under the Pages project subpath (…/onboarding-multi-agents/).
    const r = await realFetch("demo_cache/" + hireId + ".json");
    if (!r.ok) throw new Error("no cache for " + hireId);
    return r.json();
  }

  // Returns a plain object (the JSON body) for a matched /api/* route, or the sentinel
  // PASS to mean "not ours — let the real network handle it".
  const PASS = Symbol("pass");

  async function route(url, init) {
    const body = init && init.body ? JSON.parse(init.body) : {};

    // GET /api/profiles — the picker's roster (pre-generated at build time).
    if (url.includes("/api/profiles")) {
      const r = await realFetch("profiles.json");
      return r.json();
    }

    // POST /api/run — start a run: load the frozen cache, hand back the first screen.
    if (url.includes("/api/run")) {
      const hireId = body.hire_id;
      let cache;
      try {
        cache = await loadCache(hireId);
      } catch (e) {
        return errorView(hireId);
      }
      const sid = newId();
      const view = viewForStep(cache, 0);
      SESSIONS.set(sid, { hire_id: hireId, cache, step_index: 0, last_view: view });
      return { session_id: sid, mode: "cached", view };
    }

    // POST /api/session/{id}/gate — a gate click: advance one frozen screen.
    let m = url.match(/\/api\/session\/([^/]+)\/gate/);
    if (m) {
      const sess = SESSIONS.get(m[1]);
      if (!sess) return expired();
      sess.step_index += 1;
      sess.last_view = viewForStep(sess.cache, sess.step_index);
      return { session_id: m[1], mode: "cached", view: sess.last_view };
    }

    // GET /api/session/{id} — re-fetch the current screen.
    m = url.match(/\/api\/session\/([^/]+)$/);
    if (m) {
      const sess = SESSIONS.get(m[1]);
      if (!sess) return expired();
      return { session_id: m[1], mode: "cached", view: sess.last_view };
    }

    return PASS;
  }

  const realFetch = window.fetch.bind(window);

  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    if (url.includes("/api/")) {
      const data = await route(url, init || {});
      if (data !== PASS) {
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
    }
    return realFetch(input, init);
  };
})();
