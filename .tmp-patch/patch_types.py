p = "/Users/bytedance/github/opencodex/src/types.ts"
src = open(p).read()

marker = "/**\n * Claude Code inbound settings (devlog/260711_claude_inbound). Consumed by the"
inject = '''/**
 * xAI Grok-compatible "Live Search" configuration. Wire format is xAI top-level
 * `search_parameters` body field on `/v1/chat/completions` (a.k.a. the legacy Live Search API).
 * Field names in TypeScript are camelCase and are converted to snake_case on the wire by the
 * openai-chat adapter.
 *
 * Reference: https://docs.x.ai/docs/guides/live-search  sources[].type is one of `web` | `news` | `x` | `rss`.
 *
 * NOTE: xAI officially deprecated this on api.x.ai (410 Gone after 2026-01-12) in favor of the
 * Agent Tools API on `/v1/responses`. Third-party Grok proxies typically still accept
 * `search_parameters` on chat/completions  that is the intended target for this config.
 */
export interface OcxLiveSearchConfig {
  /** "auto" (default) lets the model decide; "on" forces search; "off" disables it. */
  mode?: "auto" | "on" | "off";
  /** When true, ask the backend to return a top-level `citations: string[]` array on the final chunk. */
  returnCitations?: boolean;
  /** Data sources the backend may consult. Defaults to backend own default (typically web+x+news). */
  sources?: OcxLiveSearchSource[];
  /** ISO-8601 date (YYYY-MM-DD). Only include content on/after this date. */
  fromDate?: string;
  /** ISO-8601 date (YYYY-MM-DD). Only include content on/before this date. */
  toDate?: string;
  /** Cap on how many search results the backend may consult. */
  maxSearchResults?: number;
}

/** One entry of `OcxLiveSearchConfig.sources`. Matches xAI official source type enumeration. */
export type OcxLiveSearchSource =
  | { type: "web"; country?: string; excludedWebsites?: string[]; allowedWebsites?: string[]; safeSearch?: boolean }
  | { type: "news"; country?: string; excludedWebsites?: string[]; safeSearch?: boolean }
  | { type: "x"; allowedXHandles?: string[]; excludedXHandles?: string[] }
  | { type: "rss"; links: string[] };

'''
if marker not in src:
    raise SystemExit("marker not found")
src2 = src.replace(marker, inject + marker, 1)

old = "  forwardHeaders?: string[];\n  /** Default provider-routing preferences for models sent through the canonical OpenRouter API. */"
new = '''  forwardHeaders?: string[];
  /**
   * Model IDs on this provider that support Grok-compatible "Live Search" (top-level
   * `search_parameters` body field on chat/completions). Matches openai-chat only. When a
   * request model is in this list AND Codex enabled `web_search` (or `liveSearchAlwaysOn`
   * is true), the adapter injects `search_parameters` and the web-search sidecar is bypassed
   * so the upstream Grok backend runs the search itself.
   *
   * Reference: https://docs.x.ai/docs/guides/live-search (xAI Live Search wire spec).
   */
  liveSearchModels?: string[];
  /** Provider-wide default Live Search payload. Applied to every whitelisted model unless overridden. */
  liveSearch?: OcxLiveSearchConfig;
  /**
   * Per-model overrides shallow-merged onto `liveSearch`. Key = exact model id (Ollama family
   * "before-colon" match is also supported via modelInList). Overrides win field-by-field.
   */
  modelLiveSearch?: Record<string, OcxLiveSearchConfig>;
  /**
   * When true, inject `search_parameters` on every whitelisted-model request, even if Codex
   * did not enable web_search. Default false  the adapter only injects when Codex asked for
   * web_search, so users don not unknowingly pay for search on every turn.
   */
  liveSearchAlwaysOn?: boolean;
  /**
   * Which xAI live-search wire format the upstream understands. Only "search_parameters" is
   * implemented today (chat/completions top-level field, matches Cherry Studio and most Grok
   * proxies). "responses_tools" is reserved for a future xAI-Responses adapter and is currently
   * a no-op on openai-chat. Defaults to "search_parameters".
   */
  liveSearchWireVersion?: "search_parameters" | "responses_tools";
  /** Default provider-routing preferences for models sent through the canonical OpenRouter API. */'''
if old not in src2:
    raise SystemExit("forwardHeaders anchor not found")
src3 = src2.replace(old, new, 1)

open(p, "w").write(src3)
print("OK", len(src3) - len(src))
