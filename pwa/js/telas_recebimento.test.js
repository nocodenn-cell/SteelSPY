import { describe, expect, it } from "vitest";

import { criarChavesDeEnvio } from "./telas_recebimento.js";

function arquivo(nome, tamanho, modificado) {
  return { name: nome, size: tamanho, lastModified: modificado };
}

describe("criarChavesDeEnvio", () => {
  it("devolve a mesma chave para o mesmo arquivo reenviado", () => {
    const chave = criarChavesDeEnvio();
    const foto = arquivo("carga.jpg", 2048, 1700000000000);

    expect(chave(foto)).toBe(chave(foto));
  });

  it("reconhece o retry mesmo com um File novo, de mesmos metadados", () => {
    const chave = criarChavesDeEnvio();

    expect(chave(arquivo("carga.jpg", 2048, 1700000000000))).toBe(
      chave(arquivo("carga.jpg", 2048, 1700000000000)),
    );
  });

  it("dá chaves diferentes a arquivos diferentes", () => {
    const chave = criarChavesDeEnvio();

    expect(chave(arquivo("a.jpg", 10, 1))).not.toBe(chave(arquivo("b.jpg", 10, 1)));
    expect(chave(arquivo("a.jpg", 11, 1))).not.toBe(chave(arquivo("a.jpg", 10, 1)));
  });

  it("não compartilha chaves entre telas/entregas distintas", () => {
    const entregaA = criarChavesDeEnvio();
    const entregaB = criarChavesDeEnvio();
    const foto = arquivo("carga.jpg", 2048, 1700000000000);

    // A mesma imagem em outra entrega é reutilização, não retry.
    expect(entregaA(foto)).not.toBe(entregaB(foto));
  });

  it("tolera arquivo sem nome/tamanho (captura crua)", () => {
    const chave = criarChavesDeEnvio();

    const primeira = chave({});
    expect(primeira).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
    expect(chave({})).toBe(primeira);
  });
});
