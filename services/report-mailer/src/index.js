const REPORT_PATHS = {
  daily: "reports/daily-latest.pdf",
  weekly: "reports/weekly-latest.pdf",
  feasibility: "reports/feasibility-latest.pdf",
};

function corsHeaders(origin, allowedOrigin) {
  const allowed = origin && origin === allowedOrigin ? origin : allowedOrigin;
  return {
    "Access-Control-Allow-Origin": allowed,
    "Access-Control-Allow-Methods": "POST,OPTIONS,GET",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function json(body, status, headers) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...headers },
  });
}

function validEmail(value) {
  return typeof value === "string" && value.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}


function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

function feasibilityBlock(summary) {
  if (!summary || typeof summary !== "object") return "";
  const park = escapeHtml(String(summary.park_name || "园区").slice(0, 120));
  const conclusion = escapeHtml(String(summary.conclusion || "").slice(0, 600));
  const boundary = escapeHtml(String(summary.decision_boundary || "").slice(0, 600));
  const projects = Array.isArray(summary.selected_projects)
    ? summary.selected_projects.slice(0, 12).map((name) => `<li>${escapeHtml(String(name).slice(0, 160))}</li>`).join("")
    : "";
  const capex = Number(summary.capex_10k_cny);
  const abatement = Number(summary.annual_abatement_tco2);
  return `<div style="margin:16px 0;padding:14px 16px;border:1px solid #d9e0da;border-radius:8px">
    <h3 style="margin:0 0 8px">${park}：本次可行性测算摘要</h3>
    ${conclusion ? `<p><strong>结论：</strong>${conclusion}</p>` : ""}
    ${boundary ? `<p><strong>适用边界：</strong>${boundary}</p>` : ""}
    ${Number.isFinite(capex) ? `<p><strong>入选投资：</strong>${capex.toLocaleString("zh-CN")} 万元</p>` : ""}
    ${Number.isFinite(abatement) ? `<p><strong>年度减排：</strong>${abatement.toLocaleString("zh-CN")} tCO₂</p>` : ""}
    ${projects ? `<p><strong>入选项目：</strong></p><ul>${projects}</ul>` : ""}
  </div>`;
}

function bufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, Math.min(i + chunk, bytes.length)));
  }
  return btoa(binary);
}

async function verifyTurnstile(token, ip, secret) {
  if (!secret) return true;
  if (!token) return false;
  const form = new FormData();
  form.append("secret", secret);
  form.append("response", token);
  if (ip) form.append("remoteip", ip);
  const response = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form });
  const payload = await response.json();
  return Boolean(payload.success);
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const allowedOrigin = env.ALLOWED_ORIGIN || "https://cj-oi.github.io";
    const cors = corsHeaders(origin, allowedOrigin);

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method === "GET") return json({ ok: true, service: "park-report-mailer" }, 200, cors);
    if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405, cors);
    if (origin && origin !== allowedOrigin) return json({ error: "origin_not_allowed" }, 403, cors);

    let payload;
    try { payload = await request.json(); }
    catch (_) { return json({ error: "invalid_json" }, 400, cors); }

    const email = String(payload.email || "").trim().toLowerCase();
    const reportType = String(payload.report_type || "weekly");
    if (!payload.consent) return json({ error: "consent_required" }, 400, cors);
    if (!validEmail(email)) return json({ error: "invalid_email" }, 400, cors);
    if (!(reportType in REPORT_PATHS)) return json({ error: "invalid_report_type" }, 400, cors);

    const ip = request.headers.get("CF-Connecting-IP") || "";
    const turnstileOk = await verifyTurnstile(payload.turnstile_token, ip, env.TURNSTILE_SECRET_KEY || "");
    if (!turnstileOk) return json({ error: "verification_failed" }, 403, cors);

    const siteUrl = (env.SITE_URL || "https://cj-oi.github.io/zero-carbon-park/").replace(/\/?$/, "/");
    const reportUrl = new URL(REPORT_PATHS[reportType], siteUrl).href;
    const reportResponse = await fetch(reportUrl, { cf: { cacheTtl: 300, cacheEverything: true } });
    if (!reportResponse.ok) return json({ error: "report_not_available" }, 502, cors);
    const contentLength = Number(reportResponse.headers.get("content-length") || 0);
    if (contentLength > 12 * 1024 * 1024) return json({ error: "report_too_large" }, 413, cors);
    const reportBuffer = await reportResponse.arrayBuffer();
    if (reportBuffer.byteLength > 12 * 1024 * 1024) return json({ error: "report_too_large" }, 413, cors);

    if (!env.RESEND_API_KEY || !env.REPORT_FROM) return json({ error: "mailer_not_configured" }, 503, cors);
    const labels = { daily: "零碳园区公开信息日报", weekly: "零碳园区公开信息周报", feasibility: "零碳园区可行性初筛报告" };
    const currentSummary = reportType === "feasibility" ? feasibilityBlock(payload.feasibility_summary) : "";
    const sendResponse = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { "Authorization": `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        from: env.REPORT_FROM,
        to: [email],
        subject: labels[reportType],
        html: `<p>您好：</p><p>附件为${labels[reportType]}。</p>${currentSummary}<p>在线版本：<a href="${reportUrl}">${reportUrl}</a></p><p>报告用于公开信息整理、数据补齐和前期筛查；正式决策前请核验园区边界、原始台账和项目参数。</p>`,
        attachments: [{ filename: `${reportType}-latest.pdf`, content: bufferToBase64(reportBuffer) }],
      }),
    });
    const sendPayload = await sendResponse.json().catch(() => ({}));
    if (!sendResponse.ok) return json({ error: "send_failed", detail: sendPayload.message || sendPayload.name || "unknown" }, 502, cors);
    return json({ ok: true, id: sendPayload.id || null }, 200, cors);
  },
};
