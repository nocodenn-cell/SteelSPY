/**
 * Casca do app: liga roteador, sessão e as doze telas.
 *
 * Nada de lógica de negócio aqui. Esta camada decide apenas qual tela montar,
 * se a rota é compatível com o papel da pessoa na obra, e o que a barra de
 * navegação mostra. Toda permissão que aparece aqui é conforto — a autoridade é
 * o servidor, conferido em cada requisição.
 */

import { getApiBaseUrl } from "./config.js";
import { boot, iniciar, irPara } from "./roteador.js";
import { obraAtual, pode, usuario } from "./sessao.js";
import { blocoErro, cartao, el, estadoVazio, titulo } from "./render.js";
import {
  telaConferir,
  telaHistorico,
  telaLogin,
  telaObras,
  telaPainel,
} from "./telas_entrada.js";
import {
  telaDossie,
  telaDossies,
  telaNfe,
  telaPedido,
  telaPedidos,
  telaDivergencias,
} from "./telas_compra.js";
import { telaFotos, telaRecebimento } from "./telas_recebimento.js";

function base() {
  return getApiBaseUrl().replace(/\/$/, "");
}

/**
 * Rota → ação necessária na obra.
 *
 * Não é autorização: é para ninguém andar até uma tela que só devolveria 403 no
 * portão, sem sinal. O servidor repete a mesma conferência em cada chamada.
 */
const ACAO_POR_ROTA = {
  pedidos: "gerenciar_pedido",
  pedido: "gerenciar_pedido",
  divergencias: "ver_recebimento",
  nfe: "ver_recebimento",
  recebimento: "criar_recebimento",
  fotos: "anexar_evidencia",
  historico: "ver_recebimento",
  dossies: "ver_recebimento",
  dossie: "exportar_dossie",
  conferir: "ver_recebimento",
};

function montar(rota, params) {
  const b = base();
  if (!b && rota !== "login") {
    return cartao(
      titulo("Falta configurar", "A app não sabe onde fica a API."),
      el(
        "p",
        { class: "text-sm font-bold" },
        "Preencha apiBaseUrl no bloco ",
        el("code", { class: "font-mono" }, "#stellspy-config"),
        " do index.html.",
      ),
    );
  }

  const exigida = ACAO_POR_ROTA[rota];
  if (exigida && !pode(exigida)) {
    return cartao(
      titulo("Sem permissão aqui", `Seu papel nesta obra não tem a ação "${exigida}".`),
      estadoVazio(
        "Volte ao painel",
        "O painel mostra só o que você pode fazer nesta obra.",
        el("button", {
          type: "button",
          class: "touch-btn mt-3 w-full bg-slate-900 text-white font-black rounded-xl border-4 border-black text-sm",
          onclick: () => irPara("obra"),
        }, "IR PARA O PAINEL"),
      ),
    );
  }

  switch (rota) {
    case "login": return telaLogin(b);
    case "obras": return telaObras(b);
    case "painel": return telaPainel(b);
    case "pedidos": return telaPedidos(b);
    case "pedido": return telaPedido(b, params[0]);
    case "nfe": return telaNfe(b);
    case "recebimento": return telaRecebimento(b);
    case "fotos": return telaFotos(b, params[0]);
    case "divergencias": return telaDivergencias(b, params[0]);
    case "historico": return telaHistorico(b);
    case "dossies": return telaDossies(b);
    case "dossie": return telaDossie(b, params[0]);
    case "conferir": return telaConferir(b);
    default:
      return cartao(
        el("h2", { class: "text-lg font-black uppercase mb-2" }, "Página não encontrada"),
        blocoErro("O endereço digitado não corresponde a nenhuma tela.", () => irPara("obra")),
      );
  }
}

/** Barra de navegação: só o que o papel permite, e nenhuma opção vira beco. */
function atualizarNav(rota) {
  const nav = document.getElementById("nav");
  const quem = document.getElementById("qQuem");
  const onde = document.getElementById("qOnde");
  const u = usuario();
  const obra = obraAtual();

  quem.textContent = u ? u.nome : "";
  onde.textContent = obra ? obra.nome : "";

  if (!u || !obra || rota === "login" || rota === "obras") {
    nav.classList.add("hidden");
    return;
  }
  nav.classList.remove("hidden");
  for (const botao of nav.querySelectorAll(".nav-btn")) {
    const destino = botao.dataset.rota;
    const permitida = !ACAO_POR_ROTA[destino] || pode(ACAO_POR_ROTA[destino]);
    botao.hidden = !permitida;
    const ativo = destino === rota || (destino === "obra" && rota === "painel");
    botao.className = `nav-btn ${ativo ? "nav-btn-ativa" : ""}`;
  }
}

function tratarOffline() {
  window.addEventListener("offline", () => {
    const tela = document.getElementById("tela");
    tela.prepend(el(
      "div",
      { class: "p-3 mb-4 bg-amber-100 border-4 border-amber-600 rounded-xl text-sm font-black", role: "alert" },
      "Sem rede agora. Nada foi enviado — nada foi marcado como concluído.",
    ));
  });
}

/** A barra de navegação é estática; os destinos vêm do `data-rota` de cada botão. */
function ligarNav() {
  for (const botao of document.querySelectorAll("#nav .nav-btn")) {
    botao.addEventListener("click", () => irPara(botao.dataset.rota));
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  iniciar(base, montar, atualizarNav);
  tratarOffline();
  ligarNav();
  await boot(base);
});

if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  navigator.serviceWorker.register("./sw.js").catch(() => {});
}
