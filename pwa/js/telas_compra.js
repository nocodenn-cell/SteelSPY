/**
 * Telas de compra: pedido, nota fiscal, divergência e dossiê.
 *
 * Estas são as telas onde a auditoria acontece. A regra de ouro delas é a mesma
 * do motor de correlação: o app mostra a evidência e quem decide é gente. Nenhuma
 * tela daqui "resolve" uma ambiguidade sozinha — ela oferece a escolha e grava a
 * assinatura de quem escolheu.
 */

import {
  conciliar,
  decidirConciliacao,
  desfazerCorrelacao,
  dossie,
  dossiePdf,
  listarConciliacoes,
  listarCorrelacoes,
  listarNfeDaObra,
  listarNfeDoPedido,
  listarPedidos,
  obterPedido,
  correlacionar,
  vincularNfe,
} from "./api.js";
import {
  badgeSeveridade,
  blocoErro,
  cartao,
  carregando,
  campo,
  el,
  estadoVazio,
  formatoDataHora,
  formatoNumero,
  mostrarToast,
  protegerEnvio,
  rotuloStatusLinha,
  titulo,
} from "./render.js";
import { csrf, pode } from "./sessao.js";
import { irPara } from "./roteador.js";
import { obraDaTela, tentar } from "./telas_entrada.js";

// ---------------------------------------------------------------------------
// Pedidos
// ---------------------------------------------------------------------------

export function telaPedidos(base) {
  const obra = obraDaTela();
  const corpo = el("div", {}, carregando());
  const busca = el("input", {
    type: "search", class: "w-full p-3 mb-4 border-4 border-black rounded-lg text-base font-bold",
    placeholder: "número do pedido", autocomplete: "off",
  });
  let todos = [];

  function pintar() {
    const filtro = busca.value.trim().toLowerCase();
    const itens = todos.filter((p) => !filtro || String(p.numero).toLowerCase().includes(filtro));
    corpo.textContent = "";
    if (!todos.length) {
      corpo.append(estadoVazio(
        "Nenhum pedido nesta obra",
        "Cadastre o pedido no sistema da construtora ou peça ao administrador para importar.",
      ));
      return;
    }
    if (!itens.length) {
      corpo.append(estadoVazio("Nada encontrado", `Nenhum pedido com "${busca.value}".`));
      return;
    }
    for (const p of itens) {
      corpo.append(el(
        "button",
        {
          type: "button",
          class: "w-full text-left bg-white border-4 border-black rounded-xl mb-3 p-4 shadow-[3px_3px_0_#000]",
          onclick: () => irPara(`pedido/${p.id}`),
        },
        el(
          "div",
          { class: "flex items-center justify-between gap-2 mb-1" },
          el("span", { class: "font-black text-lg" }, `Pedido ${p.numero}`),
          badgeSeveridade(_severidadeDoStatus(p.status)),
        ),
        el(
          "p",
          { class: "text-sm font-bold text-gray-700" },
          `${formatoNumero(p.valor_total, { unidade: "R$" })} · ${formatoDataHora(p.emitido_em)}`,
        ),
      ));
    }
  }

  async function carregar() {
    corpo.textContent = "";
    corpo.append(carregando());
    try {
      todos = await tentar(base, () => listarPedidos(base, obra.id, csrf()));
      pintar();
    } catch (e) {
      corpo.textContent = "";
      corpo.append(blocoErro(e.message || "Não carregou os pedidos.", carregar));
    }
  }

  busca.addEventListener("input", pintar);
  setTimeout(carregar, 0);

  return cartao(
    titulo("Pedidos de compra", "O que a obra combinou de receber."),
    busca,
    corpo,
  );
}

function _severidadeDoStatus(status) {
  return { completo: "VERDE", parcial: "AMARELO", divergente: "VERMELHO", encerrado: "VERDE" }[status] || "PENDENTE";
}

// ---------------------------------------------------------------------------
// Pedido: detalhe, vínculo de NF-e e correlação
// ---------------------------------------------------------------------------

export function telaPedido(base, pedidoId) {
  const obra = obraDaTela();
  const corpo = el("div", {}, carregando());

  async function carregar() {
    corpo.textContent = "";
    corpo.append(carregando());
    try {
      const [pedido, notas, correlacoes, conciliacoes] = await tentar(base, () =>
        Promise.all([
          obterPedido(base, pedidoId),
          listarNfeDoPedido(base, pedidoId),
          listarCorrelacoes(base, pedidoId),
          listarConciliacoes(base, pedidoId),
        ]),
      );
      corpo.textContent = "";
      corpo.append(
        _cartaoPedido(pedido),
        _cartaoLinhas(pedido),
        _cartaoNotas(base, obra, pedido, notas, carregar),
        _cartaoCorrelacoes(base, correlacoes, pedido, carregar),
        _cartaoAcoes(base, pedido, conciliacoes, carregar),
      );
    } catch (e) {
      corpo.textContent = "";
      corpo.append(blocoErro(e.message || "Não carregou o pedido.", carregar));
    }
  }

  setTimeout(carregar, 0);
  return el("div", {}, corpo);
}

function _cartaoPedido(pedido) {
  return cartao(
    titulo(`Pedido ${pedido.numero}`, `Status: ${rotuloStatusLinha(pedido.status) || pedido.status}`),
    campo("Emitido em", pedido.emitido_em ? formatoDataHora(pedido.emitido_em) : null),
    campo("Previsão de entrega", pedido.previsao_entrega ? formatoDataHora(pedido.previsao_entrega) : null),
    campo("Valor total", formatoNumero(pedido.valor_total, { unidade: "R$" })),
    campo("Observações", pedido.observacoes),
  );
}

function _cartaoLinhas(pedido) {
  const linhas = pedido.itens.map((i) => el(
    "div",
    { class: "py-3 border-b-4 border-gray-200 last:border-0" },
    el(
      "div",
      { class: "flex items-start justify-between gap-2" },
      el("span", { class: "font-black text-base" }, `L${i.linha} · ${i.material_tipo}`),
      el("span", { class: "text-sm font-black whitespace-nowrap" }, `${formatoNumero(i.quantidade)} ${i.unidade}`),
    ),
    el(
      "p",
      { class: "text-xs font-bold text-gray-700 mt-1" },
      [
        i.bitola_mm ? `Ø ${formatoNumero(i.bitola_mm, { casas: 1 })} mm` : null,
        i.marca_exigida ? `marca ${i.marca_exigida}` : null,
        i.codigo_produto_fornecedor ? `código ${i.codigo_produto_fornecedor}` : "sem código do fornecedor",
      ]
        .filter(Boolean)
        .join(" · "),
    ),
  ));

  return cartao(
    el("h3", { class: "text-base font-black uppercase mb-2" }, `Linhas do pedido (${pedido.itens.length})`),
    ...linhas,
  );
}

/**
 * Botão "vincular nota".
 *
 * A lista de notas da obra vem do servidor, mas o vínculo só é aceito se nota e
 * pedido forem da mesma obra, do mesmo tenant e se o emitente bater com o
 * fornecedor — conferência que o backend refaz, não o navegador.
 */
function _cartaoNotas(base, obra, pedido, notas, aoMudar) {
  const corpo = el("div", {});
  if (!notas.length) {
    corpo.append(estadoVazio(
      "Nenhuma nota vinculada",
      "Sem nota não há cobrança para comparar. Vincule a NF-e que chegou com a carga.",
    ));
  } else {
    for (const n of notas) {
      corpo.append(el(
        "div",
        { class: "py-3 border-b-4 border-gray-200 last:border-0" },
        el(
          "div",
          { class: "flex items-center justify-between gap-2" },
          el("span", { class: "font-black text-sm break-all" }, `Chave …${String(n.chave_acesso).slice(-8)}`),
          badgeSeveridade(n.status_conferencia),
        ),
        el(
          "p",
          { class: "text-xs font-bold text-gray-700 mt-1" },
          `${n.itens.length} item(ns) faturado(s) · ${formatoDataHora(n.processado_em)}`,
        ),
        el(
          "ul",
          { class: "mt-2 text-xs font-bold text-gray-800 list-disc pl-5" },
          ...n.itens.map((i) => el(
            "li",
            {},
            `${i.n_item}. ${i.descricao || "sem descrição"} — ${formatoNumero(i.quantidade)} ${i.unidade || ""}${i.codigo_produto ? " · " + i.codigo_produto : ""}`,
          )),
        ),
      ));
    }
  }

  if (pode("gerenciar_pedido")) {
    const avisos = el("div", {});
    const seletorNota = el("select", {
      class: "w-full p-3 mb-2 border-4 border-black rounded-lg text-sm font-bold",
    }, el("option", { value: "" }, "Carregando notas da obra…"));
    const botao = el("button", {
      type: "button",
      class: "touch-btn w-full bg-slate-800 text-white font-black rounded-xl border-4 border-black text-sm mb-3",
    }, "VINCULAR NOTA AO PEDIDO");

    botao.addEventListener("click", () => {
      if (!seletorNota.value) {
        avisos.textContent = "";
        avisos.append(blocoErro("Escolha a nota que chegou com a carga."));
        return;
      }
      protegerEnvio(botao, async () => {
        try {
          await tentar(base, () => vincularNfe(base, pedido.id, seletorNota.value, csrf()));
          mostrarToast("Nota vinculada.", "sucesso");
          aoMudar();
        } catch (e) {
          avisos.textContent = "";
          avisos.append(blocoErro(e.message || "Não vinculou."));
        }
      });
    });

    // As notas aptas a vincular são as da obra ainda sem pedido — 404 não é
    // opção aqui: a lista é a mesma que a tela de notas mostra.
    tentar(base, () => listarNfeDaObra(base, obra.id))
      .then((dados) => {
        seletorNota.textContent = "";
        seletorNota.append(el("option", { value: "" }, "Escolher nota…"));
        const livres = dados.filter((n) => !n.pedido_id);
        if (!livres.length) {
          seletorNota.append(el("option", { value: "" }, "Nenhuma nota livre nesta obra"));
          seletorNota.disabled = true;
          botao.disabled = true;
          return;
        }
        for (const n of livres) {
          seletorNota.append(el(
            "option",
            { value: n.id },
            `…${String(n.chave_acesso).slice(-8)} · ${n.status_conferencia || "sem conferência"}`,
          ));
        }
      })
      .catch(() => {
        seletorNota.textContent = "";
        seletorNota.append(el("option", { value: "" }, "Não foi possível listar as notas"));
      });

    corpo.append(
      el("h4", { class: "text-sm font-black uppercase mt-4 mb-2" }, "Vincular uma nota"),
      avisos,
      seletorNota,
      botao,
    );
  }

  return cartao(
    el("h3", { class: "text-base font-black uppercase mb-2" }, "Notas fiscais"),
    el(
      "p",
      { class: "text-xs font-bold text-gray-700 mb-3" },
      "A nota é a cobrança. Sozinha ela não prova o que entrou no portão.",
    ),
    corpo,
  );
}

function _cartaoCorrelacoes(base, correlacoes, pedido, aoMudar) {
  const ativas = correlacoes.filter((c) => !c.removido_em);
  const porItem = new Map(pedido.itens.map((i) => [i.id, `L${i.linha}`]));

  const corpo = el("div", {});
  if (!ativas.length) {
    corpo.append(el(
      "p",
      { class: "text-sm font-bold text-gray-700" },
      "Nenhuma correlação manual. O sistema associa sozinho quando há evidência suficiente.",
    ));
  }
  for (const c of ativas) {
    const desfazer = el("button", {
      type: "button",
      class: "text-xs font-black text-red-800 underline",
    }, "desfazer");
    desfazer.addEventListener("click", () => {
      protegerEnvio(desfazer, async () => {
        try {
          await tentar(base, () => desfazerCorrelacao(base, c.id, csrf()));
          mostrarToast("Correlação encerrada.", "sucesso");
          aoMudar();
        } catch (e) {
          mostrarToast(e.message || "Não desfez.", "erro");
        }
      });
    });

    corpo.append(el(
      "div",
      { class: "flex items-center justify-between gap-2 py-2 border-b-2 border-gray-200 last:border-0" },
      el(
        "span",
        { class: "text-sm font-bold" },
        `${porItem.get(c.pedido_item_id) || "linha"} ← nota item ${c.nfe_item_numero}${c.quantidade ? ` (${formatoNumero(c.quantidade)})` : ""}`,
      ),
      pode("gerenciar_pedido") ? desfazer : null,
    ));
  }
  return cartao(
    el("h3", { class: "text-base font-black uppercase mb-2" }, "Correlações manuais"),
    el(
      "p",
      { class: "text-xs font-bold text-gray-700 mb-2" },
      "Encerrar não apaga: fica no banco quem correlacionou e quando.",
    ),
    corpo,
  );
}

function _cartaoAcoes(base, pedido, conciliacoes, aoMudar) {
  const ultima = conciliacoes[0] || null;
  const corpo = el("div", {});

  if (pode("criar_recebimento")) {
    const botao = el("button", {
      type: "button",
      class: "touch-btn w-full bg-blue-600 text-white font-black rounded-xl border-4 border-black mb-3",
    }, "CONCILIAR AGORA");
    botao.addEventListener("click", () => {
      protegerEnvio(botao, async () => {
        try {
          const dados = await tentar(base, () => conciliar(base, pedido.id, csrf()));
          const sev = dados.resultado.severidade_tecnica;
          mostrarToast(`Conciliação: ${sev}`, sev === "VERDE" ? "sucesso" : "erro");
          aoMudar();
        } catch (e) {
          mostrarToast(e.message || "Não conciliou.", "erro");
        }
      });
    });
    corpo.append(botao);
  }

  corpo.append(
    el(
      "button",
      {
        type: "button",
        class: "touch-btn w-full bg-white text-black font-black rounded-xl border-4 border-black mb-3",
        onclick: () => irPara(`divergencias/${pedido.id}`),
      },
      "VER DIVERGÊNCIAS E DECIDIR",
    ),
    el(
      "button",
      {
        type: "button",
        class: "touch-btn w-full bg-slate-900 text-white font-black rounded-xl border-4 border-black",
        onclick: () => irPara(`dossie/${pedido.id}`),
      },
      "DOSSIÊ DO PEDIDO",
    ),
  );

  const rodape = ultima
    ? el(
        "p",
        { class: "text-xs font-bold text-gray-700 mt-3" },
        `Última conciliação ${formatoDataHora(ultima.criado_em)} · ${ultima.severidade_tecnica} · ${
          ultima.status === "em_analise" ? "aguardando decisão" : `decidida: ${ultima.status}`
        }`,
      )
    : el("p", { class: "text-xs font-bold text-gray-700 mt-3" }, "Ainda não rodou conciliação neste pedido.");

  return cartao(el("h3", { class: "text-base font-black uppercase mb-2" }, "O que fazer"), corpo, rodape);
}

// ---------------------------------------------------------------------------
// Notas fiscais da obra
// ---------------------------------------------------------------------------

export function telaNfe(base) {
  const obra = obraDaTela();
  const corpo = el("div", {}, carregando());

  async function carregar() {
    corpo.textContent = "";
    corpo.append(carregando());
    try {
      const notas = await tentar(base, () => listarNfeDaObra(base, obra.id));
      corpo.textContent = "";
      if (!notas.length) {
        corpo.append(estadoVazio("Nenhuma nota nesta obra", "A nota aparece depois de processada pelo servidor."));
        return;
      }
      for (const n of notas) {
        // resumo_global é o texto curto que o motor de conferência gravou.
        const resumo = String(n.resumo_global || "");
        corpo.append(el(
          "div",
          { class: "bg-white border-4 border-black rounded-xl mb-3 p-4" },
          el(
            "div",
            { class: "flex items-center justify-between gap-2 mb-1" },
            el("span", { class: "font-mono text-xs font-black break-all" }, `…${String(n.chave_acesso).slice(-12)}`),
            badgeSeveridade(n.status_conferencia),
          ),
          el(
            "p",
            { class: "text-xs font-bold text-gray-700" },
            `${formatoDataHora(n.processado_em)} · ${n.tipo === "entrada" ? "entrada" : n.tipo || "—"}`,
          ),
          el(
            "p",
            { class: "text-sm font-bold mt-2" },
            resumo || "Sem resumo do servidor.",
          ),
          n.pedido_id
            ? el("button", {
                type: "button",
                class: "text-xs font-black text-blue-800 underline mt-2",
                onclick: () => irPara(`pedido/${n.pedido_id}`),
              }, "ver o pedido vinculado")
            : pode("gerenciar_pedido")
              ? el("p", { class: "text-xs font-bold text-gray-700 mt-2" }, "sem pedido vinculado — vincule pela tela do pedido")
              : null,
        ));
      }
    } catch (e) {
      corpo.textContent = "";
      corpo.append(blocoErro(e.message || "Não carregou as notas.", carregar));
    }
  }

  setTimeout(carregar, 0);
  return cartao(
    titulo("Notas fiscais da obra", "O que o fornecedor cobrou."),
    corpo,
  );
}

// ---------------------------------------------------------------------------
// Divergências e decisão humana
// ---------------------------------------------------------------------------

export function telaDivergencias(base, pedidoId) {
  const corpo = el("div", {}, carregando());

  async function carregar() {
    corpo.textContent = "";
    corpo.append(carregando());
    try {
      const [conciliacoes, pedido, correlacoes] = await tentar(base, () =>
        Promise.all([
          listarConciliacoes(base, pedidoId),
          obterPedido(base, pedidoId),
          listarCorrelacoes(base, pedidoId),
        ]),
      );
      corpo.textContent = "";
      if (!conciliacoes.length) {
        corpo.append(estadoVazio(
          "Sem conciliação",
          "Rode a conciliação na tela do pedido para ver as divergências.",
          el("button", {
            type: "button",
            class: "touch-btn mt-3 w-full bg-blue-600 text-white font-black rounded-xl border-4 border-black text-sm",
            onclick: () => irPara(`pedido/${pedidoId}`),
          }, "IR PARA O PEDIDO"),
        ));
        return;
      }
      // Só o que ainda vale: correlação desfeita fica no histórico, não disputa item.
      const ativas = correlacoes.filter((x) => !x.removido_em);
      // A tela é sobre a decisão de agora. `listar_conciliacoes` vem da mais recente;
      // reexibir as substituídas com formulário vivo levaria a pessoa a correlacionar
      // contra uma foto que o sistema já superou.
      const [atual, ...anteriores] = conciliacoes;
      corpo.append(_cartaoConciliacao(base, atual, pedido, carregar, ativas));
      if (anteriores.length) {
        corpo.append(cartao(
          el("h3", { class: "text-base font-black uppercase mb-2" }, "CONCILIAÇÕES ANTERIORES"),
          ...anteriores.map((c) => el(
            "p",
            { class: "text-xs font-bold mb-1" },
            `${formatoDataHora(c.criado_em)} · ${c.severidade_tecnica} · ` +
              (c.status === "em_analise" ? "sem decisão" : c.status),
          )),
          el(
            "p",
            { class: "text-xs font-bold text-gray-700 mt-2" },
            "Cada conciliação guarda o que o sistema viu na hora. O histórico completo está no dossiê do pedido.",
          ),
        ));
      }
    } catch (e) {
      corpo.textContent = "";
      corpo.append(blocoErro(e.message || "Não carregou as divergências.", carregar));
    }
  }

  setTimeout(carregar, 0);
  return el(
    "div",
    {},
    cartao(
      titulo("Divergências", "O que o sistema encontrou e o que só gente pode decidir."),
      el(
        "p",
        { class: "text-sm font-bold text-gray-700" },
        "Aceitar uma divergência é ato de responsabilidade técnica. Sua decisão fica gravada com seu nome e horário.",
      ),
    ),
    corpo,
  );
}

function _cartaoConciliacao(base, c, pedido, aoMudar, ativas) {
  const progresso = c.progresso || {};
  const linhas = c.linhas || [];
  const ambiguidades = c.ambiguidades || [];
  const semPedido = c.faturados_sem_pedido || [];

  const blocos = [];

  for (const l of linhas) {
    if (l.severidade_tecnica === "VERDE" && l.status_linha !== "revisao") continue;
    blocos.push(el(
      "div",
      { class: "py-3 border-b-4 border-gray-200 last:border-0" },
      el(
        "div",
        { class: "flex items-center justify-between gap-2" },
        el("span", { class: "font-black text-sm" }, `L${l.linha} · ${l.material}`),
        badgeSeveridade(l.severidade_tecnica),
      ),
      el("p", { class: "text-xs font-bold uppercase text-gray-600 mt-1" }, rotuloStatusLinha(l.status_linha)),
      ...(l.motivos || []).map((m) => el("p", { class: "text-sm font-bold mt-1" }, m)),
      l.incompatibilidade_unidade
        ? el("p", { class: "text-xs font-bold text-amber-900 mt-1" }, "Unidade incompatível entre pedido e nota.")
        : null,
    ));
  }

  for (const a of ambiguidades) {
    blocos.push(_blocoAmbiguidade(base, a, pedido, aoMudar, ativas));
  }

  for (const f of semPedido) {
    blocos.push(el(
      "div",
      { class: "py-3 border-b-4 border-gray-200 last:border-0" },
      el(
        "div",
        { class: "flex items-center justify-between gap-2" },
        el("span", { class: "font-black text-sm" }, `Cobrança sem linha: item ${f.n_item}`),
        badgeSeveridade("VERMELHO"),
      ),
      el("p", { class: "text-sm font-bold mt-1" }, f.descricao || "item sem descrição"),
      el(
        "p",
        { class: "text-xs font-bold text-gray-700 mt-1" },
        `${formatoNumero(f.quantidade)} ${f.unidade || ""} · nada no pedido bate com isto.`,
      ),
    ));
  }

  const pct = progresso.percentual_faturado;
  return cartao(
    el(
      "div",
      { class: "flex items-center justify-between gap-2 mb-3" },
      el("h3", { class: "text-base font-black uppercase" }, `Pedido ${pedido.numero}`),
      badgeSeveridade(c.severidade_tecnica),
    ),
    el(
      "div",
      { class: "grid grid-cols-2 gap-2 mb-3" },
      _mini("Faturado do pedido", pct === null || pct === undefined ? "—" : `${Math.round(pct * 100)}%`),
      _mini("Linhas", String(progresso.total_linhas || 0)),
      _mini("Conciliada em", formatoDataHora(c.criado_em)),
      _mini("Decisão", c.status === "em_analise" ? "aberta" : c.status),
    ),
    c.requer_revisao_humana
      ? el(
          "p",
          { class: "p-3 bg-amber-100 border-4 border-amber-600 rounded-xl text-sm font-bold mb-3" },
          "Tem ponto que o sistema não resolve sozinho: falta evidência para associar, sobra cobrança sem linha ou quantidade fora do combinado. Quem decide é você.",
        )
      : null,
    c.aviso
      ? el("p", { class: "text-xs font-bold text-gray-700 mb-3" }, c.aviso)
      : null,
    blocos.length
      ? el("div", {}, ...blocos)
      : el("p", { class: "text-sm font-bold text-green-800" }, "Nenhuma linha fora do acordo."),
    ambiguidades.length && ativas.length && pode("criar_recebimento")
      ? _avisoReconciliar(base, pedido, aoMudar)
      : null,
    // O vocabulário do banco é em_analise | aceita | rejeitada. "em_analise" é a
    // divergência ainda sem dono: é aqui que a decisão humana acontece.
    c.status === "em_analise" && pode("override") ? _formularioDecisao(base, c, aoMudar) : null,
    c.status === "em_analise" && !pode("override")
      ? el(
          "p",
          { class: "text-xs font-bold text-gray-700 mt-3" },
          "Há divergência esperando decisão. Seu papel nesta obra não registra decisões.",
        )
      : null,
    c.status !== "em_analise"
      ? el(
          "p",
          { class: "text-xs font-bold text-gray-700 mt-3" },
          `Decisão ${c.status} registrada${c.decidida_por ? " por " + c.decidida_por : ""}.`,
        )
      : null,
  );
}

function _mini(rotulo, valor) {
  return el(
    "div",
    { class: "p-2 bg-slate-100 border-4 border-black rounded-xl" },
    el("p", { class: "text-xs font-bold uppercase text-gray-600" }, rotulo),
    el("p", { class: "text-lg font-black leading-none" }, valor),
  );
}

/**
 * Ambiguidade: o motor mostrou os candidatos e parou. Aqui a pessoa escolhe, e a
 * escolha vira correlação manual com autoria.
 */
function _avisoReconciliar(base, pedido, aoMudar) {
  const avisos = el("div", {});
  const botao = el("button", {
    type: "button",
    class: "touch-btn w-full bg-blue-700 text-white font-black rounded-xl border-4 border-black text-sm mt-2",
  }, "RECONCILIAR COM AS MINHAS ESCOLHAS");

  botao.addEventListener("click", () => {
    protegerEnvio(botao, async () => {
      try {
        const r = await tentar(base, () => conciliar(base, pedido.id, csrf()));
        mostrarToast(`Conciliação: ${r.severidade_tecnica}.`, "sucesso");
        aoMudar();
      } catch (e) {
        avisos.textContent = "";
        avisos.append(blocoErro(e.message || "Não conciliou."));
      }
    });
  });

  return el(
    "div",
    { class: "p-3 bg-slate-100 border-4 border-black rounded-xl mt-3" },
    el(
      "p",
      { class: "text-xs font-bold" },
      "Suas correlações já foram registradas. Os números acima são da conciliação anterior — rode de novo para o sistema recalcular com elas.",
    ),
    avisos,
    botao,
  );
}

function _blocoAmbiguidade(base, a, pedido, aoMudar, ativas) {
  const linha = pedido.itens.find((i) => String(i.id) === String(a.pedido_item_id));
  const seletor = el("select", { class: "w-full p-3 mb-2 border-4 border-black rounded-lg text-sm font-bold" });
  seletor.append(el("option", { value: "" }, "Escolher item da nota…"));

  // A conciliação é uma foto do momento em que rodou. Se a pessoa já atribuiu
  // este item a uma linha, a foto está velha: mostrar como se ainda sobrasse
  // convidaria a pedir o mesmo aço duas vezes.
  const reivindicado = new Map();
  for (const x of ativas) {
    const chave = `${x.nfe_log_id}:${x.nfe_item_numero}`;
    reivindicado.set(chave, (reivindicado.get(chave) || 0) + Number(x.quantidade ?? -1));
  }
  const meus = ativas.filter((x) => String(x.pedido_item_id) === String(a.pedido_item_id));

  for (const cand of a.candidatos || []) {
    const total = Number(cand.quantidade ?? 0);
    const chave = `${cand.nfe_log_id}:${cand.n_item}`;
    const tomadoBruto = reivindicado.get(chave);
    const tomado = tomadoBruto === undefined ? 0 : (tomadoBruto < 0 ? total : tomadoBruto);
    const sobrando = ((cand.saldo ?? total) - tomado);
    const esgotado = total > 0 && sobrando <= 0;
    const meu = meus.some((x) => x.nfe_log_id === cand.nfe_log_id && Number(x.nfe_item_numero) === Number(cand.n_item));
    seletor.append(el(
      "option",
      { value: `${cand.nfe_log_id}:${cand.n_item}`, disabled: esgotado },
      `item ${cand.n_item} · ${cand.descricao || "sem descrição"} · ${formatoNumero(cand.quantidade)} ${cand.unidade || ""}` +
        (esgotado
          ? (meu ? " — já é seu" : " — já atribuído a outra linha")
          : (cand.saldo !== null && cand.saldo !== undefined ? ` (sobrando ${formatoNumero(sobrando)})` : "")),
    ));
  }

  const qtd = el("input", {
    type: "number", step: "0.001", min: "0", inputmode: "decimal",
    class: "w-full p-3 mb-2 border-4 border-black rounded-lg text-sm font-bold",
    placeholder: "quantidade (vazio = item inteiro)",
  });
  const obs = el("textarea", {
    rows: "2", class: "w-full p-3 mb-2 border-4 border-black rounded-lg text-sm font-bold",
    placeholder: "por que esta linha é este item",
  });
  const avisos = el("div", {});
  const botao = el("button", {
    type: "button",
    class: "touch-btn w-full bg-green-700 text-white font-black rounded-xl border-4 border-black text-sm",
  }, "CONFIRMAR CORRESPONDÊNCIA");

  botao.addEventListener("click", () => {
    if (!seletor.value || !linha) {
      avisos.textContent = "";
      avisos.append(blocoErro("Escolha o item da nota antes de confirmar."));
      return;
    }
    if ((obs.value || "").trim().length < 5) {
      avisos.textContent = "";
      avisos.append(blocoErro("Escreva o motivo em poucas palavras. Fica no registro."));
      return;
    }
    const [nfeLogId, nItem] = seletor.value.split(":");
    protegerEnvio(botao, async () => {
      try {
        await tentar(base, () => correlacionar(base, pedido.id, {
          pedido_item_id: linha.id,
          nfe_log_id: nfeLogId,
          nfe_item_numero: Number(nItem),
          quantidade: qtd.value ? Number(qtd.value) : null,
          observacao: obs.value.trim(),
        }, csrf()));
        mostrarToast("Correspondência registrada.", "sucesso");
        aoMudar();
      } catch (e) {
        avisos.textContent = "";
        avisos.append(blocoErro(e.message || "Não registrou."));
      }
    });
  });

  return el(
    "div",
    { class: "p-4 bg-amber-50 border-4 border-black rounded-xl mb-3" },
    el("p", { class: "font-black text-sm mb-1" }, `L${a.linha} · ${linha ? linha.material_tipo : "linha"}`),
    el("p", { class: "text-xs font-bold mb-2" }, a.motivo),
    ...(meus.length
      ? meus.map((x) => el(
          "p",
          { class: "text-xs font-black text-green-800 mb-1" },
          `Atribuído: item ${x.nfe_item_numero} · ` +
          (x.quantidade === null ? "item inteiro" : `${formatoNumero(x.quantidade)} desta linha`) +
          ` · ${formatoDataHora(x.criado_em)}`,
        ))
      : []),
    el(
      "p",
      { class: "text-xs font-bold text-gray-700 mb-2" },
      `Disputado por: ${(a.disputado_por_linha || []).map((l) => `L${l}`).join(", ") || "—"}`,
    ),
    pode("gerenciar_pedido")
      ? el("div", {}, avisos, seletor, qtd, obs, botao)
      : el("p", { class: "text-xs font-bold" }, "Seu papel não registra correspondência. Peça a quem gerencia o pedido."),
  );
}

function _formularioDecisao(base, c, aoMudar) {
  const justificativa = el("textarea", {
    rows: "3", class: "w-full p-3 mb-2 border-4 border-black rounded-lg text-sm font-bold",
    placeholder: "o que foi decidido e por quê (mínimo 5 caracteres)",
  });
  const avisos = el("div", {});

  function botao(rotulo, decisao, cor) {
    const b = el("button", {
      type: "button",
      class: `touch-btn w-full ${cor} text-white font-black rounded-xl border-4 border-black text-sm mb-2`,
    }, rotulo);
    b.addEventListener("click", () => {
      if (justificativa.value.trim().length < 5) {
        avisos.textContent = "";
        avisos.append(blocoErro("Justificativa é obrigatória. Ela é a prova da decisão."));
        return;
      }
      protegerEnvio(b, async () => {
        try {
          await tentar(base, () => decidirConciliacao(base, c.id, decisao, justificativa.value.trim(), csrf()));
          mostrarToast(`Decisão registrada: ${decisao}.`, "sucesso");
          aoMudar();
        } catch (e) {
          avisos.textContent = "";
          avisos.append(blocoErro(e.message || "Não registrou a decisão."));
        }
      });
    });
    return b;
  }

  return el(
    "div",
    { class: "mt-4 pt-4 border-t-4 border-black" },
    el("h4", { class: "text-sm font-black uppercase mb-2" }, "Decidir"),
    avisos,
    justificativa,
    botao("ACEITAR DIVERGÊNCIA", "aceita", "bg-green-700"),
    botao("REJEITAR / BLOQUEAR", "rejeitada", "bg-red-700"),
  );
}

// ---------------------------------------------------------------------------
// Dossiê
// ---------------------------------------------------------------------------

export function telaDossies(base) {
  const obra = obraDaTela();
  const corpo = el("div", {}, carregando());

  async function carregar() {
    corpo.textContent = "";
    corpo.append(carregando());
    try {
      const pedidos = await tentar(base, () => listarPedidos(base, obra.id, csrf()));
      corpo.textContent = "";
      if (!pedidos.length) {
        corpo.append(estadoVazio("Sem pedido", "Dossiê se faz de um pedido. Cadastre-o primeiro."));
        return;
      }
      for (const p of pedidos) {
        corpo.append(el(
          "button",
          {
            type: "button",
            class: "w-full text-left bg-white border-4 border-black rounded-xl mb-3 p-4 font-black",
            onclick: () => irPara(`dossie/${p.id}`),
          },
          `Dossiê do pedido ${p.numero}`,
        ));
      }
    } catch (e) {
      corpo.textContent = "";
      corpo.append(blocoErro(e.message || "Não carregou.", carregar));
    }
  }

  setTimeout(carregar, 0);
  return cartao(titulo("Dossiês", "A prova completa de cada pedido."), corpo);
}

export function telaDossie(base, pedidoId) {
  const corpo = el("div", {}, carregando());

  async function carregar() {
    corpo.textContent = "";
    corpo.append(carregando());
    try {
      const d = await tentar(base, () => dossie(base, pedidoId));
      corpo.textContent = "";
      corpo.append(
        cartao(
          titulo(`Dossiê — pedido ${d.pedido.numero}`, `Status do pedido: ${d.pedido.status}`),
          campo("Identificador", d.id),
          campo("Gerado em", d.gerado_em ? formatoDataHora(d.gerado_em) : null),
          campo("Notas", String(d.total_nfe ?? (d.nfe || []).length)),
          campo("Evidências", String(d.total_evidencias)),
          campo("Conciliações", String(d.total_conciliacoes)),
          d.ressalva ? el("p", { class: "text-xs font-bold text-gray-700 mt-3" }, d.ressalva) : null,
        ),
        _blocoLista("Notas fiscais", (d.nfe || []).map((n) =>
          el("p", { class: "text-sm font-bold py-2 border-b-2 border-gray-200 last:border-0" },
            `…${String(n.chave_acesso).slice(-8)} · ${n.status_conferencia || "sem status"}`)),
        "Nenhuma nota vinculada."),
        _blocoEvidencias(d.evidencias || []),
        _blocoLista("Conciliações", (d.conciliacoes || []).map((cc) =>
          el("p", { class: "text-sm font-bold py-2 border-b-2 border-gray-200 last:border-0" },
            `${formatoDataHora(cc.criado_em)} · ${cc.severidade_tecnica} · ${cc.status}`)),
        "Nenhuma conciliação."),
      );

      const avisos = el("div", {});
      const baixar = el("button", {
        type: "button",
        class: "touch-btn w-full bg-blue-600 text-white font-black rounded-xl border-4 border-black",
      }, "BAIXAR DOSSIÊ EM PDF");
      baixar.addEventListener("click", () => {
        protegerEnvio(baixar, async () => {
          try {
            const blob = await tentar(base, () => dossiePdf(base, pedidoId));
            const href = URL.createObjectURL(blob);
            const link = el("a", { href, download: `dossie-${d.pedido.numero}.pdf` });
            document.body.append(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(href);
            mostrarToast("Dossiê baixado.", "sucesso");
          } catch (e) {
            avisos.textContent = "";
            avisos.append(blocoErro(e.message || "Não gerou o PDF.", () => baixar.click()));
          }
        });
      });

      corpo.append(
        cartao(
          el("h3", { class: "text-base font-black uppercase mb-2" }, "Documento"),
          avisos,
          pode("exportar_dossie") ? baixar : el(
            "p",
            { class: "text-sm font-bold" },
            "Seu papel tem leitura, mas exportação de dossiê não está liberada para ele.",
          ),
          el(
            "p",
            { class: "text-xs font-bold text-gray-700 mt-3" },
            "O dossiê reúne os fatos e as assinaturas. Ele não é laudo pericial nem prova judicial por si só.",
          ),
        ),
      );
    } catch (e) {
      corpo.textContent = "";
      corpo.append(blocoErro(e.message || "Não carregou o dossiê.", carregar));
    }
  }

  setTimeout(carregar, 0);
  return el("div", {}, corpo);
}

function _blocoLista(titulo_, itens, vazio) {
  return cartao(
    el("h3", { class: "text-base font-black uppercase mb-2" }, titulo_),
    ...(itens.length ? itens : [el("p", { class: "text-sm font-bold text-gray-700" }, vazio)]),
  );
}

function _blocoEvidencias(evidencias) {
  if (!evidencias.length) {
    return _blocoLista("Evidências", [], "Nenhuma foto registrada.");
  }
  return cartao(
    el("h3", { class: "text-base font-black uppercase mb-2" }, `Evidências (${evidencias.length})`),
    el(
      "p",
      { class: "text-xs font-bold text-gray-700 mb-2" },
      "Cada foto tem o hash do arquivo. Hash diferente = arquivo diferente.",
    ),
    ...evidencias.map((e) => el(
      "div",
      { class: "py-2 border-b-2 border-gray-200 last:border-0" },
      el(
        "div",
        { class: "flex items-center justify-between gap-2" },
        el("span", { class: "text-sm font-black uppercase" }, `${e.tipo} · ${e.origem}`),
        el("span", { class: "text-xs font-bold text-gray-700" }, formatoDataHora(e.recebida_em)),
      ),
      el("p", { class: "text-[10px] font-mono break-all mt-1" }, `sha256 ${String(e.sha256).slice(0, 32)}…`),
      e.sinalizacao_fraude
        ? el("p", { class: "text-xs font-black text-red-800 mt-1" }, "Sinalização de fraude neste arquivo.")
        : null,
    )),
  );
}
