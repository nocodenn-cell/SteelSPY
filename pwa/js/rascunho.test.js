import { beforeEach, describe, expect, it } from "vitest";

import { criarRascunho } from "./rascunho.js";

const OBRA = "obra-a";
const OUTRA_OBRA = "obra-b";
const T0 = Date.parse("2026-11-04T12:00:00.000Z");
const ID = "11111111-2222-4333-8444-555555555555";

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

describe("rascunho", () => {
  let storage;
  let relogio;
  let rascunho;

  beforeEach(() => {
    storage = new MemoriaStorage();
    relogio = T0;
    rascunho = criarRascunho(storage, { agora: () => relogio });
  });

  it("guarda, lê e informa quando a entrada começou", () => {
    rascunho.guardar(OBRA, ID);

    expect(rascunho.ler(OBRA)).toBe(ID);
    expect(rascunho.inicio(OBRA).toISOString()).toBe("2026-11-04T12:00:00.000Z");
  });

  it("sobrevive a fechar o navegador (nova instância, mesmo localStorage)", () => {
    rascunho.guardar(OBRA, ID);

    const depoisDeReabrir = criarRascunho(storage, { agora: () => relogio });
    expect(depoisDeReabrir.ler(OBRA)).toBe(ID);
  });

  it("expira para não reaproveitar a chave em outro turno", () => {
    rascunho.guardar(OBRA, ID);
    relogio += 4 * 60 * 60 * 1000 + 1;

    expect(rascunho.ler(OBRA)).toBeNull();
  });

  it("ainda vale logo antes de expirar", () => {
    rascunho.guardar(OBRA, ID);
    relogio += 4 * 60 * 60 * 1000 - 1;

    expect(rascunho.ler(OBRA)).toBe(ID);
  });

  it("recusa id que não é UUID, na gravação e na leitura", () => {
    expect(rascunho.guardar(OBRA, "abc")).toBeNull();
    expect(rascunho.ler(OBRA)).toBeNull();

    storage.setItem(`${"stellspy.recebimento_em_aberto"}:${OBRA}`, JSON.stringify({ id: "abc", criado_em: relogio }));
    expect(rascunho.ler(OBRA)).toBeNull();
  });

  it("recusa data de criação no futuro além da tolerância de relógio", () => {
    storage.setItem(
      `stellspy.recebimento_em_aberto:${OBRA}`,
      JSON.stringify({ id: ID, criado_em: relogio + 5 * 60 * 1000 }),
    );
    expect(rascunho.ler(OBRA)).toBeNull();
  });

  it("storage corrompido não derruba a tela", () => {
    storage.setItem(`stellspy.recebimento_em_aberto:${OBRA}`, "não é json");
    expect(rascunho.ler(OBRA)).toBeNull();
  });

  it("limpar apaga só a obra pedida", () => {
    rascunho.guardar(OBRA, ID);
    rascunho.guardar(OUTRA_OBRA, ID);

    rascunho.limpar(OBRA);

    expect(rascunho.ler(OBRA)).toBeNull();
    expect(rascunho.ler(OUTRA_OBRA)).toBe(ID);
  });

  it("sem storage funciona em memória", () => {
    const semStorage = criarRascunho(null, { agora: () => relogio });
    semStorage.guardar(OBRA, ID);

    expect(semStorage.ler(OBRA)).toBe(ID);
    semStorage.limpar(OBRA);
    expect(semStorage.ler(OBRA)).toBeNull();
  });
});
