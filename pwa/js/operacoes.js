/**
 * Estado de cada operação de campo: pendente, confirmada ou falhou.
 *
 * O app não tem fila offline — e não finge ter. O que ele garante é que o
 * operador (e quem abrir a tela depois de um reload) saiba exatamente onde cada
 * envio parou. "Pendente" significa "toquei em enviar e o servidor ainda não
 * respondeu"; se a resposta se perdeu, o registro continua pendente até uma nova
 * tentativa — e a idempotência do servidor faz a repetição cair no mesmo
 * registro, não num segundo.
 *
 * O estado vive em `localStorage` (sobrevive a reload e a fechar o navegador).
 * Sem storage — aba privada, política do aparelho — cai para memória: a tela
 * continua honesta, só não sobrevive ao reload.
 */

export const STATUS = Object.freeze({
  PENDENTE: "pendente",
  CONFIRMADA: "confirmada",
  FALHOU: "falhou",
});

const CHAVE = "stellspy.operacoes";
const LIMITE_POR_OBRA = 25;

const ROTULOS = {
  pendente: "Pendente",
  confirmada: "Confirmada",
  falhou: "Falhou",
};

export function rotuloStatus(status) {
  return ROTULOS[status] || String(status || "—");
}

function _storagePadrao() {
  try {
    return globalThis.localStorage || null;
  } catch {
    return null;
  }
}

/**
 * @param {Storage|null} [storage]
 * @param {{agora?: () => Date}} [opcoes]
 */
export function criarOperacoes(storage = _storagePadrao(), { agora = () => new Date() } = {}) {
  const memoria = new Map();

  function _lerTudo() {
    if (!storage) return {};
    try {
      const bruto = storage.getItem(CHAVE);
      const dados = bruto ? JSON.parse(bruto) : {};
      return dados && typeof dados === "object" ? dados : {};
    } catch {
      return {}; // storage corrompido não pode derrubar a tela
    }
  }

  function _gravarTudo(dados) {
    if (!storage) return;
    try {
      storage.setItem(CHAVE, JSON.stringify(dados));
    } catch {
      /* cota cheia: o estado vive só na memória desta aba */
    }
  }

  function _lista(obraId) {
    const tudo = _lerTudo();
    const lista = tudo[obraId];
    if (Array.isArray(lista)) return lista;
    return memoria.get(obraId) || [];
  }

  function _salvar(obraId, lista) {
    memoria.set(obraId, lista);
    const tudo = _lerTudo();
    tudo[obraId] = lista;
    _gravarTudo(tudo);
  }

  function _atualizar(obraId, id, campos) {
    const lista = _lista(obraId);
    const i = lista.findIndex((op) => op.id === id);
    if (i < 0) return null;
    const atualizada = { ...lista[i], ...campos, atualizado_em: agora().toISOString() };
    const nova = [...lista];
    nova[i] = atualizada;
    _salvar(obraId, nova);
    return atualizada;
  }

  function registrar(obraId, { id, tipo, texto }) {
    const lista = _lista(obraId);
    const existente = lista.find((op) => op.id === id);
    if (existente) {
      // Mesma operação tentada de novo: mantém o registro e o horário original,
      // senão a tela perderia quando o envio começou.
      return _atualizar(obraId, id, { status: STATUS.PENDENTE, detalhe: null });
    }
    const registro = {
      id,
      tipo,
      texto: texto || tipo,
      status: STATUS.PENDENTE,
      criado_em: agora().toISOString(),
      atualizado_em: agora().toISOString(),
      detalhe: null,
    };
    const nova = [registro, ...lista]
      .sort((a, b) => String(b.criado_em).localeCompare(String(a.criado_em)))
      .slice(0, LIMITE_POR_OBRA);
    _salvar(obraId, nova);
    return registro;
  }

  function confirmar(obraId, id, detalhe = null) {
    return _atualizar(obraId, id, { status: STATUS.CONFIRMADA, detalhe });
  }

  function falhar(obraId, id, erro) {
    return _atualizar(obraId, id, {
      status: STATUS.FALHOU,
      detalhe: erro ? String(erro).slice(0, 300) : null,
    });
  }

  function listar(obraId) {
    return [..._lista(obraId)].sort((a, b) =>
      String(b.criado_em).localeCompare(String(a.criado_em)),
    );
  }

  function pendentes(obraId) {
    return listar(obraId).filter((op) => op.status === STATUS.PENDENTE);
  }

  function limpar(obraId) {
    memoria.delete(obraId);
    const tudo = _lerTudo();
    delete tudo[obraId];
    _gravarTudo(tudo);
  }

  return { registrar, confirmar, falhar, listar, pendentes, limpar };
}
