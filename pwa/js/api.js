const JSON_HEADERS = { "Content-Type": "application/json" };

export async function pwaLogin(base, obraId, apiKey) {
  const response = await fetch(`${base}/auth/pwa/login`, {
    method: "POST",
    headers: JSON_HEADERS,
    credentials: "include",
    body: JSON.stringify({ obra_id: obraId, api_key: apiKey }),
  });
  const raw = await response.text();
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    throw new Error(raw.slice(0, 200) || "Resposta inválida do servidor");
  }
  if (!response.ok) {
    const det = data.detail;
    const msg = typeof det === "string" ? det : JSON.stringify(det || data);
    throw new Error(msg);
  }
  return data;
}

export async function pwaLogout(base) {
  await fetch(`${base}/auth/pwa/logout`, {
    method: "POST",
    credentials: "include",
  });
}

/** @returns {Promise<{ ok: boolean, obra_id: string } | null>} */
export async function fetchPwaSession(base) {
  const response = await fetch(`${base}/auth/pwa/session`, { credentials: "include" });
  if (response.status === 401) return null;
  if (!response.ok) return null;
  return response.json();
}

/**
 * @param {{ apiKey?: string }} [opts] — se informado, envia X-API-KEY (dev/integração); senão usa cookie de sessão.
 */
export async function conferirNfe(base, obraId, chaveAcesso, opts = {}) {
  const headers = { ...JSON_HEADERS };
  if (opts.apiKey) {
    headers["X-API-KEY"] = String(opts.apiKey).trim();
  }
  const response = await fetch(`${base}/conferir`, {
    method: "POST",
    headers,
    credentials: "include",
    body: JSON.stringify({
      obra_id: obraId,
      chave_acesso: chaveAcesso,
    }),
  });
  const raw = await response.text();
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    throw new Error(raw.slice(0, 200) || "Resposta inválida do servidor");
  }
  if (!response.ok) {
    const det = data.detail;
    const msg = typeof det === "string" ? det : JSON.stringify(det || data);
    throw new Error(msg);
  }
  return data;
}

/**
 * @param {{ apiKey?: string }} [opts]
 */
export async function fetchLaudoBlob(url, opts = {}) {
  const headers = {};
  if (opts.apiKey) {
    headers["X-API-KEY"] = String(opts.apiKey).trim();
  }
  const response = await fetch(url, {
    credentials: "include",
    headers: Object.keys(headers).length ? headers : undefined,
  });
  if (!response.ok) {
    const t = await response.text();
    throw new Error(t.slice(0, 120) || `HTTP ${response.status}`);
  }
  return response.blob();
}
