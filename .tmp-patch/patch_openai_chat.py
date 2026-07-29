import re, sys, pathlib

p = pathlib.Path("/Users/bytedance/github/opencodex/src/adapters/openai-chat.ts")
src = p.read_text()

old_import = 'import type { AdapterEvent, OcxAssistantMessage, OcxContentPart, OcxMessage, OcxParsedRequest, OcxProviderConfig, OcxTextContent, OcxThinkingContent, OcxToolCall, OcxUsage } from "../types";'
new_import = 'import type { AdapterEvent, OcxAssistantMessage, OcxContentPart, OcxLiveSearchConfig, OcxLiveSearchSource, OcxMessage, OcxParsedRequest, OcxProviderConfig, OcxTextContent, OcxThinkingContent, OcxToolCall, OcxUrlCitation, OcxUsage } from "../types";'
assert old_import in src, "types import not found verbatim"
src = src.replace(old_import, new_import, 1)

helper = '''// Grok Live Search wire mapping (chat/completions `search_parameters`, legacy xAI wire).
// Camel->snake at the outer level and inside each `sources[]` entry; unknown keys pass through
// unchanged so future xAI additions do not require an opencodex bump. Called from buildRequest
// when the caller's model is on `provider.liveSearchModels` and either Codex enabled web_search
// or the provider set `liveSearchAlwaysOn: true`. See devlog/260725_grok_live_search.
//
// SECURITY: this only emits fields the caller placed in `provider.liveSearch` / `modelLiveSearch`;
// there is no request-side path from Codex to smuggle extra keys here.
function liveSearchToWire(cfg: OcxLiveSearchConfig): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (cfg.mode !== undefined) out.mode = cfg.mode;
  if (cfg.returnCitations !== undefined) out.return_citations = cfg.returnCitations;
  if (cfg.fromDate !== undefined) out.from_date = cfg.fromDate;
  if (cfg.toDate !== undefined) out.to_date = cfg.toDate;
  if (cfg.maxSearchResults !== undefined) out.max_search_results = cfg.maxSearchResults;
  if (cfg.sources !== undefined) out.sources = cfg.sources.map(liveSearchSourceToWire);
  return out;
}

function liveSearchSourceToWire(s: OcxLiveSearchSource): Record<string, unknown> {
  const out: Record<string, unknown> = { type: s.type };
  if (s.type === "web") {
    if (s.country !== undefined) out.country = s.country;
    if (s.excludedWebsites !== undefined) out.excluded_websites = s.excludedWebsites;
    if (s.allowedWebsites !== undefined) out.allowed_websites = s.allowedWebsites;
    if (s.safeSearch !== undefined) out.safe_search = s.safeSearch;
  } else if (s.type === "news") {
    if (s.country !== undefined) out.country = s.country;
    if (s.excludedWebsites !== undefined) out.excluded_websites = s.excludedWebsites;
    if (s.safeSearch !== undefined) out.safe_search = s.safeSearch;
  } else if (s.type === "x") {
    if (s.allowedXHandles !== undefined) out.allowed_x_handles = s.allowedXHandles;
    if (s.excludedXHandles !== undefined) out.excluded_x_handles = s.excludedXHandles;
  } else if (s.type === "rss") {
    out.links = s.links;
  }
  return out;
}

'''
marker = "export function createOpenAIChatAdapter(provider: OcxProviderConfig): ProviderAdapter {"
assert marker in src
src = src.replace(marker, helper + marker, 1)

old_stream_opt = '''      if (parsed.stream) {
        body.stream_options = { include_usage: true };
      }

      const url = `${provider.baseUrl}/chat/completions`;'''
new_stream_opt = '''      if (parsed.stream) {
        body.stream_options = { include_usage: true };
      }

      // Grok Live Search (`search_parameters`) - provider-config-driven, opt-in per model.
      // Gate: (a) model is on `provider.liveSearchModels`, (b) either Codex enabled `web_search`
      // (parsed._webSearch present) OR `provider.liveSearchAlwaysOn === true`, (c) wire version
      // resolves to `search_parameters` (the legacy xAI wire that third-party Grok proxies still
      // accept). The Agent-Tools wire (`responses_tools`) belongs on the /v1/responses adapter
      // and is intentionally a no-op here. Per-model overrides (`modelLiveSearch[modelId]`) merge
      // on top of provider-wide defaults (`provider.liveSearch`). Web-search sidecar is
      // short-circuited upstream (src/web-search/index.ts) so the backend runs the search itself.
      if (
        modelInList(provider.liveSearchModels, parsed.modelId)
        && (provider.liveSearchWireVersion ?? "search_parameters") === "search_parameters"
        && (provider.liveSearchAlwaysOn === true || parsed._webSearch !== undefined)
      ) {
        const merged: OcxLiveSearchConfig = {
          ...(provider.liveSearch ?? {}),
          ...(provider.modelLiveSearch?.[parsed.modelId] ?? {}),
        };
        // Default `return_citations: true` when the caller did not pin it - Codex renders the
        // "Sources" chip only when the adapter emits web_search_call_end.sources, and citations
        // are the sole channel Grok chat/completions exposes for that.
        if (merged.returnCitations === undefined) merged.returnCitations = true;
        body.search_parameters = liveSearchToWire(merged);
      }

      const url = `${provider.baseUrl}/chat/completions`;'''
assert old_stream_opt in src, "stream_options block not found"
src = src.replace(old_stream_opt, new_stream_opt, 1)

old_state = '''      let finishReason: string | undefined;

      // Single per-line handler shared by the streaming loop and the EOF residual-frame flush, so'''
new_state = '''      let finishReason: string | undefined;
      // Grok live-search citations arrive on the FINAL SSE chunk as a top-level `citations: string[]`
      // (Cherry Studio / xAI Live Search wire; see devlog/260725_grok_live_search). Buffered so a
      // single begin/end pair is emitted no matter which chunk carries the array, and de-duped so
      // a provider that repeats it on multiple chunks still yields exactly one Codex "Sources"
      // item. Emission happens on the terminal boundary (see the `emitCitationsIfAny` helper below).
      let liveSearchCitations: string[] | undefined;
      let liveSearchCitationsEmitted = false;
      let liveSearchCallSeq = 0;
      const emitCitationsIfAny = function* (): Generator<AdapterEvent> {
        if (liveSearchCitationsEmitted) return;
        if (!liveSearchCitations || liveSearchCitations.length === 0) return;
        liveSearchCitationsEmitted = true;
        const id = `ls_${++liveSearchCallSeq}`;
        const sources: OcxUrlCitation[] = liveSearchCitations.map((url) => ({ url }));
        yield { type: "web_search_call_begin", id };
        yield { type: "web_search_call_end", id, queries: [], status: "completed", sources };
      };

      // Single per-line handler shared by the streaming loop and the EOF residual-frame flush, so'''
assert old_state in src, "finishReason block not found"
src = src.replace(old_state, new_state, 1)

old_usage = '''        if (chunk.usage) {
          // Record usage but keep parsing: some providers send usage and the final content
          // delta in the SAME chunk; a bail here would drop that content. The choices
          // guard below no-ops a usage-only chunk.
          pendingUsage = usageFromOpenAIChat(chunk.usage as Record<string, unknown>);
        }'''
new_usage = '''        if (chunk.usage) {
          // Record usage but keep parsing: some providers send usage and the final content
          // delta in the SAME chunk; a bail here would drop that content. The choices
          // guard below no-ops a usage-only chunk.
          pendingUsage = usageFromOpenAIChat(chunk.usage as Record<string, unknown>);
        }

        // Grok Live Search: final chunk carries `citations: string[]` at the TOP level (not on
        // `choices[].delta`). Collect from wherever it appears; emission is deferred to the
        // terminal boundary so the "Sources" chip always follows the assistant message body.
        if (Array.isArray(chunk.citations)) {
          const cites = (chunk.citations as unknown[]).filter((c): c is string => typeof c === "string" && c.length > 0);
          if (cites.length > 0) liveSearchCitations = cites;
        }'''
assert old_usage in src, "usage block not found"
src = src.replace(old_usage, new_usage, 1)

old_done = '''        if (payload === "[DONE]") {
          yield* flushToolCalls();
          const stopReason = finishReason === "length"'''
new_done = '''        if (payload === "[DONE]") {
          yield* flushToolCalls();
          yield* emitCitationsIfAny();
          const stopReason = finishReason === "length"'''
assert old_done in src
src = src.replace(old_done, new_done, 1)

old_finish = '''        // Any non-empty finish_reason ends the generation: flush assembled tool calls as
        // atomic sequences (covers "tool_calls" AND providers that close tool turns with "stop").
        if (typeof choices[0].finish_reason === "string" && choices[0].finish_reason) {
          yield* flushToolCalls();
        }
        return "continue";'''
new_finish = '''        // Any non-empty finish_reason ends the generation: flush assembled tool calls as
        // atomic sequences (covers "tool_calls" AND providers that close tool turns with "stop").
        if (typeof choices[0].finish_reason === "string" && choices[0].finish_reason) {
          yield* flushToolCalls();
          yield* emitCitationsIfAny();
        }
        return "continue";'''
assert old_finish in src
src = src.replace(old_finish, new_finish, 1)

old_eof = '''        yield* flushToolCalls();
        // Reader EOF. A graceful close shows at least one terminal signal: `[DONE]` (returns above),'''
new_eof = '''        yield* flushToolCalls();
        yield* emitCitationsIfAny();
        // Reader EOF. A graceful close shows at least one terminal signal: `[DONE]` (returns above),'''
assert old_eof in src
src = src.replace(old_eof, new_eof, 1)

old_nonstream = '''      const usage = json.usage as Record<string, unknown> | undefined;
      events.push({
        type: "done",
        usage: usageFromOpenAIChat(usage),
      });
      return events;'''
new_nonstream = '''      // Grok Live Search citations on the non-streaming path also live at the top level.
      if (Array.isArray(json.citations)) {
        const cites = (json.citations as unknown[]).filter((c): c is string => typeof c === "string" && c.length > 0);
        if (cites.length > 0) {
          const id = `ls_1`;
          const sources: OcxUrlCitation[] = cites.map((url) => ({ url }));
          events.push({ type: "web_search_call_begin", id });
          events.push({ type: "web_search_call_end", id, queries: [], status: "completed", sources });
        }
      }
      const usage = json.usage as Record<string, unknown> | undefined;
      events.push({
        type: "done",
        usage: usageFromOpenAIChat(usage),
      });
      return events;'''
assert old_nonstream in src
src = src.replace(old_nonstream, new_nonstream, 1)

p.write_text(src)
print("patched openai-chat.ts, length:", len(src))
