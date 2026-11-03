/**
 * Telas de campo: registrar recebimento e fotografar a carga.
 *
 * Estas são as duas telas que alguém usa com luva, no portão, sob sol. Por isso:
 * botão grande, uma decisão por tela, e nada de "pronto" antes do servidor dizer
 * pronto. Cada foto carrega com chave de idempotência própria — se a rede do
 * canteiro cair no meio do upload, o reenvio não cria duas evidências.
 *
 * O registro da entrega conta linha por linha, porque "meio caminhão veio" é o
 * caso mais comum da obra. O estado (parcial, completo, divergente) vem do
 * servidor, calculado da quantidade; a tela mostra o que ele devolve.
 */

import {
  abrirRecebimento,
  encerrarRecebimento,
  obterPedido,
  obterRecebimento,
  enviarEvidencia,
  listarEvidencias,
  listarPedidos,
} from "./api.js";
import {
  badgeEstado,
  blocoErro,
  cartao,
  carregando,
  el,
  estadoVazio,
  formatoDataHora,
  formatoNumero,
  mostrarToast,
  protegerEnvio,
  rotuloEstado,
  titulo,
  uuid4,
} from "./render.js";
import { csrf, pode } from "./sessao.js";
import { irPara } from "./roteador.js";
import { obraDaTela, tentar } from "./telas_entrada.js";

const TIPOS_EVIDENCIA = [
  ["material", "O material (ferro, saco, bloco)"],
  ["etiqueta", "Etiqueta / identificação"],
  ["nfe", "Nota fiscal impressa"],
  ["lacre", "Lacre do veículo"],
  ["documento", "Outro documento"],
];

const CAMPO = "w-full p-4 mb-3 border-4 border-black rounded-lg text-base font-bold";

// ---------------------------------------------------------------------------
// Registrar recebimento
// ---------------------------------------------------------------------------

export function telaRecebimento(base) {
  const tela = el("div", {});
  // Cobertura por pedido, guardada para a tela de resultado conseguir dizer
  // "L1 · CA-50" em vez de um UUID que ninguém lê com luva.
  const coberturas = {};
  montarFormulario();
  return tela;

  function montarFormulario() {
    const obra = obraDaTela();
    // Uma chave por abertura de tela. Reenviar depois de falha de rede é tratado
    // como retry pelo servidor, não como segunda carga.
    const idCliente = uuid4();

    const tipo = el("select", { class: CAMPO },
      ...TIPO_TIPOS.map(([valor, rotulo]) => el("option", { value: valor }, rotulo)));

    const pedidoSel = el("select", { class: CAMPO },
      el("option", { value: "" }, "Sem pedido (só o carimbo do portão)"));

    const contagem = el("div", {});
    const avisos = el("div", {});

    const obs = el("textarea", {
      rows: "3", class: CAMPO,
      placeholder: "o que chegou, de qual caminhão, qualquer coisa fora do padrão",
    });

    const botao = el("button", {
      type: "button",
      class: "touch-btn w-full bg-green-700 hover:bg-green-800 text-white font-black rounded-xl border-4 border-black",
    }, "REGISTRAR ENTRADA");

    /**
     * Uma linha de contagem por linha do pedido, já com o saldo.
     *
     * Pré-cheio só na entrada: devolver é exceção, e um campo já cheio faria a
     * devolução do dia registrar o saldo inteiro como se tivesse voltado.
     */
    function pintarLinhas() {
      contagem.textContent = "";
      const cob = coberturas[pedidoSel.value];
      if (!cob) return;
      const preniu = tipo.value === "entrada";
      contagem.append(el("h4", { class: "text-sm font-black uppercase mt-2 mb-2" },
        "Quanto entrou de cada linha"));
      for (const l of cob) {
        const campo = el("input", {
          type: "text", inputmode: "decimal", class: CAMPO + " mb-1",
          value: preniu && l.saldo > 0 ? String(l.saldo) : "",
          placeholder: l.saldo > 0 ? `saldo ${formatoNumero(l.saldo)} ${l.unidade || ""}` : "0",
          dataset: { item: l.id, linha: String(l.linha) },
        });
        contagem.append(
          el("p", { class: "text-xs font-black uppercase text-gray-700" },
            `L${l.linha} · ${l.material_tipo} · pedido ${formatoNumero(l.quantidade)} ${l.unidade || ""} · ${rotuloEstado(l.status_recebimento)}`),
          campo,
        );
      }
    }

    pedidoSel.addEventListener("change", () => {
      if (!pedidoSel.value) { contagem.textContent = ""; return; }
      if (coberturas[pedidoSel.value]) { pintarLinhas(); return; }
      contagem.textContent = "";
      contagem.append(carregando("Carregando as linhas do pedido…"));
      tentar(base, () => obterPedido(base, pedidoSel.value, csrf()))
        .then((pedido) => {
          coberturas[pedido.id] = pedido.cobertura || [];
          pintarLinhas();
        })
        .catch((e) => {
          contagem.textContent = "";
          contagem.append(blocoErro(e.message || "Não carregou as linhas.", () => pedidoSel.dispatchEvent(new Event("change"))));
        });
    });
    tipo.addEventListener("change", pintarLinhas);

    function coletaItens() {
      const itens = [];
      for (const campo of contagem.querySelectorAll("input[data-item]")) {
        const texto = campo.value.trim().replace(",", ".");
        if (!texto) continue;
        const qtd = Number(texto);
        if (!Number.isFinite(qtd) || qtd <= 0) {
          throw new Error(`L${campo.dataset.linha}: informe uma quantidade maior que zero, ou deixe em branco.`);
        }
        itens.push({ pedido_item_id: campo.dataset.item, quantidade: qtd });
      }
      return itens;
    }

    botao.addEventListener("click", () => {
      avisos.textContent = "";
      let itens;
      try {
        itens = coletaItens();
      } catch (e) {
        avisos.append(blocoErro(e.message));
        return;
      }
      protegerEnvio(botao, async () => {
        try {
          const dados = await tentar(base, () =>
            abrirRecebimento(base, obra.id, {
              tipo: tipo.value,
              id_cliente: idCliente,
              observacoes: obs.value.trim() || null,
              pedido_id: pedidoSel.value || null,
              itens,
            }, csrf()),
          );
          if (!dados.criado) {
            // Retry de uma entrega que já entrou: o servidor tem o estado real.
            const detalhe = await tentar(base, () => obterRecebimento(base, dados.id, csrf()));
            mostrarToast("Já existia — mostrando o que o servidor tem.", "sucesso");
            montarResultado(detalhe);
            return;
          }
          mostrarToast(`Estado: ${rotuloEstado(dados.status)}.`, "sucesso");
          montarResultado(dados);
        } catch (e) {
          avisos.append(blocoErro(e.message || "Não abriu o recebimento.", () => botao.click()));
        }
      });
    });

    tela.textContent = "";
    tela.append(
      cartao(
        titulo("Registrar recebimento", "Abre a carga que acabou de entrar no portão."),
        el("label", { class: "block text-sm font-bold mb-1" }, "O que é?"),
        tipo,
        el("label", { class: "block text-sm font-bold mb-1" }, "Qual pedido esta carga atende?"),
        pedidoSel,
        contagem,
        el("label", { class: "block text-sm font-bold mb-1 mt-2" }, "Observações"),
        obs,
        avisos,
        botao,
      ),
      el(
        "p",
        { class: "text-sm font-bold text-center text-gray-700 px-2" },
        "Conte o que entrou, não o que a nota diz. A foto é a prova; a nota é só a cobrança.",
      ),
    );

    // Pedidos aptos a receber: qualquer pedido da obra. O servidor reconfere obra
    // e tenant quando a entrega é gravada.
    tentar(base, () => listarPedidos(base, obra.id, csrf()))
      .then((dados) => {
        pedidoSel.textContent = "";
        pedidoSel.append(el("option", { value: "" }, "Sem pedido (só o carimbo do portão)"));
        if (!dados.length) {
          pedidoSel.append(el("option", { value: "" }, "Nenhum pedido nesta obra"));
          return;
        }
        for (const p of dados) {
          pedidoSel.append(el("option", { value: p.id }, `Pedido ${p.numero} · ${rotuloEstado(p.status)}`));
        }
      })
      .catch(() => {
        pedidoSel.textContent = "";
        pedidoSel.append(el("option", { value: "" }, "Não foi possível listar os pedidos"));
        pedidoSel.disabled = true;
      });
  }

  /**
   * Resultado dito pelo servidor: o que ele decidiu que esta entrega é, e o que
   * sobra. Nada aqui é calculado no navegador — se a conta fosse aqui, duas
   * pessoas no portão poderiam ter dois estados diferentes para a mesma carga.
   */
  function montarResultado(dados) {
    // A resposta da gravação traz só {pedido_item_id, quantidade}; o nome da
    // linha vem da cobertura que a tela já tinha lido. O detalhe, por sua vez,
    // já vem do servidor com linha e unidade.
    const linhas = coberturas[dados.pedido_id] || [];
    const itens = (dados.contagem || dados.itens || []).map((i) => {
      const l = linhas.find((x) => x.id === i.pedido_item_id) || {};
      const rotulos = [`L${i.linha ?? l.linha ?? "?"}`];
      if (l.material_tipo) rotulos.push(l.material_tipo);
      rotulos.push(`${formatoNumero(i.quantidade)} ${i.unidade || l.unidade || ""}`.trim());
      return el("li", {}, rotulos.join(" · "));
    });

    const acoes = [
      el("button", {
        type: "button",
        class: "touch-btn w-full bg-blue-600 hover:bg-blue-700 text-white font-black rounded-xl border-4 border-black mb-3",
        onclick: () => irPara(`recebimento/${dados.id}/fotos`),
      }, "FOTOGRAFAR A CARGA"),
    ];
    if (dados.pedido_id) {
      acoes.push(el("button", {
        type: "button",
        class: "touch-btn w-full bg-white text-black font-black rounded-xl border-4 border-black mb-3",
        onclick: () => irPara(`pedido/${dados.pedido_id}`),
      }, "VER O SALDO DO PEDIDO"));
    }
    acoes.push(el("button", {
      type: "button",
      class: "touch-btn w-full bg-slate-900 text-white font-black rounded-xl border-4 border-black",
      onclick: montarFormulario,
    }, "REGISTRAR OUTRA ENTRADA"));

    const pedidoStatus = dados.pedido_status
      ? cartao(
          el("h3", { class: "text-base font-black uppercase mb-2" }, "Como o pedido ficou"),
          el("p", { class: "flex items-center gap-2 mb-2" }, badgeEstado(dados.pedido_status.status)),
          el("p", { class: "text-sm font-bold" }, dados.pedido_status.motivo || ""),
        )
      : null;

    tela.textContent = "";
    tela.append(
      cartao(
        titulo("Entrega registrada", `Recebido em ${formatoDataHora(dados.recebido_em)}`),
        el("p", { class: "flex items-center gap-2 mb-2" }, badgeEstado(dados.status)),
        el("p", { class: "text-sm font-bold mb-3" }, dados.motivo_status || ""),
        itens.length
          ? el("ul", { class: "text-xs font-bold text-gray-800 list-disc pl-5 mb-2" }, ...itens)
          : el("p", { class: "text-xs font-bold text-gray-700" }, "Sem contagem por linha nesta entrega."),
        ...acoes,
      ),
      pedidoStatus,
    );
  }
}


const TIPO_TIPOS = [
  ["entrada", "Entrada de material"],
  ["devolucao", "Devolução"],
  ["ajuste", "Ajuste de estoque"],
];

// ---------------------------------------------------------------------------
// Fotos da carga
// ---------------------------------------------------------------------------

export function telaFotos(base, recebimentoId) {
  const obra = obraDaTela();
  const lista = el("div", {}, carregando());
  const estadoEntrega = el("div", {});

  const seletorTipo = el("select", {
    class: "w-full p-4 mb-3 border-4 border-black rounded-lg text-base font-bold",
  }, ...TIPOS_EVIDENCIA.map(([valor, rotulo]) => el("option", { value: valor }, rotulo)));

  const avisos = el("div", {});

  const camera = el("input", {
    type: "file", accept: "image/*", capture: "environment",
    class: "hidden", id: "inCamera",
  });
  const galeria = el("input", { type: "file", accept: "image/*", multiple: true, class: "hidden", id: "inGaleria" });

  const btnCamera = el("button", {
    type: "button",
    class: "touch-btn w-full bg-blue-600 hover:bg-blue-700 text-white font-black rounded-xl border-4 border-black mb-3",
  }, "TIRAR FOTO");
  const btnGaleria = el("button", {
    type: "button",
    class: "touch-btn w-full bg-white text-black font-black rounded-xl border-4 border-black mb-3",
  }, "ESCOLHER DA GALERIA");

  btnCamera.addEventListener("click", () => camera.click());
  btnGaleria.addEventListener("click", () => galeria.click());
  camera.addEventListener("change", () => enviar(camera.files, "camera"));
  galeria.addEventListener("change", () => enviar(galeria.files, "galeria"));

  /**
   * Upload autenticado.
   *
   * `origem` vem de quem apertou o botão, mas o que vale é a resposta do
   * servidor: a lista só é tocada depois que cada arquivo voltou com id. Uma
   * falha no meio não derruba as demais — o lote continua e o que faltou fica
   * dito na tela.
   */
  async function enviar(arquivos, origem) {
    avisos.textContent = "";
    const nomes = Array.from(arquivos || []);
    if (!nomes.length) return;

    btnCamera.disabled = true;
    btnGaleria.disabled = true;
    let faltaram = 0;
    for (const [i, arquivo] of nomes.entries()) {
      btnCamera.textContent = `ENVIANDO ${i + 1} DE ${nomes.length}…`;
      try {
        await tentar(base, () =>
          enviarEvidencia(
            base,
            obra.id,
            {
              arquivo,
              tipo: seletorTipo.value,
              origem,
              recebimentoId,
              capturadaEm: new Date().toISOString(),
              chaveIdempotencia: uuid4(),
            },
            csrf(),
          ),
        );
      } catch (e) {
        faltaram += 1;
        avisos.append(blocoErro(`${arquivo.name || "foto"}: ${e.message || "não subiu."}`));
      }
    }
    btnCamera.disabled = false;
    btnGaleria.disabled = false;
    btnCamera.textContent = "TIRAR FOTO";
    camera.value = "";
    galeria.value = "";

    if (faltaram === 0) mostrarToast(`${nomes.length} foto(s) guardada(s).`, "sucesso");
    else mostrarToast(`${faltaram} de ${nomes.length} não subiu. Tente de novo.`, "erro");
    await carregar();
  }

  async function carregar() {
    lista.textContent = "";
    lista.append(carregando());
    try {
      const dados = await tentar(base, () => listarEvidencias(base, obra.id, recebimentoId, csrf()));
      lista.textContent = "";
      if (!dados.length) {
        lista.append(estadoVazio(
          "Nenhuma foto ainda",
          "Fotografe o material antes de descarregar. É a única prova de como chegou.",
        ));
        return;
      }
      for (const e of dados) {
        lista.append(_cartaoEvidencia(base, obra.id, e));
      }
    } catch (e) {
      lista.textContent = "";
      lista.append(blocoErro(e.message || "Não carregou as fotos.", carregar));
    }
  }

  /**
   * Estado da entrega, lido do servidor.
   *
   * A foto é o que se guarda; o estado é o que se decide. Mostrar aqui o que já
   * entrou, o que falta e quem encerrou evita a discussão no portão.
   */
  async function carregarEstado() {
    try {
      const d = await tentar(base, () => obterRecebimento(base, recebimentoId, csrf()));
      estadoEntrega.textContent = "";
      estadoEntrega.append(_cartaoEstadoEntrega(base, d, carregarEstado));
    } catch (e) {
      estadoEntrega.textContent = "";
      estadoEntrega.append(cartao(blocoErro(e.message || "Não mostrou o estado da entrega.", carregarEstado)));
    }
  }

  setTimeout(() => { carregar(); carregarEstado(); }, 0);

  return el(
    "div",
    {},
    estadoEntrega,
    cartao(
      titulo("Fotos da carga", "Escolha o que a foto mostra antes de enviar."),
      el("label", { class: "block text-sm font-bold mb-1" }, "A foto é de quê?"),
      seletorTipo,
      avisos,
      btnCamera,
      btnGaleria,
      camera,
      galeria,
      el(
        "p",
        { class: "text-xs font-bold text-gray-700" },
        "O servidor guarda o arquivo original e uma versão sem dados ocultos da câmera. Os dois ficam com você.",
      ),
    ),
    cartao(el("h3", { class: "text-base font-black uppercase mb-2" }, "O que já subiu"), lista),
    pode("ver_recebimento")
      ? el(
          "button",
          {
            type: "button",
            class: "touch-btn w-full bg-slate-900 text-white font-black rounded-xl border-4 border-black mb-3",
            onclick: () => irPara("historico"),
          },
          "VER TODOS OS RECEBIMENTOS",
        )
      : null,
    el(
      "button",
      {
        type: "button",
        class: "touch-btn w-full bg-white text-black font-black rounded-xl border-4 border-black",
        onclick: () => irPara("obra"),
      },
      "VOLTAR AO PAINEL",
    ),
  );
}

/**
 * Estado da entrega e, quando o papel permite, o botão que a fecha.
 *
 * `encerrado` é o único estado que nenhum cálculo produce: ele só aparece depois
 * que uma pessoa com a ação `encerrar_recebimento` escreve o motivo. Por isso o
 * campo de motivo não é opcional aqui, e por isso quem não tem a ação não vê o
 * botão — o servidor confere de novo, a tela só poupa o toque perdido.
 */
function _cartaoEstadoEntrega(base, d, aoMudar) {
  const blocos = [
    el("h3", { class: "text-base font-black uppercase mb-2" }, "Estado desta entrega"),
    el(
      "p",
      { class: "flex items-center gap-2 mb-2" },
      badgeEstado(d.status),
      el("span", { class: "text-xs font-bold text-gray-700" },
        d.pedido_numero ? `Pedido ${d.pedido_numero}` : "sem pedido vinculado"),
    ),
    d.motivo_status ? el("p", { class: "text-sm font-bold mb-2" }, d.motivo_status) : null,
    d.contagem.length
      ? el(
          "ul",
          { class: "text-xs font-bold text-gray-800 list-disc pl-5 mb-2" },
          ...d.contagem.map((c) => el(
            "li",
            {},
            `L${c.linha} · ${c.material_tipo} · ${formatoNumero(c.quantidade)} ${c.unidade || ""}`,
          )),
        )
      : el("p", { class: "text-xs font-bold text-gray-700 mb-2" }, "Sem contagem por linha nesta entrega."),
  ];

  if (d.status === "encerrado") {
    const encerramento = d.eventos.filter((e) => e.status_para === "encerrado").pop();
    blocos.push(el(
      "p",
      { class: "p-2 bg-slate-100 border-4 border-black rounded-lg text-xs font-bold" },
      encerramento
        ? `Encerrado em ${formatoDataHora(encerramento.criado_em)} por ${encerramento.autor_email || "—"}: ${encerramento.motivo || "sem motivo registrado"}`
        : "Encerrado.",
    ));
    return cartao(...blocos);
  }

  if (!pode("encerrar_recebimento")) {
    blocos.push(el(
      "p",
      { class: "text-xs font-bold text-gray-700" },
      "Fechar a entrega é decisão de engenharia ou administração; seu papel registra e fotografa.",
    ));
    return cartao(...blocos);
  }

  const motivo = el("textarea", {
    rows: "2", class: CAMPO,
    placeholder: "por que esta entrega está fechada? (ex.: o saldo chega amanhã, combinado com o fornecedor)",
  });
  const avisos = el("div", {});
  const botao = el("button", {
    type: "button",
    class: "touch-btn w-full bg-slate-900 text-white font-black rounded-xl border-4 border-black",
  }, "ENCERRAR ESTA ENTREGA");

  botao.addEventListener("click", () => {
    avisos.textContent = "";
    const texto = motivo.value.trim();
    if (texto.length < 5) {
      avisos.append(blocoErro("Escreva o motivo com uma frase — é o que a auditoria vai ler."));
      return;
    }
    protegerEnvio(botao, async () => {
      try {
        await tentar(base, () => encerrarRecebimento(base, d.id, texto, csrf()));
        mostrarToast("Entrega encerrada com a sua decisão.", "sucesso");
        await aoMudar();
      } catch (e) {
        avisos.append(blocoErro(e.message || "Não encerrou.", () => botao.click()));
      }
    });
  });

  blocos.push(
    el("h4", { class: "text-sm font-black uppercase mt-3 mb-2" }, "Encerrar"),
    avisos,
    motivo,
    botao,
  );
  return cartao(...blocos);
}

function _cartaoEvidencia(base, obraId, e) {
  const url = `${base}/evidencias/${e.id}/conteudo`;
  const original = `${url}?variante=original`;

  const miniatura = el("img", {
    src: url, alt: `evidência ${e.tipo}`, loading: "lazy",
    class: "w-full h-40 object-cover rounded-lg border-4 border-black mb-2",
  });
  // Foto quebrada é pior que lista sem foto: esconde que existe.
  miniatura.addEventListener("error", () => {
    miniatura.replaceWith(el(
      "p",
      { class: "text-xs font-bold text-red-800 mb-2" },
      "Miniatura não carregou — o arquivo continua no servidor.",
    ));
  });

  return el(
    "div",
    { class: "py-3 border-b-4 border-gray-200 last:border-0" },
    miniatura,
    el(
      "div",
      { class: "flex items-center justify-between gap-2" },
      el("span", { class: "text-sm font-black uppercase" }, `${e.tipo} · ${e.origem}`),
      el("span", { class: "text-xs font-bold text-gray-700" }, formatoDataHora(e.recebida_em)),
    ),
    el(
      "p",
      { class: "text-[10px] font-mono break-all mt-1 text-gray-700" },
      `sha256 ${String(e.sha256).slice(0, 24)}…`,
    ),
    el(
      "p",
      { class: "text-xs font-bold mt-1" },
      `${e.largura || "?"}×${e.altura || "?"} px · ${(e.bytes / 1024).toFixed(0)} KB`,
    ),
    e.sinalizacao_fraude
      ? el(
          "p",
          { class: "p-2 mt-2 bg-red-100 border-4 border-red-800 rounded-lg text-xs font-black" },
          "Esta imagem já apareceu em outro recebimento.",
        )
      : null,
    el(
      "a",
      {
        href: original,
        class: "inline-block mt-2 text-xs font-black text-blue-800 underline",
        target: "_blank",
        rel: "noopener",
      },
      "abrir arquivo original",
    ),
  );
}
