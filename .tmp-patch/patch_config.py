p = "/Users/bytedance/github/opencodex/src/config.ts"
src = open(p).read()

# 1) Insert validators for live-search fields RIGHT BEFORE `const configSchema = z.object({`
anchor = "\nconst configSchema = z.object({\n"
new_validators = '''
const LIVE_SEARCH_MODES = new Set(["auto", "on", "off"]);
const LIVE_SEARCH_SOURCE_TYPES = new Set(["web", "news", "x", "rss"]);
const ISO_DATE = /^\\d{4}-\\d{2}-\\d{2}$/;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

function stringArrayIssue(value: unknown, field: string): string | null {
  if (value === undefined) return null;
  if (!Array.isArray(value)) return `${field} must be a string array`;
  for (const s of value) {
    if (typeof s !== "string" || !s.trim()) return `${field} entries must be nonblank strings`;
  }
  return null;
}

export function liveSearchConfigError(value: unknown, field: string): string | null {
  if (value === undefined) return null;
  if (!isPlainObject(value)) return `${field} must be a plain object`;
  const v = value as Record<string, unknown>;
  if (v.mode !== undefined && (typeof v.mode !== "string" || !LIVE_SEARCH_MODES.has(v.mode as string))) {
    return `${field}.mode must be one of auto|on|off`;
  }
  if (v.returnCitations !== undefined && typeof v.returnCitations !== "boolean") {
    return `${field}.returnCitations must be a boolean`;
  }
  if (v.fromDate !== undefined && (typeof v.fromDate !== "string" || !ISO_DATE.test(v.fromDate))) {
    return `${field}.fromDate must be an ISO date YYYY-MM-DD`;
  }
  if (v.toDate !== undefined && (typeof v.toDate !== "string" || !ISO_DATE.test(v.toDate))) {
    return `${field}.toDate must be an ISO date YYYY-MM-DD`;
  }
  if (v.maxSearchResults !== undefined) {
    const n = v.maxSearchResults;
    if (typeof n !== "number" || !Number.isFinite(n) || !Number.isInteger(n) || n <= 0) {
      return `${field}.maxSearchResults must be a positive integer`;
    }
  }
  if (v.sources !== undefined) {
    if (!Array.isArray(v.sources)) return `${field}.sources must be an array`;
    for (let i = 0; i < v.sources.length; i++) {
      const src = v.sources[i];
      if (!isPlainObject(src)) return `${field}.sources[${i}] must be a plain object`;
      const s = src as Record<string, unknown>;
      if (typeof s.type !== "string" || !LIVE_SEARCH_SOURCE_TYPES.has(s.type as string)) {
        return `${field}.sources[${i}].type must be one of web|news|x|rss`;
      }
      if (s.type === "rss") {
        const linksErr = stringArrayIssue(s.links, `${field}.sources[${i}].links`);
        if (linksErr) return linksErr;
        if (!Array.isArray(s.links) || s.links.length === 0) {
          return `${field}.sources[${i}].links must be a non-empty string array (rss requires links)`;
        }
      }
      if (s.type === "web" || s.type === "news") {
        if (s.country !== undefined && (typeof s.country !== "string" || !s.country.trim())) {
          return `${field}.sources[${i}].country must be a nonblank string`;
        }
        const exErr = stringArrayIssue(s.excludedWebsites, `${field}.sources[${i}].excludedWebsites`);
        if (exErr) return exErr;
        if (s.type === "web") {
          const alErr = stringArrayIssue((s as Record<string, unknown>).allowedWebsites, `${field}.sources[${i}].allowedWebsites`);
          if (alErr) return alErr;
        }
        if (s.safeSearch !== undefined && typeof s.safeSearch !== "boolean") {
          return `${field}.sources[${i}].safeSearch must be a boolean`;
        }
      }
      if (s.type === "x") {
        const allowErr = stringArrayIssue(s.allowedXHandles, `${field}.sources[${i}].allowedXHandles`);
        if (allowErr) return allowErr;
        const exErr = stringArrayIssue(s.excludedXHandles, `${field}.sources[${i}].excludedXHandles`);
        if (exErr) return exErr;
      }
    }
  }
  return null;
}

export function liveSearchModelsConfigError(value: unknown): string | null {
  return stringArrayIssue(value, "liveSearchModels");
}

export function modelLiveSearchConfigError(value: unknown): string | null {
  if (value === undefined) return null;
  if (!isPlainObject(value)) return "modelLiveSearch must be a plain object";
  for (const [key, entry] of Object.entries(value)) {
    if (!key.trim()) return "modelLiveSearch keys must be nonblank model ids";
    const err = liveSearchConfigError(entry, `modelLiveSearch.${key}`);
    if (err) return err;
  }
  return null;
}
'''
if anchor not in src:
    raise SystemExit("configSchema anchor not found")
src2 = src.replace(anchor, new_validators + anchor, 1)

# 2) Add superRefine hooks inside the provider loop. Insert AFTER the maxOutputError block, BEFORE codexAccountMode check.
old_block = '''    const maxOutputError = positiveIntegerRecordConfigError(
      (provider as { modelMaxOutputTokens?: unknown }).modelMaxOutputTokens,
      "modelMaxOutputTokens",
    );
    if (maxOutputError) {
      ctx.addIssue({
        code: "custom",
        path: ["providers", name, "modelMaxOutputTokens"],
        message: maxOutputError,
      });
    }
    if (Object.hasOwn(provider, "codexAccountMode") && provider.codexAccountMode !== undefined) {'''
new_block = '''    const maxOutputError = positiveIntegerRecordConfigError(
      (provider as { modelMaxOutputTokens?: unknown }).modelMaxOutputTokens,
      "modelMaxOutputTokens",
    );
    if (maxOutputError) {
      ctx.addIssue({
        code: "custom",
        path: ["providers", name, "modelMaxOutputTokens"],
        message: maxOutputError,
      });
    }
    // Live Search validation (Grok-compatible `search_parameters` wire).
    const liveSearchModelsErr = liveSearchModelsConfigError((provider as { liveSearchModels?: unknown }).liveSearchModels);
    if (liveSearchModelsErr) {
      ctx.addIssue({
        code: "custom",
        path: ["providers", name, "liveSearchModels"],
        message: liveSearchModelsErr,
      });
    }
    const liveSearchErr = liveSearchConfigError((provider as { liveSearch?: unknown }).liveSearch, "liveSearch");
    if (liveSearchErr) {
      ctx.addIssue({
        code: "custom",
        path: ["providers", name, "liveSearch"],
        message: liveSearchErr,
      });
    }
    const modelLiveSearchErr = modelLiveSearchConfigError((provider as { modelLiveSearch?: unknown }).modelLiveSearch);
    if (modelLiveSearchErr) {
      ctx.addIssue({
        code: "custom",
        path: ["providers", name, "modelLiveSearch"],
        message: modelLiveSearchErr,
      });
    }
    if ((provider as { liveSearchAlwaysOn?: unknown }).liveSearchAlwaysOn !== undefined
      && typeof (provider as { liveSearchAlwaysOn?: unknown }).liveSearchAlwaysOn !== "boolean") {
      ctx.addIssue({
        code: "custom",
        path: ["providers", name, "liveSearchAlwaysOn"],
        message: "liveSearchAlwaysOn must be a boolean",
      });
    }
    const liveSearchWire = (provider as { liveSearchWireVersion?: unknown }).liveSearchWireVersion;
    if (liveSearchWire !== undefined && liveSearchWire !== "search_parameters" && liveSearchWire !== "responses_tools") {
      ctx.addIssue({
        code: "custom",
        path: ["providers", name, "liveSearchWireVersion"],
        message: "liveSearchWireVersion must be one of search_parameters|responses_tools",
      });
    }
    if (Object.hasOwn(provider, "codexAccountMode") && provider.codexAccountMode !== undefined) {'''
if old_block not in src2:
    raise SystemExit("provider loop anchor not found")
src3 = src2.replace(old_block, new_block, 1)

open(p, "w").write(src3)
print("OK", len(src3) - len(src))
