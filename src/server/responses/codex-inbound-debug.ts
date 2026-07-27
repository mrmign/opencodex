/**
 * Codex inbound /v1/responses request dump. Opt-in, controlled by the `codex` debug flag
 * (env `OCX_CODEX_DEBUG=1`, or `setDebugSettings({ codex: true })` at runtime).
 *
 * Prints method, URL, sanitized request headers (Authorization/Cookie/x-oai-attestation
 * redacted), and the parsed JSON body to stderr for eyeball debugging. Body is truncated
 * past DEFAULT_MAX so a giant compaction turn does not blow up the terminal.
 *
 * Not suitable for production log sinks — this is a developer-only console dump.
 */
import { isCodexDebugEnabled } from "../../lib/debug-settings";

const DEFAULT_MAX = 64 * 1024; // 64 KiB per body dump

const REDACT = new Set([
  "authorization",
  "cookie",
  "set-cookie",
  "proxy-authorization",
  "x-oai-attestation",
]);

function sanitizeHeaders(headers: Headers): Record<string, string> {
  const out: Record<string, string> = {};
  headers.forEach((value, key) => {
    out[key] = REDACT.has(key.toLowerCase()) ? "[redacted]" : value;
  });
  return out;
}

function stringifyBody(body: unknown, max: number): string {
  let text: string;
  try {
    text = JSON.stringify(body, null, 2) ?? String(body);
  } catch {
    text = String(body);
  }
  if (text.length > max) {
    return text.slice(0, max) + `\n... [truncated ${text.length - max} bytes]`;
  }
  return text;
}

export function dumpCodexInboundRequest(req: Request, body: unknown, opts?: { max?: number }): void {
  if (!isCodexDebugEnabled()) return;
  const max = opts?.max ?? DEFAULT_MAX;
  const url = new URL(req.url);
  const line = `[opencodex] codex-inbound ${req.method} ${url.pathname}${url.search}`;
  const headers = sanitizeHeaders(req.headers);
  const bodyText = stringifyBody(body, max);
  console.warn(line);
  console.warn(`[opencodex] codex-inbound headers ${JSON.stringify(headers)}`);
  console.warn(`[opencodex] codex-inbound body\n${bodyText}`);
}
