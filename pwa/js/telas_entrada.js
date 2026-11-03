/**
 * Telas de entrada: acesso, escolha de obra, painel, histórico e a conferência
 * por chave que já existia.
 *
 * Escolha de linguagem: quem usa isto no portão é almoxarife e fiscal, com luva,
 * sol e pressa. Nada de "entidade", "payload" ou "validação de integridade".
 * Fala-se do ferro, da nota e da foto.
 */

import { ErroApi, conferirNfe, listarRecebimentos } from "./api.js";
import {
  badgeSeveridade,
  blocoErro,
  cartao,
  carregando,
  el,
  estadoVazio,
  formatoDataHora,
  mostrarToast,
  protegerEnvio,
  renderizarResultado,
  titulo,
} from "./render.js";
import {
  comSessao,
  csrf,
  escolherObra,
  entrar,
  obraAtual,
  obras,
  recarregarObras,
  sair,
  usuario,
} from "./sessao.js";
import { irPara, renderizar } from "./roteador.js";

const LOGIN_SENHA_FRACA = 6;

/** 409 é "existem duas construtoras com esse e-mail" — aí a pessoa escolhe. */
function _precisaEscolherTenant(erro) {
  return erro instanceof ErroApi && erro.status === 409;
}

export function telaLogin(base) {
  const email = el("input", {
    type: "email", id: "inEmail", autocomplete: "username", inputmode: "email",
    class: "w-full p-4 mb-3 border-4 border-black rounded-lg text-base font-bold focus:outline-none focus:ring-4 focus:ring-blue-500",
    placeholder: "seu.email@trabalho",
  });
  const senha = el("input", {
    type: "password", id: "inSenha", autocomplete: "current-password",
    class: "w-full p-4 mb-3 border-4 border-black rounded-lg text-base font-bold focus:outline-none focus:ring-4 focus:ring-blue-500",
    placeholder: "sua senha",
  });
  const campoTenant = el("input", {
    type: "text", id: "inTenant", autocomplete: "organization",
    class: "hidden w-full p-4 mb-3 border-4 border-black rounded-lg text-base font-bold",
    placeholder: "código da construtora",
  });
  const rotuloTenant = el("label", {
    class: "hidden block text-sm font-bold mb-1", for: "inTenant",
  }, "Código da construtora");
  const erro = el("div", { id: "erroLogin" });
  const botao = el("button", {
    type: "button", id: "btnEntrar",
    class: "touch-btn w-full bg-blue-600 hover:bg-blue-700 text-white font-black rounded-xl border-4 border-black",
  }, "ENTRAR");

  async function submeter() {
    erro.textContent = "";
    if (!base) {
      erro.append(blocoErro("Configure apiBaseUrl no bloco #stellspy-config do index.html."));
      return;
    }
    if (!email.value.trim() || senha.value.length < LOGIN_SENHA_FRACA) {
      erro.append(blocoErro("Digite seu e-mail e sua senha completa."));
      return;
    }
    await protegerEnvio(botao, async () => {
      try {
        await entrar(base, email.value.trim(), senha.value, campoTenant.value.trim() || undefined);
        mostrarToast("Entrou.", "sucesso");
        location.hash = obras().length === 1 ? "#/obra" : "#/obras";
        renderizar();
      } catch (e) {
        if (e instanceof ErroApi && e.status === 409) {
          // O servidor devolve 409 sem listar as construtoras: dizer quais
          // existem seria confirmar que o e-mail pertence a outra empresa.
          campoTenant.classList.remove("hidden");
          rotuloTenant.classList.remove("hidden");
          erro.append(blocoErro(
            "Seu e-mail existe em mais de uma construtora. Digite o código da sua e tente de novo.",
          ));
          return;
        }
        if (e instanceof ErroApi && e.status === 429) {
          erro.append(blocoErro(e.message || "Muitas tentativas. Aguarde um pouco."));
          return;
        }
        erro.append(blocoErro(e.message || "Não entrou. Confira e-mail e senha."));
      }
    });
  }

  botao.addEventListener("click", submeter);
  senha.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") submeter();
  });

  return el(
    "div",
    {},
    cartao(
      titulo("Acesso", "Use o e-mail que a construtora cadastrou para você."),
      el("label", { class: "block text-sm font-bold mb-1", for: "inEmail" }, "E-mail"),
      email,
      el("label", { class: "block text-sm font-bold mb-1", for: "inSenha" }, "Senha"),
      senha,
      rotuloTenant,
      campoTenant,
      erro,
      botao,
    ),
    el(
      "p",
      { class: "text-sm font-bold text-center text-gray-700 px-2" },
      "Sua senha não fica salva neste aparelho. Quem libera cada ação é o servidor, toda vez.",
    ),
  );
}

export function telaObras(base) {
  const corpo = el("div", {}, carregando());

  function linha(obra) {
    return el(
      "button",
      {
        type: "button",
        class: "touch-btn w-full text-left bg-white hover:bg-gray-100 border-4 border-black rounded-xl mb-3 px-4 shadow-[4px_4px_0_#000]",
        onclick: () => {
          escolherObra(obra.id);
          irPara("obra");
        },
      },
      el("span", { class: "block font-black text-lg" }, obra.nome),
      el(
        "span",
        { class: "block text-sm font-bold text-gray-700 mt-1" },
        `Papel aqui: ${_nomePapel(obra.papel_na_obra)} · ${obra.acoes.length} ações liberadas`,
      ),
    );
  }

  async function carregar() {
    corpo.textContent = "";
    corpo.append(carregando());
    try {
      // A lista vem do servidor a cada entrada nesta tela: papel e ações são o
      // que o vínculo diz hoje, não o que o aparelho guardou ontem.
      await tentar(base, () => recarregarObras(base));
      const lista = obras();
      corpo.textContent = "";
      corpo.append(
        ...(lista.length
          ? lista.map(linha)
          : [estadoVazio("Nenhuma obra", "Peça ao administrador da construtora para vincular você a uma obra.")]),
      );
    } catch (e) {
      corpo.textContent = "";
      corpo.append(blocoErro(e.message || "Não carregou suas obras.", carregar));
    }
  }

  carregar();

  return el(
    "div",
    {},
    cartao(
      titulo("Onde você está?", "Escolha a obra. Você só vê obra em que tem vínculo."),
      corpo,
    ),
    el(
      "button",
      {
        type: "button",
        class: "touch-btn w-full bg-white text-black font-bold rounded-xl border-4 border-black text-sm",
        onclick: async () => { await sair(base); irPara("login"); },
      },
      "SAIR",
    ),
  );
}

function _nomePapel(papel) {
  return { engenheiro: "Engenharia", fiscal: "Fiscal do canteiro", auditor: "Auditoria (leitura)" }[papel] || papel;
}

export function telaPainel(base) {
  const obra = obraDaTela();
  const corpo = el("div", { id: "painelCorpo" }, carregando());

  async function carregar() {
    corpo.textContent = "";
    corpo.append(carregando());
    try {
      const rec = await tentar(base, () => listarRecebimentos(base, obra.id, csrf(), 5));
      corpo.textContent = "";
      corpo.append(resumoHoje(rec));
    } catch (e) {
      corpo.textContent = "";
      corpo.append(blocoErro(e.message || "Não carregou.", carregar));
    }
  }

  setTimeout(carregar, 0);

  return el(
    "div",
    {},
    cartao(
      titulo(`Obra: ${obra.nome}`, `Papel: ${_nomePapel(obra.papel_na_obra)}`),
      corpo,
    ),
    cartao(
      el("h3", { class: "text-base font-black uppercase mb-3" }, "O que fazer agora"),
      _menu(base),
    ),
  );
}

function resumoHoje(itens) {
  if (!itens.length) {
    return estadoVazio(
      "Nenhum recebimento ainda",
      "Assim que você registrar a primeira carga, ela aparece aqui.",
    );
  }
  const hoje = new Date().toDateString();
  const deHoje = itens.filter((r) => new Date(r.recebido_em).toDateString() === hoje);
  const fotos = itens.reduce((soma, r) => soma + r.total_evidencias, 0);

  return el(
    "div",
    {},
    el(
      "div",
      { class: "grid grid-cols-2 gap-3 mb-4" },
      _contador("Hoje", String(deHoje.length), "recebimentos"),
      _contador("Total", String(itens.length), `e ${fotos} fotos`),
    ),
    el("h3", { class: "text-sm font-black uppercase mb-2" }, "Últimos"),
    ...itens.slice(0, 3).map((r) => el(
      "div",
      { class: "flex items-center justify-between gap-2 py-2 border-b-2 border-gray-200 last:border-0" },
      el("span", { class: "text-sm font-bold" }, formatoDataHora(r.recebido_em)),
      el("span", { class: "text-xs font-black uppercase" }, `${r.total_evidencias} foto(s)`),
      badgeSeveridade(r.status === "conferido" ? "VERDE" : "PENDENTE"),
    )),
  );
}

function _contador(rotulo, valor, sub) {
  return el(
    "div",
    { class: "p-3 bg-slate-900 text-white rounded-xl border-4 border-black text-center" },
    el("p", { class: "text-3xl font-black leading-none" }, valor),
    el("p", { class: "text-xs font-bold uppercase mt-1" }, rotulo),
    el("p", { class: "text-xs font-bold opacity-80" }, sub),
  );
}

function _menu(base) {
  const obra = obraDaTela();
  const itens = [
    { rota: "recebimento", acao: "criar_recebimento", titulo: "Registrar recebimento", texto: "Abrir a carga que acabou de entrar." },
    { rota: "historico", acao: "ver_recebimento", titulo: "Histórico de recebimentos", texto: "O que já entrou nesta obra." },
    { rota: "pedidos", acao: "gerenciar_pedido", titulo: "Pedidos de compra", texto: "O que foi comprado e com qual fornecedor." },
    { rota: "nfe", acao: "ver_recebimento", titulo: "Notas fiscais (NF-e)", texto: "Buscar nota pelo código ou chave." },
    { rota: "conferir", acao: "ver_recebimento", titulo: "Conferir NF-e pela chave", texto: "Modo rápido: digite os 44 dígitos." },
    { rota: "dossies", acao: "exportar_dossie", titulo: "Dossiê", texto: "Prova completa de um pedido, em PDF." },
  ];

  // Item sem `acao` aparece sempre; com `acao`, só se o servidor liberou.
  // Esconder é conforto, não permissão: o servidor confere de novo em cada chamada.
  const visiveis = itens.filter((i) => !i.acao || obra.acoes.includes(i.acao));

  return el(
    "div",
    {},
    ...visiveis.map((i) => el(
      "button",
      {
        type: "button",
        class: "touch-btn w-full text-left bg-white hover:bg-gray-100 border-4 border-black rounded-xl mb-3 px-4",
        onclick: () => irPara(i.rota),
      },
      el("span", { class: "block font-black text-base" }, i.titulo),
      el("span", { class: "block text-xs font-bold text-gray-700" }, i.texto),
    )),
    visiveis.length === 0
      ? estadoVazio("Nada liberado", "Seu papel nesta obra não tem nenhuma das ações do menu.")
      : null,
  );
}

export function telaHistorico(base) {
  const obra = obraDaTela();
  const corpo = el("div", {}, carregando());

  async function carregar() {
    corpo.textContent = "";
    corpo.append(carregando());
    try {
      const dados = await tentar(base, () => listarRecebimentos(base, obra.id, csrf(), 50));
      corpo.textContent = "";
      if (!dados.length) {
        corpo.append(estadoVazio("Nenhum recebimento", "Esta obra ainda não registrou entrada de material."));
        return;
      }
      for (const r of dados) {
        corpo.append(el(
          "button",
          {
            type: "button",
            class: "w-full text-left bg-white border-4 border-black rounded-xl mb-3 p-4 shadow-[3px_3px_0_#000]",
            onclick: () => irPara(`recebimento/${r.id}/fotos`),
          },
          el(
            "div",
            { class: "flex items-center justify-between gap-2 mb-2" },
            el("span", { class: "font-black text-base" }, formatoDataHora(r.recebido_em)),
            badgeSeveridade(r.status === "conferido" ? "VERDE" : "PENDENTE"),
          ),
          el(
            "p",
            { class: "text-sm font-bold text-gray-700" },
            `${r.tipo} · ${r.total_evidencias} foto(s)${r.criado_por_nome ? " · por " + r.criado_por_nome : ""}`,
          ),
          r.observacoes ? el("p", { class: "text-sm font-bold mt-1" }, r.observacoes) : null,
        ));
      }
    } catch (e) {
      corpo.textContent = "";
      corpo.append(blocoErro(e.message || "Não carregou o histórico.", carregar));
    }
  }

  setTimeout(carregar, 0);
  return cartao(titulo("Histórico de recebimentos", "Toque em um para ver as fotos."), corpo);
}

/**
 * Tela de conferência por chave — o componente que já existia.
 *
 * Mantido separado do fluxo de pedido porque atende o caso "chegou uma nota que
 * ninguém abriu pedido": a conferência técnica acontece na hora, no portão.
 */
export function telaConferir(base) {
  const obra = obraDaTela();
  const chave = el("input", {
    type: "text", id: "inChave", inputmode: "numeric", maxlength: "54", autocomplete: "off",
    class: "field-key w-full p-4 mb-2 border-4 border-black rounded-lg focus:outline-none focus:ring-4 focus:ring-blue-500",
    placeholder: "44 dígitos da NF-e",
  });
  const contagem = el("p", { class: "text-sm font-bold mb-4" }, "0 / 44 dígitos");
  const resultado = el("div", { id: "resultadoConferir" });
  const erro = el("div", {});
  const botao = el("button", {
    type: "button",
    class: "touch-btn w-full bg-blue-600 text-white font-black rounded-xl border-4 border-black flex justify-center items-center gap-3",
  }, "CONFERIR MATERIAL");

  chave.addEventListener("input", () => {
    const so = chave.value.replace(/\D/g, "").slice(0, 44);
    chave.value = so.replace(/(.{4})/g, "$1 ").trim();
    contagem.textContent = `${so.length} / 44 dígitos`;
  });

  botao.addEventListener("click", () => {
    const digits = chave.value.replace(/\D/g, "");
    if (digits.length !== 44) {
      erro.textContent = "";
      erro.append(blocoErro("A chave da NF-e tem exatamente 44 dígitos."));
      return;
    }
    erro.textContent = "";
    protegerEnvio(botao, async () => {
      botao.textContent = "PROCESSANDO…";
      try {
        const dados = await conferirNfe(base, obra.id, digits);
        renderizarResultado(dados, base, resultado);
        mostrarToast(`Resultado: ${dados.status}`, dados.status === "VERDE" ? "sucesso" : "erro");
      } catch (e) {
        erro.append(blocoErro(e.message || "Não conectou. Verifique a rede.", () => botao.click()));
      }
    });
  });

  return el(
    "div",
    {},
    cartao(
      titulo("Conferir NF-e pela chave", "Comparece a nota contra a especificação da obra."),
      el("label", { class: "block text-sm font-bold mb-1", for: "inChave" }, "Chave de acesso"),
      chave,
      contagem,
      erro,
      botao,
    ),
    resultado,
  );
}

// ---------------------------------------------------------------------------
// Auxiliares compartilhados pelas telas
// ---------------------------------------------------------------------------

/** A obra escolhida. Toda tela operacional parte dela. */
export function obraDaTela() {
  const obra = obraAtual();
  if (!obra) {
    throw new Error("Escolha a obra primeiro.");
  }
  return obra;
}

/**
 * Executa a chamada autenticada. Se a sessão morreu no caminho, o roteador é
 * avisado e a pessoa volta para o login com o motivo dito — nenhuma tela trata
 * 401 sozinha, porque a resposta certa é sempre a mesma.
 */
export async function tentar(base, fn) {
  try {
    return await comSessao(base, fn);
  } catch (e) {
    if (e instanceof ErroApi && e.status === 401) {
      window.dispatchEvent(new CustomEvent("stellspy:401"));
    }
    throw e;
  }
}

export { el, cartao, titulo, carregando, blocoErro, estadoVazio, badgeSeveridade, formatoDataHora, protegerEnvio, mostrarToast, csrf };
