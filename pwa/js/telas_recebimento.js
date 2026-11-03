/**
 * Telas de campo: registrar recebimento e fotografar a carga.
 *
 * Estas são as duas telas que alguém usa com luva, no portão, sob sol. Por isso:
 * botão grande, uma decisão por tela, e nada de "pronto" antes do servidor dizer
 * pronto. Cada foto carrega com chave de idempotência própria — se a rede do
 * canteiro cair no meio do upload, o reenvio não cria duas evidências.
 */

import { abrirRecebimento, enviarEvidencia, listarEvidencias } from "./api.js";
import {
  blocoErro,
  cartao,
  carregando,
  el,
  estadoVazio,
  formatoDataHora,
  mostrarToast,
  protegerEnvio,
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

// ---------------------------------------------------------------------------
// Registrar recebimento
// ---------------------------------------------------------------------------

export function telaRecebimento(base) {
  const obra = obraDaTela();
  // Uma chave por abertura de tela. Reenviar depois de falha de rede é tratado
  // como retry pelo servidor, não como segunda carga.
  const idCliente = uuid4();

  const tipo = el("select", {
    class: "w-full p-4 mb-3 border-4 border-black rounded-lg text-base font-bold",
  }, ...TIPO_TIPOS.map(([valor, rotulo]) => el("option", { value: valor }, rotulo)));

  const obs = el("textarea", {
    rows: "3", class: "w-full p-4 mb-3 border-4 border-black rounded-lg text-base font-bold",
    placeholder: "o que chegou, de qual caminhão, qualquer coisa fora do padrão",
  });

  const avisos = el("div", {});
  const botao = el("button", {
    type: "button",
    class: "touch-btn w-full bg-green-700 hover:bg-green-800 text-white font-black rounded-xl border-4 border-black",
  }, "ABRIR RECEBIMENTO");

  botao.addEventListener("click", () => {
    avisos.textContent = "";
    protegerEnvio(botao, async () => {
      try {
        const dados = await tentar(base, () =>
          abrirRecebimento(base, obra.id, {
            tipo: tipo.value,
            id_cliente: idCliente,
            observacoes: obs.value.trim() || null,
          }, csrf()),
        );
        mostrarToast(dados.criado ? "Recebimento aberto." : "Já existia — continuando.", "sucesso");
        irPara(`recebimento/${dados.id}/fotos`);
      } catch (e) {
        avisos.append(blocoErro(e.message || "Não abriu o recebimento.", () => botao.click()));
      }
    });
  });

  return el(
    "div",
    {},
    cartao(
      titulo("Registrar recebimento", "Abre a carga que acabou de entrar no portão."),
      el("label", { class: "block text-sm font-bold mb-1" }, "O que é?"),
      tipo,
      el("label", { class: "block text-sm font-bold mb-1" }, "Observações"),
      obs,
      avisos,
      botao,
    ),
    el(
      "p",
      { class: "text-sm font-bold text-center text-gray-700 px-2" },
      "Depois de abrir, fotografe o material. A foto é a prova; a nota é só a cobrança.",
    ),
  );
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

  setTimeout(carregar, 0);

  return el(
    "div",
    {},
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
