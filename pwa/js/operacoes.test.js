import { beforeEach, describe, expect, it } from "vitest";

import { STATUS, criarOperacoes } from "./operacoes.js";

const OBRA_A = "obra-a";
const OBRA_B = "obra-b";
const T0 = Date.parse("2026-11-04T12:00:00.000Z");

class MemoriaStorage {
  constructor() {
    this.dados = new Map();
  }
  getItem(chave) {
    return this.dados.has(chave) ? this.dados.get(chave) : null;
  }
  setItem(chave, valor) {
    this.dados.set(chave, String(valor));
  }
  removeItem(chave) {
    this.dados.delete(chave);
  }
}

describe("operacoes", () => {
  let storage;
  let relogio;
  let ops;

  beforeEach(() => {
    storage = new MemoriaStorage();
    relogio = T0;
    ops = criarOperacoes(storage, { agora: () => new Date(relogio) });
  });

  it("começa pendente e guarda o horário de início", () => {
    ops.registrar(OBRA_A, { id: "op-1", tipo: "recebimento", texto: "Entrada" });

    const [op] = ops.listar(OBRA_A);
    expect(op.status).toBe(STATUS.PENDENTE);
    expect(op.id).toBe("op-1");
    expect(op.criado_em).toBe("2026-11-04T12:00:00.000Z");
    expect(ops.pendentes(OBRA_A)).toHaveLength(1);
  });

  it("repetir a mesma operação não cria registro novo nem perde o início", () => {
    ops.registrar(OBRA_A, { id: "op-1", tipo: "recebimento", texto: "Entrada" });
    relogio += 60_000;
    ops.registrar(OBRA_A, { id: "op-1", tipo: "recebimento", texto: "Entrada" });

    expect(ops.listar(OBRA_A)).toHaveLength(1);
    const [op] = ops.listar(OBRA_A);
    expect(op.criado_em).toBe("2026-11-04T12:00:00.000Z");
    expect(op.atualizado_em).toBe("2026-11-04T12:01:00.000Z");
    expect(op.status).toBe(STATUS.PENDENTE);
  });

  it("confirmar registra o que o servidor devolveu", () => {
    ops.registrar(OBRA_A, { id: "op-1", tipo: "recebimento", texto: "Entrada" });
    relogio += 5_000;
    ops.confirmar(OBRA_A, "op-1", "Recebimento abc · Completo");

    const [op] = ops.listar(OBRA_A);
    expect(op.status).toBe(STATUS.CONFIRMADA);
    expect(op.detalhe).toBe("Recebimento abc · Completo");
    expect(ops.pendentes(OBRA_A)).toHaveLength(0);
  });

  it("falhar guarda o erro e permite tentar de novo", () => {
    ops.registrar(OBRA_A, { id: "op-1", tipo: "recebimento", texto: "Entrada" });
    ops.falhar(OBRA_A, "op-1", "Sem conexão com o servidor.");

    expect(ops.listar(OBRA_A)[0].status).toBe(STATUS.FALHOU);
    expect(ops.listar(OBRA_A)[0].detalhe).toMatch(/Sem conexão/);

    ops.registrar(OBRA_A, { id: "op-1", tipo: "recebimento", texto: "Entrada" });
    expect(ops.listar(OBRA_A)[0].status).toBe(STATUS.PENDENTE);
    expect(ops.listar(OBRA_A)[0].detalhe).toBeNull();
  });

  it("não mistura obras", () => {
    ops.registrar(OBRA_A, { id: "a", tipo: "foto", texto: "foto-a" });
    ops.registrar(OBRA_B, { id: "b", tipo: "foto", texto: "foto-b" });

    expect(ops.listar(OBRA_A).map((o) => o.id)).toEqual(["a"]);
    expect(ops.listar(OBRA_B).map((o) => o.id)).toEqual(["b"]);
  });

  it("sobrevive a recarregar a página (nova instância, mesmo storage)", () => {
    ops.registrar(OBRA_A, { id: "op-1", tipo: "recebimento", texto: "Entrada" });

    const depoisDoReload = criarOperacoes(storage, { agora: () => new Date(relogio) });
    const [op] = depoisDoReload.listar(OBRA_A);
    expect(op.id).toBe("op-1");
    expect(op.status).toBe(STATUS.PENDENTE);
    expect(depoisDoReload.pendentes(OBRA_A)).toHaveLength(1);
  });

  it("storage corrompido devolve lista vazia em vez de derrubar a tela", () => {
    storage.setItem("stellspy.operacoes", "{isso não é json");
    expect(ops.listar(OBRA_A)).toEqual([]);

    ops.registrar(OBRA_A, { id: "op-1", tipo: "recebimento", texto: "Entrada" });
    expect(ops.listar(OBRA_A)).toHaveLength(1);
  });

  it("sem storage funciona em memória", () => {
    const semStorage = criarOperacoes(null, { agora: () => new Date(relogio) });
    semStorage.registrar(OBRA_A, { id: "op-1", tipo: "foto", texto: "foto" });

    expect(semStorage.listar(OBRA_A)).toHaveLength(1);
    expect(semStorage.pendentes(OBRA_A)).toHaveLength(1);
  });

  it("mantém no máximo 25 operações por obra, as mais recentes", () => {
    for (let i = 0; i < 30; i += 1) {
      relogio += 1_000;
      ops.registrar(OBRA_A, { id: `op-${i}`, tipo: "foto", texto: `foto ${i}` });
    }

    const lista = ops.listar(OBRA_A);
    expect(lista).toHaveLength(25);
    expect(lista[0].id).toBe("op-29");
    expect(lista.at(-1).id).toBe("op-5");
  });

  it("limpar apaga só a obra pedida", () => {
    ops.registrar(OBRA_A, { id: "a", tipo: "foto", texto: "a" });
    ops.registrar(OBRA_B, { id: "b", tipo: "foto", texto: "b" });

    ops.limpar(OBRA_A);

    expect(ops.listar(OBRA_A)).toEqual([]);
    expect(ops.listar(OBRA_B)).toHaveLength(1);
  });
});
