/**
 * Estado de sessão do PWA: quem entrou, em qual obra, e o que o servidor deixou.
 *
 * Nada aqui é autorização. `acoes` vem de `/auth/obras`, calculado pela matriz no
 * servidor, e serve apenas para não mostrar botão que vai dar 403. A autoridade é
 * a mesma matriz, conferida de novo em cada requisição.
 *
 * O token CSRF é lido do cookie legível quando a página recarrega — é o lado
 * cliente do double submit. Ele sozinho não autentica nada; sem o cookie HttpOnly
 * da sessão, toda chamada volta 401.
 */

import { chamar, login as apiLogin, logout as apiLogout, minhasObras, quemSou } from "./api.js";

const COOKIE_CSRF = "stellspy_csrf";
const CHAVE_OBRA = "stellspy.obra_escolhida";

/** @type {{usuario: object|null, csrf: string|null, obras: object[], obraId: string|null}} */
const estado = { usuario: null, csrf: null, obras: [], obraId: null };

function _cookieCsrf() {
  const partes = (document.cookie || "").split(";");
  for (const parte of partes) {
    const i = parte.indexOf("=");
    if (i < 0) continue;
    if (parte.slice(0, i).trim() === COOKIE_CSRF) {
      return decodeURIComponent(parte.slice(i + 1).trim());
    }
  }
  return null;
}

/** A obra escolhida sobrevive ao reload, mas é sempre revalidada no servidor. */
function _restaurarObra() {
  try {
    return sessionStorage.getItem(CHAVE_OBRA);
  } catch {
    return null;
  }
}

function _guardarObra(obraId) {
  try {
    if (obraId) sessionStorage.setItem(CHAVE_OBRA, obraId);
    else sessionStorage.removeItem(CHAVE_OBRA);
  } catch {
    /* sem storage (aba privada): a escolha só não sobrevive ao reload. */
  }
}

export function get(base) {
  return { ...estado, base };
}

export function csrf() {
  return estado.csrf;
}

export function usuario() {
  return estado.usuario;
}

export function obras() {
  return estado.obras;
}

export function obraAtual() {
  return estado.obras.find((o) => o.id === estado.obraId) || null;
}

/**
 * A ação está liberada nesta obra? Só existe para esconder botão.
 * Se a lista vier vazia (obra ainda não carregada), o botão fica escondido —
 * falhar para o lado fechado é o lado certo num app de auditoria.
 */
export function pode(acao) {
  const obra = obraAtual();
  return !!(obra && Array.isArray(obra.acoes) && obra.acoes.includes(acao));
}

export async function entrar(base, email, senha, tenant) {
  const dados = await apiLogin(base, email, senha, tenant);
  estado.usuario = dados.usuario;
  estado.csrf = dados.csrf_token || _cookieCsrf();
  // O login diz quem você é, não onde pode trabalhar. Sem buscar as obras aqui,
  // a primeira tela depois do acesso mostraria "nenhuma obra" para quem acabou
  // de entrar. Falhou? A tela de obras busca de novo, com o erro à vista.
  try {
    await _lerObras(base);
  } catch {
    estado.obras = [];
  }
  return dados;
}

export async function sair(base) {
  await apiLogout(base, estado.csrf).catch(() => {});
  estado.usuario = null;
  estado.csrf = null;
  estado.obras = [];
  estado.obraId = null;
  _guardarObra(null);
}

/**
 * Obras e ações por obra, sempre do servidor.
 *
 * A obra escolhida no aparelho só continua válida enquanto o servidor a devolve:
 * se o vínculo acabou, a escolha local é descartada em vez de virar uma tela que
 * devolve 404.
 */
async function _lerObras(base) {
  estado.obras = await minhasObras(base);
  if (estado.obraId && !estado.obras.some((o) => o.id === estado.obraId)) {
    estado.obraId = null;
    _guardarObra(null);
  }
  return estado.obras;
}

export function recarregarObras(base) {
  return _lerObras(base);
}

/**
 * Reconstroi a sessão a partir do servidor.
 *
 * Retorna `null` quando não há sessão. É chamado no boot e depois de qualquer 401
 * no meio do uso: o app nunca mostra "logado" com base no que guardou localmente.
 */
export async function restaurar(base) {
  estado.csrf = estado.csrf || _cookieCsrf();
  try {
    estado.usuario = await quemSou(base);
    await _lerObras(base);
  } catch (e) {
    estado.usuario = null;
    estado.obras = [];
    estado.obraId = null;
    return null;
  }

  const guardada = _restaurarObra();
  estado.obraId = estado.obras.some((o) => o.id === guardada) ? guardada : null;
  return estado.usuario;
}

export function escolherObra(obraId) {
  const existe = estado.obras.some((o) => o.id === obraId);
  estado.obraId = existe ? obraId : null;
  _guardarObra(estado.obraId);
  return estado.obraId;
}

/**
 * Chamada autenticada com CSRF automático e retry único em 401.
 *
 * O retry existe por um motivo concreto: a sessão pode ter sido revogada enquanto
 * a tela estava aberta. Reconstroi-se o estado uma vez e repete-se a chamada; se
 * continuar 401, o erro sobe e o roteador leva para o login.
 */
export async function comSessao(base, fn) {
  try {
    return await fn(estado.csrf);
  } catch (e) {
    if (e && e.status === 401) {
      const aindaTem = await restaurar(base);
      if (aindaTem) return await fn(estado.csrf);
    }
    throw e;
  }
}

export { chamar };
