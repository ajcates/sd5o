// Same-origin-controlled replacement for the free third-party CORS proxy
// chain in src/app/calls-list.js. Those proxies (cors-get-proxy, allorigins,
// cors.lol) die or get rate-limited on a rolling basis because they're
// shared, unauthenticated, and have no uptime guarantee. This Worker is ours:
// it forwards to the CAD API and adds the CORS header itself, and holds the
// function key as a secret instead of shipping it in client source
// (see notes/offgeo/todo.md OFF-011).

const UPSTREAM_URL = "https://leag-caddata-dev-fa-leag-caddata-dev-fa-blue.azurewebsites.us/api/GetCADEvents";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: CORS_HEADERS });
    }

    const upstream = new URL(UPSTREAM_URL);
    upstream.searchParams.set("code", env.CAD_FUNCTION_KEY);
    upstream.searchParams.set("_", Date.now().toString());

    const response = await fetch(upstream, { cf: { cacheTtl: 0 } });
    const body = await response.text();

    return new Response(body, {
      status: response.status,
      headers: {
        ...CORS_HEADERS,
        "Content-Type": response.headers.get("Content-Type") || "application/json",
        "Cache-Control": "no-store",
      },
    });
  },
};
