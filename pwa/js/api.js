/**
 * Cliente HTTP do PWA operacional.
 *
 * Três regras que este módulo faz cumprir em toda chamada, e que são a razão de
 * ele existir separado da UI:
 *
 * 1. A credencial é sempre o cookie de sessão (`credentials: include`). Nada de
 *    token em localStorage: quem guarda sessão em JS perde a proteção HttpOnly.
 * 2. Toda escrita manda `X-CSRF-Token`. O servidor confere com o `jti` — o
 *    valor aqui é conveniência, nunca autoridade.
 * 3. Só se considera concluído o que o backend confirmou. `chamar()` lança em
 *    qualquer status fora de 2xx; a tela não tem caminho "assume que deu".
 *
 * O erro carregado em `ErroApi` é o texto do `detail` do servidor — já escrito
 * para ler em campo, sem SQL nem host.
 */

const JSON_HEADERS = { "Content-Type": "application/json" };

export class ErroApi extends Error {
  constructor(status, detail, payload) {
    super(detail || `HTTP ${status}`);
    this.name = "ErroApi";
    this.status = status;
    this.detail = detail || `HTTP ${status}`;
    this.payload = payload;
  }
}

function _detalhe(data, textoBruto, status) {
  const det = data && data.detail;
  if (typeof det === "string" && det.trim()) return det;
  if (det && typeof det === "object") {
    const primeiro = Array.isArray(det) ? det[0] : det;
    const msg = primeiro && (primeiro.msg || primeiro.detail);
    if (msg) return String(msg);
    return JSON.stringify(det).slice(0, 200);
  }
  return textoBruto.slice(0, 200) || `Resposta inválida (HTTP ${status})`;
}

async function _ler(resposta) {
  const texto = await resposta.text();
  if (!texto) return null;
  try {
    return JSON.parse(texto);
  } catch {
    return { _bruto: texto };
  }
}

/**
 * @param {string} base
 * @param {string} caminho  começa com "/"
 * @param {{method?: string, corpo?: any, csrf?: string|null, formulario?: FormData, consulta?: object, aceito?: string}} [opcoes]
 */
export async function chamar(base, caminho, opcoes = {}) {
  const metodo = (opcoes.method || "GET").toUpperCase();
  const url = new URL(base + caminho);
  for (const [chave, valor] of Object.entries(opcoes.consulta || {})) {
    if (valor !== null && valor !== undefined && valor !== "") {
      url.searchParams.set(chave, String(valor));
    }
  }

  const headers = {};
  if (opcoes.aceito) headers.Accept = opcoes.aceito;

  let corpo = undefined;
  if (opcoes.formulario) {
    corpo = opcoes.formulario; // multipart: o browser põe o Content-Type sozinho.
  } else if (opcoes.corpo !== undefined) {
    headers["Content-Type"] = "application/json";
    corpo = JSON.stringify(opcoes.corpo);
  }

  if (metodo !== "GET" && metodo !== "HEAD" && opcoes.csrf) {
    headers["X-CSRF-Token"] = opcoes.csrf;
  }

  const resposta = await fetch(url.toString(), {
    method: metodo,
    headers: Object.keys(headers).length ? headers : undefined,
    credentials: "include",
    body: corpo,
  });

  if (opcoes.aceito === "application/pdf") {
    if (!resposta.ok) {
      throw new ErroApi(resposta.status, _detalhe(await _ler(resposta), "", resposta.status));
    }
    return resposta.blob();
  }

  const dados = await _ler(resposta);
  if (!resposta.ok) {
    throw new ErroApi(resposta.status, _detalhe(dados, dados?._bruto || "", resposta.status), dados);
  }
  return dados;
}

// ---------------------------------------------------------------------------
// Identidade e escopo
// ---------------------------------------------------------------------------

export function login(base, email, senha, tenant) {
  return chamar(base, "/auth/login", {
    method: "POST",
    corpo: tenant ? { email, senha, tenant } : { email, senha },
  });
}

export function logout(base, csrf) {
  return chamar(base, "/auth/logout", { method: "POST", csrf });
}

export function quemSou(base) {
  return chamar(base, "/auth/eu");
}

/** Obras com vínculo, cada uma com o papel na obra e as ações que o servidor permite. */
export function minhasObras(base) {
  return listar(base, "/auth/obras");
}

/**
 * Toda listagem chega ao app como array.
 *
 * O servidor embrulha em `{itens: …}`; se cada tela desembrulhasse por conta
 * própria, uma leria `undefined` e a tela cairia no portão, sob sol, com a
 * carga esperando. O desembrulho acontece uma vez, aqui.
 */
async function listar(base, url, opcoes = {}) {
  const dados = await chamar(base, url, opcoes);
  return dados.itens || [];
}

// ---------------------------------------------------------------------------
// Pedidos
// ---------------------------------------------------------------------------

export function listarPedidos(base, obraId, csrf) {
  return listar(base, `/obras/${obraId}/pedidos`, { csrf });
}

export function obterPedido(base, pedidoId, csrf) {
  return chamar(base, `/pedidos/${pedidoId}`, { csrf });
}

export function listarNfeDaObra(base, obraId, csrf) {
  return listar(base, `/obras/${obraId}/nfe`, { csrf, consulta: { limite: 50 } });
}

export function listarNfeDoPedido(base, pedidoId, csrf) {
  return listar(base, `/pedidos/${pedidoId}/nfe`, { csrf });
}

export function vincularNfe(base, pedidoId, nfeLogId, csrf) {
  return chamar(base, `/pedidos/${pedidoId}/vincular-nfe`, {
    method: "POST",
    corpo: { nfe_log_id: nfeLogId },
    csrf,
  });
}

export function conciliar(base, pedidoId, csrf, nfeLogId = null) {
  return chamar(base, `/pedidos/${pedidoId}/conciliar`, {
    method: "POST",
    corpo: nfeLogId ? { nfe_log_id: nfeLogId } : {},
    csrf,
  });
}

export function listarConciliacoes(base, pedidoId, csrf) {
  return listar(base, `/pedidos/${pedidoId}/conciliacoes`, { csrf });
}

export function decidirConciliacao(base, conciliacaoId, decisao, justificativa, csrf) {
  return chamar(base, `/conciliacoes/${conciliacaoId}/decisao`, {
    method: "POST",
    corpo: { decisao, justificativa },
    csrf,
  });
}

export function listarCorrelacoes(base, pedidoId, csrf) {
  return listar(base, `/pedidos/${pedidoId}/correlacoes`, { csrf });
}

export function correlacionar(base, pedidoId, dados, csrf) {
  return chamar(base, `/pedidos/${pedidoId}/correlacoes`, { method: "POST", corpo: dados, csrf });
}

export function desfazerCorrelacao(base, correlacaoId, csrf) {
  return chamar(base, `/correlacoes/${correlacaoId}`, { method: "DELETE", csrf });
}

export function dossie(base, pedidoId, csrf) {
  return chamar(base, `/pedidos/${pedidoId}/dossie`, { csrf });
}

export function dossiePdf(base, pedidoId) {
  return chamar(base, `/pedidos/${pedidoId}/dossie.pdf`, { aceito: "application/pdf" });
}

// ---------------------------------------------------------------------------
// Recebimento e evidências
// ---------------------------------------------------------------------------

export function abrirRecebimento(base, obraId, corpo, csrf) {
  return chamar(base, `/obras/${obraId}/recebimentos`, { method: "POST", corpo, csrf });
}

/** Estado de uma entrega: status, contagem por linha e a trilha de quem mudou quê. */
export function obterRecebimento(base, recebimentoId, csrf) {
  return chamar(base, `/recebimentos/${recebimentoId}`, { csrf });
}

/**
 * Encerra a entrega. `motivo` é obrigatório: `encerrado` não é calculado em
 * nenhum lugar do sistema, é decisão de gente e precisa de assinatura.
 */
export function encerrarRecebimento(base, recebimentoId, motivo, csrf) {
  return chamar(base, `/recebimentos/${recebimentoId}/encerrar`, {
    method: "POST",
    corpo: { motivo },
    csrf,
  });
}

/** Trilha do pedido: transições de entrega e de pedido, com autor e motivo. */
export function transicoes(base, pedidoId, csrf) {
  return chamar(base, `/pedidos/${pedidoId}/transicoes`, { csrf });
}

export function listarRecebimentos(base, obraId, csrf, limite = 30) {
  return listar(base, `/obras/${obraId}/recebimentos`, { csrf, consulta: { limite } });
}

export function listarEvidencias(base, obraId, recebimentoId, csrf) {
  return listar(base, `/obras/${obraId}/evidencias`, {
    csrf,
    consulta: { recebimento_id: recebimentoId },
  });
}

/**
 * Upload autenticado. `chaveIdempotencia` é obrigatória por construção: reenviar
 * a mesma foto depois de uma falha de rede não pode criar duas evidências.
 */
export function enviarEvidencia(
  base, obraId, { arquivo, tipo, origem, recebimentoId, capturadaEm, chaveIdempotencia }, csrf,
) {
  const form = new FormData();
  form.append("arquivo", arquivo, arquivo.name || "captura.jpg");
  form.append("tipo", tipo);
  form.append("origem", origem);
  if (recebimentoId) form.append("recebimento_id", recebimentoId);
  if (capturadaEm) form.append("capturada_em", capturadaEm);
  if (chaveIdempotencia) form.append("idempotency_key", chaveIdempotencia);
  return chamar(base, `/obras/${obraId}/evidencias`, { method: "POST", formulario: form, csrf });
}

// ---------------------------------------------------------------------------
// O que já existia: conferência por chave de acesso
// ---------------------------------------------------------------------------

export async function conferirNfe(base, obraId, chaveAcesso, opts = {}) {
  const headers = { ...JSON_HEADERS };
  if (opts.apiKey) headers["X-API-KEY"] = String(opts.apiKey).trim();
  const resposta = await fetch(`${base}/conferir`, {
    method: "POST",
    headers,
    credentials: "include",
    body: JSON.stringify({ obra_id: obraId, chave_acesso: chaveAcesso }),
  });
  const texto = await resposta.text();
  let data;
  try {
    data = JSON.parse(texto);
  } catch {
    throw new Error(texto.slice(0, 200) || "Resposta inválida do servidor");
  }
  if (!resposta.ok) {
    const det = data.detail;
    throw new Error(typeof det === "string" ? det : JSON.stringify(det || data));
  }
  return data;
}

export async function pwaLogin(base, obraId, apiKey) {
  return chamar(base, "/auth/pwa/login", {
    method: "POST",
    corpo: { obra_id: obraId, api_key: apiKey },
  });
}

export async function pwaLogout(base) {
  await chamar(base, "/auth/pwa/logout", { method: "POST" }).catch(() => {});
}

/** @returns {Promise<{ok: boolean, obra_id: string} | null>} */
export async function fetchPwaSession(base) {
  const resposta = await fetch(`${base}/auth/pwa/session`, { credentials: "include" });
  if (!resposta.ok) return null;
  return resposta.json();
}

export async function fetchLaudoBlob(url, opts = {}) {
  const headers = {};
  if (opts.apiKey) headers["X-API-KEY"] = String(opts.apiKey).trim();
  const resposta = await fetch(url, {
    credentials: "include",
    headers: Object.keys(headers).length ? headers : undefined,
  });
  if (!resposta.ok) {
    const t = await resposta.text();
    throw new Error(t.slice(0, 120) || `HTTP ${resposta.status}`);
  }
  return resposta.blob();
}
