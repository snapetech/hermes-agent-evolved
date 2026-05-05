(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  const { React } = SDK;
  const { Card, CardHeader, CardTitle, CardContent, Badge, Button } = SDK.components;
  const { useEffect, useState } = SDK.hooks;

  function Pill(props) {
    return React.createElement(Badge, { variant: props.ok ? "default" : "destructive" }, props.children);
  }

  function KV(props) {
    return React.createElement("div", { className: "grid grid-cols-[180px_1fr] gap-3 border-b border-border/50 py-2 text-sm" },
      React.createElement("span", { className: "text-muted-foreground" }, props.k),
      React.createElement("span", { className: "font-courier break-all" }, String(props.v ?? ""))
    );
  }

  function Lines(props) {
    const rows = props.rows || [];
    if (!rows.length) {
      return React.createElement("div", { className: "text-sm text-muted-foreground" }, props.empty || "None");
    }
    return React.createElement("div", { className: "grid gap-2" },
      rows.map(function (row, idx) {
        return React.createElement("div", { key: idx, className: "rounded border border-border p-3 text-sm" }, row);
      })
    );
  }

  function OpsRuntimePage() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);

    function refresh() {
      setLoading(true);
      SDK.fetchJSON("/api/plugins/ops-runtime/snapshot")
        .then(setData)
        .catch(function (err) { setData({ error: String(err) }); })
        .finally(function () { setLoading(false); });
    }

    useEffect(function () {
      refresh();
      const id = setInterval(refresh, 30000);
      return function () { clearInterval(id); };
    }, []);

    const model = data && data.model || {};
    const runtime = data && data.runtime || {};
    const k8s = data && data.kubernetes || {};
    const ollama = data && data.ollama || {};
    const sessions = data && data.sessions || {};
    const cron = data && data.cron || {};
    const mcp = data && data.mcp_processes || {};
    const hooks = data && data.hooks || {};
    const alerts = data && data.alerts || [];
    const loadedModels = ollama.ok && ollama.data && Array.isArray(ollama.data.models) ? ollama.data.models : [];

    return React.createElement("div", { className: "flex flex-col gap-6" },
      React.createElement(Card, null,
        React.createElement(CardHeader, null,
          React.createElement("div", { className: "flex items-center justify-between gap-3" },
            React.createElement("div", { className: "flex items-center gap-3" },
              React.createElement(CardTitle, { className: "text-lg" }, "NOC"),
              React.createElement(Pill, { ok: alerts.length === 0 && !data?.error }, data?.error ? "error" : alerts.length ? `${alerts.length} alert(s)` : "quiet")
            ),
            React.createElement(Button, { onClick: refresh, disabled: loading }, loading ? "Refreshing..." : "Refresh")
          )
        ),
        React.createElement(CardContent, null,
          React.createElement(Lines, { rows: alerts, empty: "No runtime alerts." })
        )
      ),

      React.createElement(Card, null,
        React.createElement(CardHeader, null,
          React.createElement("div", { className: "flex items-center justify-between gap-3" },
            React.createElement("div", { className: "flex items-center gap-3" },
              React.createElement(CardTitle, { className: "text-lg" }, "Ops Runtime"),
              React.createElement(Pill, { ok: !data?.error }, data?.error ? "error" : "live")
            ),
            React.createElement(Button, { onClick: refresh, disabled: loading }, loading ? "Refreshing..." : "Refresh")
          )
        ),
        React.createElement(CardContent, null,
          React.createElement("div", { className: "grid gap-1" },
            React.createElement(KV, { k: "Hermes home", v: data && data.hermes_home }),
            React.createElement(KV, { k: "Model", v: `${model.provider || ""}:${model.default || ""}` }),
            React.createElement(KV, { k: "Context", v: `${model.context_length || ""} logical / ${model.ollama_num_ctx || ""} ollama num_ctx` }),
            React.createElement(KV, { k: "Terminal", v: `${runtime.terminal_backend || ""} @ ${runtime.terminal_cwd || ""}` }),
            React.createElement(KV, { k: "Approvals", v: runtime.approvals_mode }),
            React.createElement(KV, { k: "Checkpoints", v: JSON.stringify(runtime.checkpoints || {}) }),
            React.createElement(KV, { k: "Gateway worktrees", v: JSON.stringify(runtime.gateway_worktrees || {}) }),
            React.createElement(KV, { k: "Memory provider", v: runtime.memory_provider }),
            React.createElement(KV, { k: "MCP servers", v: (runtime.mcp_servers || []).join(", ") }),
            React.createElement(KV, { k: "Profiles", v: (runtime.profiles || []).join(", ") }),
            React.createElement(KV, { k: "Background processes", v: runtime.background_processes })
          )
        )
      ),

      React.createElement(Card, null,
        React.createElement(CardHeader, null,
          React.createElement("div", { className: "flex items-center gap-3" },
            React.createElement(CardTitle, { className: "text-base" }, "Sessions / Cron / Hooks"),
            React.createElement(Pill, { ok: !!sessions.ok && !!cron.ok }, sessions.ok && cron.ok ? "ok" : "check")
          )
        ),
        React.createElement(CardContent, null,
          React.createElement("div", { className: "grid gap-1" },
            React.createElement(KV, { k: "Active sessions", v: sessions.active }),
            React.createElement(KV, { k: "Stale active >6h", v: sessions.stale_6h }),
            React.createElement(KV, { k: "Cron jobs", v: `${cron.enabled || 0}/${cron.jobs || 0} enabled` }),
            React.createElement(KV, { k: "Cron failures", v: cron.failures || 0 }),
            React.createElement(KV, { k: "BOOT.md", v: hooks.boot_md || "not installed" }),
            React.createElement(KV, { k: "Hooks", v: (hooks.hooks || []).join(", ") || "none" })
          )
        )
      ),

      React.createElement(Card, null,
        React.createElement(CardHeader, null,
          React.createElement("div", { className: "flex items-center gap-3" },
            React.createElement(CardTitle, { className: "text-base" }, "MCP Processes"),
            React.createElement(Pill, { ok: !!mcp.ok && (mcp.count || 0) <= 12 }, mcp.ok ? `${mcp.count || 0} running` : "check")
          )
        ),
        React.createElement(CardContent, null,
          (mcp.processes || []).length
            ? React.createElement("pre", { className: "max-h-80 overflow-auto whitespace-pre-wrap rounded border border-border bg-background/40 p-3 text-xs" },
                (mcp.processes || []).map(function (p) {
                  return `${p.pid} rss=${p.rss_kb}KB age=${p.etime} ${p.command}`;
                }).join("\n")
              )
            : React.createElement("div", { className: "text-sm text-muted-foreground" }, mcp.error || "No MCP-like child processes found.")
        )
      ),

      React.createElement(Card, null,
        React.createElement(CardHeader, null,
          React.createElement("div", { className: "flex items-center gap-3" },
            React.createElement(CardTitle, { className: "text-base" }, "Kubernetes"),
            React.createElement(Pill, { ok: !!k8s.ok }, k8s.ok ? "ok" : "check")
          )
        ),
        React.createElement(CardContent, null,
          React.createElement("pre", { className: "max-h-80 overflow-auto whitespace-pre-wrap rounded border border-border bg-background/40 p-3 text-xs" },
            k8s.stdout || k8s.stderr || k8s.error || "No Kubernetes data"
          )
        )
      ),

      React.createElement(Card, null,
        React.createElement(CardHeader, null,
          React.createElement("div", { className: "flex items-center gap-3" },
            React.createElement(CardTitle, { className: "text-base" }, "Ollama"),
            React.createElement(Pill, { ok: !!ollama.ok }, ollama.ok ? "ok" : "check")
          )
        ),
        React.createElement(CardContent, null,
          loadedModels.length
            ? React.createElement("div", { className: "grid gap-2" },
                loadedModels.map(function (m) {
                  return React.createElement("div", { key: m.name || m.model, className: "rounded border border-border p-3 text-sm" },
                    React.createElement("div", { className: "font-courier" }, m.name || m.model),
                    React.createElement("div", { className: "text-muted-foreground" }, `VRAM: ${m.size_vram || "?"} · expires: ${m.expires_at || "?"}`)
                  );
                })
              )
            : React.createElement("pre", { className: "whitespace-pre-wrap rounded border border-border bg-background/40 p-3 text-xs" },
                ollama.error || "No loaded Ollama models"
              )
        )
      )
    );
  }

  window.__HERMES_PLUGINS__.register("ops-runtime", OpsRuntimePage);
})();
