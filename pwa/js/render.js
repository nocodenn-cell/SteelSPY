import { fetchLaudoBlob } from "./api.js";

let toastTimeout = null;

/**
 * Toast simples (remove após ~4s). Tipos: erro | sucesso | info
 * @param {string} mensagem
 * @param {'erro'|'sucesso'|'info'} [tipo]
 */
export function mostrarToast(mensagem, tipo = "erro") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const cores = {
    erro: "bg-red-600",
    sucesso: "bg-green-600",
    info: "bg-blue-600",
  };

  const toast = document.createElement("div");
  toast.setAttribute("role", "status");
  toast.className = `${cores[tipo] || cores.erro} text-white px-4 py-2 rounded-lg shadow-lg mb-2 text-sm border-2 border-black max-w-[min(100vw-2rem,24rem)]`;
  toast.textContent = mensagem;

  container.appendChild(toast);

  if (toastTimeout) clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    toast.remove();
  }, 4000);
}

export function conclusaoItem(i) {
  return i["conclusão"] || i.conclusao || "—";
}

// ---------------------------------------------------------------------------
// Blocos do app operacional
//
// Tudo aqui constrói nós reais (createElement + textContent). `innerHTML` só
// aparece no renderizador antigo da conferência, que já escapa com escapeHtml.
// Dados de NF-e, pedido e foto vêm de fora e nunca entram como HTML.
// ---------------------------------------------------------------------------

/** @param {string} tag @param {object} [props] @param {(Node|string|Array)[]} [filhos] */
export function el(tag, props = {}, ...filhos) {
  const no = document.createElement(tag);
  for (const [chave, valor] of Object.entries(props)) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (chave === "class") no.className = valor;
    else if (chave === "dataset") Object.assign(no.dataset, valor);
    else if (chave === "hidden") no.hidden = !!valor;
    else if (chave.startsWith("on") && typeof valor === "function") {
      no.addEventListener(chave.slice(2), valor);
    } else no.setAttribute(chave, valor === true ? "" : valor);
  }
 for (const filho of filhos.flat(3)) {
    if (filho === null || filho === undefined || filho === false) continue;
    no.append(filho instanceof Node ? filho : document.createTextNode(String(filho)));
  }
  return no;
}

const SEVERIDADES = {
  VERDE: { cls: "status-verde", rotulo: "CONFORME" },
  AMARELO: { cls: "status-amarelo", rotulo: "ATENÇÃO" },
  VERMELHO: { cls: "status-vermelho", rotulo: "DIVERGENTE" },
  PENDENTE: { cls: "status-pendente", rotulo: "PENDENTE" },
};

export function badgeSeveridade(severidade) {
  const t = SEVERIDADES[String(severidade || "").toUpperCase()] || SEVERIDADES.PENDENTE;
  return el(
    "span",
    { class: `inline-block px-3 py-1 rounded-lg font-black text-sm border-4 border-black ${t.cls}` },
    t.rotulo,
  );
}

const STATUS_LINHA = {
  pendente: "Aguardando nota",
  parcial: "Parcial",
  completo: "Completo",
  divergente: "Divergente",
  revisao: "Precisa de revisão",
};

export function rotuloStatusLinha(status) {
  return STATUS_LINHA[status] || status || "—";
}

/**
 * Ciclo de vida da entrega e do pedido.
 *
 * Vocabulário separado de `STATUS_LINHA` de propósito: aqui "pendente" é "ainda
 * ninguém contou no portão", e na conciliação é "falta nota". Misturar os dois
 * faria a mesma palavra significar duas coisas na mesma tela.
 */
const ESTADOS = {
  pendente: { rotulo: "Sem contagem", cor: "PENDENTE" },
  aberto: { rotulo: "Aberto", cor: "PENDENTE" },
  parcial: { rotulo: "Entrega parcial", cor: "AMARELO" },
  completo: { rotulo: "Completou o pedido", cor: "VERDE" },
  atendido: { rotulo: "Atendido", cor: "VERDE" },
  divergente: { rotulo: "Divergente", cor: "VERMELHO" },
  encerrado: { rotulo: "Encerrado", cor: "VERDE" },
  cancelado: { rotulo: "Cancelado", cor: "PENDENTE" },
};

export function rotuloEstado(estado) {
  return (ESTADOS[estado] || { rotulo: estado || "—" }).rotulo;
}

export function badgeEstado(estado) {
  const e = ESTADOS[estado] || { rotulo: estado || "sem estado", cor: "PENDENTE" };
  const t = SEVERIDADES[e.cor];
  return el(
    "span",
    { class: `inline-block px-3 py-1 rounded-lg font-black text-sm border-4 border-black ${t.cls}` },
    String(e.rotulo).toUpperCase(),
  );
}

export function cartao(...conteudo) {
  return el(
    "section",
    { class: "bg-white p-5 rounded-xl border-4 border-black shadow-[4px_4px_0_#000] mb-5" },
    ...conteudo,
  );
}

export function titulo(texto, subtitulo) {
  return el(
    "div",
    { class: "mb-4" },
    el("h2", { class: "text-lg font-black uppercase" }, texto),
    subtitulo ? el("p", { class: "text-sm font-bold text-gray-700 mt-1" }, subtitulo) : null,
  );
}

export function carregando(texto = "Carregando…") {
  return el(
    "div",
    { class: "flex items-center justify-center gap-3 p-8 text-slate-700 font-bold", role: "status" },
    el("span", { class: "spinner", style: "border-top-color:currentColor;border-color:rgba(15,23,42,.25)", "aria-hidden": "true" }),
    texto,
  );
}

/**
 * Estado de erro com botão de repetir.
 *
 * Erro silencioso é o pior resultado possível num app de campo: o almoxarife
 * fecha a tela achando que não tinha nada. Toda falha oferece "tentar de novo".
 */
export function blocoErro(mensagem, onTentar) {
  return el(
    "div",
    { class: "p-4 bg-red-100 border-4 border-red-800 text-red-950 rounded-xl mb-4", role: "alert" },
    el("p", { class: "font-black mb-2" }, "Deu errado"),
    el("p", { class: "text-sm font-bold leading-snug" }, mensagem),
    onTentar
      ? el(
          "button",
          {
            type: "button",
            class: "touch-btn mt-3 w-full bg-red-800 text-white font-black rounded-xl border-4 border-black",
            onclick: onTentar,
          },
          "TENTAR DE NOVO",
        )
      : null,
  );
}

export function estadoVazio(titulo_, texto, acao) {
  return el(
    "div",
    { class: "p-6 bg-slate-100 border-4 border-dashed border-slate-400 rounded-xl text-center mb-4" },
    el("p", { class: "font-black text-base mb-1" }, titulo_),
    el("p", { class: "text-sm font-bold text-gray-700" }, texto),
    acao,
  );
}

export function campo(nome, valor, { vazio = "—" } = {}) {
  return el(
    "div",
    { class: "flex justify-between gap-3 py-2 border-b-2 border-gray-200 last:border-0" },
    el("span", { class: "text-sm font-bold text-gray-600 uppercase" }, nome),
    el("span", { class: "text-sm font-black text-right break-words" }, valor || vazio),
  );
}

export function formatoNumero(valor, { unidade = "", casas = 2 } = {}) {
  if (valor === null || valor === undefined || valor === "") return "—";
  const n = Number(valor);
  if (!Number.isFinite(n)) return String(valor);
  const milhar = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: casas });
  return `${milhar.format(n)}${unidade ? " " + unidade : ""}`;
}

export function formatoDataHora(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(d);
}

export function uuid4() {
  if (crypto && crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

/**
 * Protege envio duplo.
 *
 * Toque duplo em conexão ruim de canteiro é o caso real: dois toques gerariam
 * dois recebimentos. O botão desabilita antes da primeira awaited e só volta
 * depois que o backend respondeu — sucesso ou falha.
 */
export function protegerEnvio(botao, tarefa) {
  if (!botao || botao.disabled) return Promise.resolve(null);
  const rotuloOriginal = botao.textContent;
  botao.disabled = true;
  botao.textContent = "ENVIANDO…";
  return Promise.resolve()
    .then(tarefa)
    .finally(() => {
      botao.disabled = false;
      if (botao.isConnected) botao.textContent = rotuloOriginal;
    });
}

export function spinnerBotao(botao, texto) {
  botao.textContent = "";
  botao.append(el("span", { class: "spinner", "aria-hidden": "true" }), el("span", {}, texto));
  botao.classList.add("flex", "justify-center", "items-center", "gap-3");
}


/**
 * Resultado de uma conferência por chave de acesso.
 *
 * Escreve dentro de `container` (a tela decide onde o resultado aparece), então
 * trocar de rota não deixa resíduo da tela anterior. Os botões de PDF só
 * aparecem depois que o servidor devolveu um `nfe_log_id`: sem id, não há
 * documento a pedir.
 */
export function renderizarResultado(data, base, container) {
  const st = String(data.status || "PENDENTE").toUpperCase();
  const temas = {
    VERDE: { cls: "status-verde", icone: "✓", rotulo: "LIBERADO" },
    AMARELO: { cls: "status-amarelo", icone: "!", rotulo: "ATENÇÃO" },
    VERMELHO: { cls: "status-vermelho", icone: "✕", rotulo: "BLOQUEADO" },
    PENDENTE: { cls: "status-pendente", icone: "…", rotulo: "AGUARDANDO NOTA" },
  };
  const t = temas[st] || temas.PENDENTE;

  const descricao =
    st === "PENDENTE"
      ? data.mensagem || "A nota ainda não está disponível. Tente de novo em alguns minutos."
      : data.alerta || "Conferência concluída.";

  const r = data.resumo && typeof data.resumo === "object" ? data.resumo : null;
  const detalhes = data.detalhes || [];

  container.textContent = "";
  container.append(
    cartao(
      el(
        "div",
        { class: `rounded-xl p-6 text-center ${t.cls}` },
        el("p", { class: "text-4xl font-black leading-none" }, t.icone),
        el("p", { class: "text-xl font-black mt-2" }, t.rotulo),
        el("p", { class: "text-sm font-bold mt-2 leading-snug" }, descricao),
      ),
      typeof data.mensagem_fiscal === "string" && data.mensagem_fiscal.trim()
        ? el(
            "p",
            { class: "mt-4 p-3 bg-amber-100 border-4 border-amber-600 rounded-xl text-sm font-bold" },
            data.mensagem_fiscal.trim(),
          )
        : null,
      r
        ? el(
            "p",
            { class: "mt-4 text-sm font-bold text-gray-700" },
            `Itens: ${r.verdes || 0} ok · ${r.amarelos || 0} atenção · ${r.vermelhos || 0} crítico · ${r.total || 0} total`,
          )
        : null,
    ),
    cartao(
      el("h3", { class: "text-base font-black uppercase mb-2" }, "Item por item"),
      detalhes.length
        ? detalhes.map((i) => el(
            "div",
            { class: "flex flex-col gap-1 py-3 border-b-4 border-gray-200 last:border-0" },
            el("span", { class: "font-black text-base" }, String(i.item || "—")),
            el("span", { class: "text-xs font-bold uppercase text-gray-600" }, "Recebido / análise"),
            el("span", { class: "font-bold" }, conclusaoItem(i)),
          ))
        : el(
            "p",
            { class: "font-bold text-gray-800" },
            st === "PENDENTE" ? "Os itens aparecem quando a nota for obtida." : "Nenhum item retornado.",
          ),
    ),
  );

  if (st !== "PENDENTE" && data.nfe_log_id) {
    const avisos = el("div", {});
    const laudoRel = data.laudo_pdf || `/conferir/${data.nfe_log_id}/laudo.pdf`;
    const divRel = data.divergencias_pdf || `/conferir/${data.nfe_log_id}/divergencias.pdf`;
    container.append(
      cartao(
        el("h3", { class: "text-base font-black uppercase mb-2" }, "Documentos"),
        avisos,
        _botaoPdf(base, avisos, "LAUDO TÉCNICO (PDF)", `${base}${laudoRel}`),
        _botaoPdf(
          base,
          avisos,
          "DIVERGÊNCIAS (PDF)",
          `${base}${divRel}`,
          "bg-white text-black",
        ),
        el(
          "p",
          { class: "text-xs font-bold text-gray-700 mt-3" },
          "O PDF é gerado pelo servidor com os dados que ele tem. Baixe quando precisar provar.",
        ),
      ),
    );
  }
}

/** Botão de download que só confirma quando os bytes chegaram. */
function _botaoPdf(base, avisos, rotulo, url, cor = "bg-blue-600 hover:bg-blue-700 text-white") {
  const botao = el("button", {
    type: "button",
    class: `touch-btn w-full ${cor} font-black rounded-xl border-4 border-black mb-3`,
  }, rotulo);
  botao.addEventListener("click", () => {
    protegerEnvio(botao, async () => {
      botao.textContent = "BAIXANDO…";
      try {
        const blob = await fetchLaudoBlob(url);
        const nome = url.split("/").pop().split("?")[0] || "documento.pdf";
        const href = URL.createObjectURL(blob);
        const link = el("a", { href, download: nome });
        document.body.append(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(href);
        botao.textContent = rotulo;
        mostrarToast("Baixado.", "sucesso");
      } catch (e) {
        botao.textContent = rotulo;
        avisos.append(blocoErro(e.message || "Não baixou.", () => botao.click()));
      }
    });
  });
  return botao;
}
