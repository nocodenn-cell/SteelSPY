import { getApiBaseUrl } from "./config.js";
import { pwaLogin, pwaLogout, conferirNfe, fetchLaudoBlob } from "./api.js";
import { renderizarResultado, onlyDigits, mostrarToast } from "./render.js";

let lastLaudoUrl = null;
let lastDivergenciasUrl = null;
let loggedIn = false;

/** RFC 4122 (hex com hífens) */
function isValidUUID(uuid) {
  const uuidRegex =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(String(uuid || "").trim());
}

function $(id) {
  return document.getElementById(id);
}

function showEl(id, show) {
  const el = $(id);
  if (!el) return;
  el.classList.toggle("hidden", !show);
}

function showFormError(msg) {
  const el = $("formError");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("hidden");
}

function clearFormError() {
  const el = $("formError");
  if (!el) return;
  el.textContent = "";
  el.classList.add("hidden");
}

function showLoginError(msg) {
  const el = $("loginError");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("hidden");
}

function clearLoginError() {
  const el = $("loginError");
  if (!el) return;
  el.textContent = "";
  el.classList.add("hidden");
}

function announce(msg) {
  const el = $("liveRegion");
  if (el) el.textContent = msg;
}

function apiBase() {
  return getApiBaseUrl().replace(/\/$/, "");
}

function useHeaderKeyMode() {
  const c = $("useHeaderKey");
  return !!(c && c.checked);
}

function currentApiKey() {
  const v = ($("apiKey") && $("apiKey").value) || "";
  return String(v).trim();
}

function syncLoginUi() {
  const base = apiBase();
  const hasBase = !!base;
  showEl("configWarning", !hasBase);
  showEl("loginBlock", hasBase);
  const badge = $("sessionBadge");
  if (badge) {
    badge.textContent = loggedIn ? "Sessão ativa (cookie)" : "Sem sessão";
    badge.classList.toggle("bg-emerald-700", loggedIn);
    badge.classList.toggle("bg-slate-600", !loggedIn);
  }
  const loginBtn = $("btnLogin");
  if (loginBtn) loginBtn.disabled = !hasBase;
  const hk = useHeaderKeyMode();
  showEl("cookieActions", !hk);
  if ($("apiKey")) $("apiKey").autocomplete = hk ? "off" : "current-password";
}

export async function handleLogin() {
  clearLoginError();
  const base = apiBase();
  if (!base) {
    showLoginError("Defina apiBaseUrl no bloco de configuração (#stellspy-config).");
    return;
  }
  const obraId = (($("obraId") && $("obraId").value) || "").trim();
  const key = currentApiKey();
  if (!isValidUUID(obraId)) {
    showLoginError(
      "ID da obra inválido. Use o formato: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    );
    return;
  }
  if (!key) {
    showLoginError("Informe a API Key da obra.");
    return;
  }
  const btn = $("btnLogin");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Entrando…";
  }
  try {
    await pwaLogin(base, obraId, key);
    loggedIn = true;
    if ($("apiKey")) $("apiKey").value = "";
    announce("Sessão iniciada.");
  } catch (e) {
    loggedIn = false;
    showLoginError(e.message || "Falha no login.");
    announce("Erro no login.");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Entrar na obra";
    }
    syncLoginUi();
  }
}

export async function handleLogout() {
  const base = apiBase();
  if (base) {
    try {
      await pwaLogout(base);
    } catch {
      /* ignore */
    }
  }
  loggedIn = false;
  announce("Sessão encerrada.");
  syncLoginUi();
}

export async function handleConferir() {
  clearFormError();
  const base = apiBase();
  if (!base) {
    showFormError("Configure apiBaseUrl em #stellspy-config.");
    return;
  }
  const obraId = (($("obraId") && $("obraId").value) || "").trim();
  const chave = onlyDigits(($("nfeKey") && $("nfeKey").value) || "");
  if (!isValidUUID(obraId)) {
    showFormError(
      "ID da obra inválido. Use o formato: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    );
    return;
  }
  if (chave.length !== 44) {
    showFormError("A chave deve ter exatamente 44 dígitos.");
    return;
  }
  const hk = useHeaderKeyMode();
  const key = currentApiKey();
  if (hk && !key) {
    showFormError("Informe a API Key ou desmarque o modo header.");
    return;
  }
  if (!hk && !loggedIn) {
    showFormError("Entre na obra (login) ou marque o envio por X-API-KEY.");
    return;
  }

  const btn = $("btnCheck");
  const resultArea = $("resultArea");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML =
      '<span class="spinner" aria-hidden="true"></span><span>PROCESSANDO…</span>';
  }
  if (resultArea) resultArea.classList.add("hidden");

  try {
    const data = await conferirNfe(base, obraId, chave, hk ? { apiKey: key } : {});
    const out = renderizarResultado(data, base);
    lastLaudoUrl = out.lastLaudoUrl;
    lastDivergenciasUrl = out.lastDivergenciasUrl;
    announce(`Resultado: ${data.status}`);
  } catch (err) {
    showFormError(err.message || "Erro ao conectar. Verifique rede e URL da API.");
    announce("Erro na conferência.");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = "CONFERIR MATERIAL";
    }
  }
}

async function handleAbrirDivergenciasPdf() {
  const base = apiBase();
  if (!base || !lastDivergenciasUrl) {
    mostrarToast("Nenhum PDF de divergências disponível.", "info");
    return;
  }
  const hk = useHeaderKeyMode();
  const key = currentApiKey();
  if (hk && !key) {
    mostrarToast("Informe a API Key para baixar o PDF.", "erro");
    return;
  }
  const btn = document.getElementById("btnPdfDiv");
  if (btn) {
    btn.disabled = true;
  }
  try {
    const headers = {};
    if (hk && key) headers["X-API-KEY"] = key;
    const response = await fetch(lastDivergenciasUrl, {
      credentials: "include",
      headers: Object.keys(headers).length ? headers : undefined,
    });
    if (!response.ok) {
      const t = await response.text();
      throw new Error(t.slice(0, 120) || `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (e) {
    mostrarToast(
      "Falha ao baixar PDF. " + (e.message || String(e)),
      "erro",
    );
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function handleAbrirLaudo() {
  if (!lastLaudoUrl) return;
  const base = apiBase();
  const btn = $("btnPdf");
  const hk = useHeaderKeyMode();
  const key = currentApiKey();
  if (btn) btn.disabled = true;
  try {
    const blob = await fetchLaudoBlob(lastLaudoUrl, hk ? { apiKey: key } : {});
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (e) {
    mostrarToast(
      "Não foi possível abrir o laudo. " + (e.message || String(e)),
      "erro",
    );
  } finally {
    if (btn) btn.disabled = false;
  }
}

function wireNfeInput() {
  const nfeInput = $("nfeKey");
  if (!nfeInput) return;
  nfeInput.addEventListener("input", () => {
    const only = nfeInput.value.replace(/\D/g, "").slice(0, 44);
    nfeInput.value = only.replace(/(.{4})/g, "$1 ").trim();
    const dc = $("digitCount");
    if (dc) dc.textContent = String(only.length);
  });
}

function wireHeaderKeyToggle() {
  const c = $("useHeaderKey");
  if (!c) return;
  c.addEventListener("change", () => {
    if (c.checked) {
      loggedIn = false;
    }
    syncLoginUi();
  });
}

window.stellspyLogin = handleLogin;
window.stellspyLogout = handleLogout;
window.stellspyConferir = handleConferir;
window.stellspyLaudo = handleAbrirLaudo;
window.stellspyDivergenciasPdf = handleAbrirDivergenciasPdf;

wireNfeInput();
wireHeaderKeyToggle();

const preObra = (() => {
  const el = document.getElementById("stellspy-config");
  if (!el?.textContent?.trim()) return "";
  try {
    const j = JSON.parse(el.textContent);
    return String(j.obraId || j.obra_id || "").trim();
  } catch {
    return "";
  }
})();

if (preObra && $("obraId")) {
  $("obraId").value = preObra;
}

syncLoginUi();

/** Cookie de sessão: alinha UI com o servidor; em 401 limpa estado e avisa uma vez. */
async function verificarSessao() {
  const base = apiBase();
  const hk = useHeaderKeyMode();
  if (!base || hk) return true;

  try {
    const response = await fetch(`${base}/auth/pwa/session`, {
      credentials: "include",
    });

    if (response.status === 401) {
      if (loggedIn) {
        mostrarToast("Sessão expirada. Faça login novamente.", "info");
        announce("Sessão expirada.");
      }
      loggedIn = false;
      syncLoginUi();
      return false;
    }

    if (!response.ok) {
      return loggedIn;
    }

    const data = await response.json();
    loggedIn = !!data.ok;
    syncLoginUi();
    return loggedIn;
  } catch {
    return loggedIn;
  }
}

void verificarSessao();

setInterval(() => {
  void verificarSessao();
}, 5 * 60 * 1000);

if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  navigator.serviceWorker.register("./sw.js").catch(() => {});
}
