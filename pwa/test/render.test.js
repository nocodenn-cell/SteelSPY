// B4 e M7: funções puras de render.js. Rodam em Node, sem DOM.
import { describe, expect, it } from "vitest";
import { conclusaoItem, valoresComparados } from "../js/render.js";

describe("valoresComparados (B4)", () => {
  it("expõe esperado e recebido do item da API", () => {
    const item = { item: "CA-50 10mm", esperado: "10 mm / GERDAU", recebido: "10 mm / GERDAU / 12 m" };
    expect(valoresComparados(item)).toEqual({
      esperado: "10 mm / GERDAU",
      recebido: "10 mm / GERDAU / 12 m",
    });
  });

  it("usa travessão quando a API não manda o campo", () => {
    expect(valoresComparados({ item: "X" })).toEqual({ esperado: "—", recebido: "—" });
  });

  it("trata texto vazio como ausente", () => {
    expect(valoresComparados({ esperado: "   ", recebido: "" })).toEqual({ esperado: "—", recebido: "—" });
  });
});

describe("conclusaoItem", () => {
  it("lê a chave ASCII 'conclusao'", () => {
    expect(conclusaoItem({ conclusao: "Conforme" })).toBe("Conforme");
  });

  it("aceita a chave legada acentuada durante a transição (B10)", () => {
    expect(conclusaoItem({ "conclusão": "Conforme" })).toBe("Conforme");
  });

  it("devolve travessão sem conclusão", () => {
    expect(conclusaoItem({})).toBe("—");
  });
});
