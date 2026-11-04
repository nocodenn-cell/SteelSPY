/**
 * Rascunho do recebimento em aberto.
 *
 * O `id_cliente` é a chave que o servidor usa para não duplicar a carga. Se ele
 * se perder entre uma tentativa e outra, "tentar de novo" vira uma segunda
 * entrada — e no portão isso significa material contado duas vezes.
 *
 * Fica em `localStorage` porque a falha real não é só o reload: é o operador
 * fechar o navegador atrás do caminhão, voltar dez minutos depois e registrar a
 * mesma carga. O rascunho expira (4 h por padrão) para não reaproveitar a chave
 * numa entrega de outro turno; passou do prazo, a próxima entrada nasce com id
 * novo. Depois da resposta do servidor, o rascunho é limpo.
 */

const CHAVE = "stellspy.recebimento_em_aberto";
const VALIDADE_PADRAO_MS = 4 * 60 * 60 * 1000;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function _storagePadrao() {
  try {
    return globalThis.localStorage || null;
  } catch {
    return null;
  }
}

/**
 * @param {Storage|null} [storage]
 * @param {{agora?: () => number, validadeMs?: number}} [opcoes]
 */
export function criarRascunho(
  storage = _storagePadrao(),
  { agora = () => Date.now(), validadeMs = VALIDADE_PADRAO_MS } = {},
) {
  const memoria = new Map();

  function _ler(obraId) {
    if (!storage) return memoria.get(obraId) || null;
    try {
      const bruto = storage.getItem(`${CHAVE}:${obraId}`);
      if (!bruto) return null;
      const dados = JSON.parse(bruto);
      return dados && typeof dados === "object" ? dados : null;
    } catch {
      return null;
    }
  }

  function _gravar(obraId, dados) {
    memoria.set(obraId, dados);
    if (!storage) return;
    try {
      storage.setItem(`${CHAVE}:${obraId}`, JSON.stringify(dados));
    } catch {
      /* sem storage: o rascunho vive só enquanto a aba estiver aberta. */
    }
  }

  function ler(obraId) {
    const dados = _ler(obraId);
    if (!dados || !UUID_RE.test(String(dados.id || ""))) return null;
    const criado = Number(dados.criado_em);
    if (!Number.isFinite(criado)) return null;
    // Tolerância de 60 s para relógio que anda um pouco para frente.
    if (criado > agora() + 60_000) return null;
    if (agora() - criado > validadeMs) return null;
    return String(dados.id);
  }

  function inicio(obraId) {
    if (!ler(obraId)) return null;
    return new Date(Number(_ler(obraId).criado_em));
  }

  function guardar(obraId, id) {
    if (!UUID_RE.test(String(id || ""))) return null;
    const dados = { id: String(id), criado_em: agora() };
    _gravar(obraId, dados);
    return dados;
  }

  function limpar(obraId) {
    memoria.delete(obraId);
    if (!storage) return;
    try {
      storage.removeItem(`${CHAVE}:${obraId}`);
    } catch {
      /* nada a limpar */
    }
  }

  return { ler, inicio, guardar, limpar };
}
