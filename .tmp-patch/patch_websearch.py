p = "/Users/bytedance/github/opencodex/src/web-search/index.ts"
src = open(p).read()
old = "): SidecarPlan | undefined {\n  if (!parsed._webSearch || isPassthrough) return undefined;\n  const cfg = config.webSearchSidecar ?? {};\n  if (cfg.enabled === false) return undefined;\n"
new = """): SidecarPlan | undefined {
  if (!parsed._webSearch || isPassthrough) return undefined;
  // Provider-native Live Search (Grok `search_parameters` wire) takes over  bypass the sidecar so
  // the upstream backend performs the search itself, and citations flow via the adapter stream
  // parser instead of the sidecar loop. Whitelist is per-model (see OcxProviderConfig.liveSearchModels).
  if (modelInList(provider.liveSearchModels, modelId)) return undefined;
  const cfg = config.webSearchSidecar ?? {};
  if (cfg.enabled === false) return undefined;
"""
if old not in src:
    raise SystemExit("planWebSearch anchor not found")
src2 = src.replace(old, new, 1)
open(p, "w").write(src2)
print("OK")
