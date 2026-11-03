/**
 * Roteador do app operacional.
 *
 * Hash-route porque o app é estático e servido por qualquer CDN: não depende de
 * reescrita de URL no servidor. Uma tela por vez, sempre reconstruída — estado
 * de negócio mora no backend, estado de tela mora no hash.
 *
 * A rota é o que permite "voltar" no celular durante uma descarga, no meio de
 * uma foto, sem perder a obra escolhida.
 */

import { restaurar, sair, usuario, obraAtual } from "./sessao.js";

/** @type {{rota: string, params: string[], erro: string|null}} */
const estado = { rota: "login", params: [], erro: null };

let montador = null;
let trocaTela = null;

/**
 * Paterns na ordem importam: a primeira que casar ganha.
 * `:id` vira um segmento capturado.
 */
const ROTAS = [
  ["login", "login"],
  ["obras", "obras"],
  ["obra", "painel"],
  ["pedidos", "pedidos"],
  ["pedido/:id", "pedido", 1],
  ["nfe", "nfe"],
  ["recebimento", "recebimento"],
  ["recebimento/:id/fotos", "fotos", 1],
  ["divergencias/:id", "divergencias", 1],
  ["historico", "historico"],
  ["dossies", "dossies"],
  ["dossie/:id", "dossie", 1],
  ["conferir", "conferir"],
];

function _parsear(hash) {
  const caminho = String(hash || "").replace(/^#\/?/, "").replace(/\/$/, "");
  const segmentos = caminho ? caminho.split("/") : [];
  for (const [padrao, nome, captura] of ROTAS) {
    const partes = padrao.split("/");
    if (partes.length !== segmentos.length) continue;
    const params = [];
    let casou = true;
    for (let i = 0; i < partes.length; i += 1) {
      if (partes[i].startsWith(":")) params.push(decodeURIComponent(segmentos[i]));
      else if (partes[i] !== segmentos[i]) { casou = false; break; }
    }
    if (casou) return { rota: nome, params: params.slice(0, captura || 0) };
  }
  return null;
}

export function irPara(caminho) {
  const alvo = caminho.startsWith("#") ? caminho : `#/${caminho.replace(/^\//, "")}`;
  if (location.hash === alvo) renderizar();
  else location.hash = alvo;
}

export function rotaAtual() {
  return { ...estado };
}

/** Sessão é pré-requisito de toda rota menos a de login. */
function _exigirSessao(rotas) {
  return rotas !== "login" && !usuario();
}

export function renderizar() {
  const parsed = _parsear(location.hash) || (usuario() ? { rota: "obra", params: [] } : { rota: "login", params: [] });
  estado.rota = parsed.rota;
  estado.params = parsed.params;

  if (_exigirSessao(parsed.rota)) {
    location.hash = "#/login";
    return;
  }
  // Sessão viva não se apresenta como porta de entrada: quem já entrou volta
  // para a obra em que estava, em vez de reler a senha numa tela vazia.
  if (parsed.rota === "login" && usuario()) {
    location.hash = obraAtual() ? "#/obra" : "#/obras";
    return;
  }
  // Toda tela operacional precisa de obra escolhida; só a de seleção dispensa.
  if (!obraAtual() && !["login", "obras"].includes(parsed.rota)) {
    location.hash = "#/obras";
    return;
  }

  const container = document.getElementById("tela");
  container.textContent = "";
  container.append(montador(parsed.rota, parsed.params));
  if (trocaTela) trocaTela(parsed.rota);
}

/**
 * Registra o montador de telas e assume o controle do hash.
 *
 * `on401` existe porque sessão revogada no meio do uso tem que levar a pessoa de
 * volta ao login com o motivo dito, não com uma tela vazia.
 */
export function iniciar(getApiBase, montar, aoTrocar) {
  montador = montar;
  trocaTela = aoTrocar;
  window.addEventListener("hashchange", () => renderizar());
  window.addEventListener("stellspy:401", async () => {
    await sair(getApiBase());
    location.hash = "#/login";
    renderizar();
  });
}

export async function boot(getApiBase) {
  const base = getApiBase();
  await restaurar(base);
  if (!usuario()) location.hash = "#/login";
  else if (!location.hash || location.hash === "#/") {
    location.hash = obraAtual() ? "#/obra" : "#/obras";
  }
  renderizar();
  return usuario();
}
