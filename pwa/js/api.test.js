import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ErroApi,
  chamar,
  conferirNfe,
  enviarEvidencia,
  minhasObras,
} from "./api.js";

const BASE = "https://api.exemplo.test";

function resposta(corpo, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (typeof corpo === "string" ? corpo : JSON.stringify(corpo)),
    blob: async () => new Blob(["pdf"]),
  };
}

function ultimaChamada() {
  const [url, opcoes] = globalThis.fetch.mock.calls.at(-1);
  return { url: String(url), opcoes };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("chamar", () => {
  it("manda o CSRF em escrita e credencial de cookie", async () => {
    const fetchMock = vi.fn(async () => resposta({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await chamar(BASE, "/auth/logout", { method: "POST", csrf: "token-123" });

    const { opcoes } = ultimaChamada();
    expect(opcoes.credentials).toBe("include");
    expect(opcoes.headers["X-CSRF-Token"]).toBe("token-123");
  });

  it("não manda CSRF em leitura", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resposta({ itens: [] })));

    await chamar(BASE, "/auth/eu", { csrf: "token-123" });

    const { opcoes } = ultimaChamada();
    expect(opcoes.method).toBe("GET");
    expect(opcoes.headers).toBeUndefined();
  });

  it("serializa o corpo em JSON com Content-Type", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resposta({ ok: true })));

    await chamar(BASE, "/x", { method: "POST", corpo: { a: 1 } });

    const { opcoes } = ultimaChamada();
    expect(opcoes.headers["Content-Type"]).toBe("application/json");
    expect(opcoes.body).toBe('{"a":1}');
  });

  it("transforma falha de rede em erro claro, sem 'Failed to fetch'", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));

    const erro = await chamar(BASE, "/x").catch((e) => e);

    expect(erro).toBeInstanceOf(ErroApi);
    expect(erro.status).toBe(0);
    expect(erro.message).toContain("Sem conexão");
    expect(erro.message.toLowerCase()).not.toContain("failed to fetch");
  });

  it("usa o detail do servidor como mensagem do erro", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resposta({ detail: "obra não encontrada" }, 404)));

    const erro = await chamar(BASE, "/x").catch((e) => e);

    expect(erro.status).toBe(404);
    expect(erro.detail).toBe("obra não encontrada");
  });

  it("devolve blob quando o aceito é PDF", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resposta("ignorado")));

    const dados = await chamar(BASE, "/x", { aceito: "application/pdf" });

    expect(dados).toBeInstanceOf(Blob);
  });
});

describe("conferirNfe", () => {
  it("passa pelo cliente comum, com CSRF e sem chave de obra", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resposta({ status: "VERDE" })));

    await conferirNfe(BASE, "obra-1", "1".repeat(44), { csrf: "csrf-x" });

    const { url, opcoes } = ultimaChamada();
    expect(url).toBe(`${BASE}/conferir`);
    expect(opcoes.headers["X-CSRF-Token"]).toBe("csrf-x");
    expect(opcoes.headers["X-API-KEY"]).toBeUndefined();
    expect(JSON.parse(opcoes.body)).toEqual({ obra_id: "obra-1", chave_acesso: "1".repeat(44) });
  });

  it("mantém o fluxo legado por chave de obra", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resposta({ status: "PENDENTE" })));

    await conferirNfe(BASE, "obra-1", "2".repeat(44), { apiKey: "  alfa-123  " });

    const { opcoes } = ultimaChamada();
    expect(opcoes.headers["X-API-KEY"]).toBe("alfa-123");
    expect(opcoes.headers["X-CSRF-Token"]).toBeUndefined();
  });
});

describe("enviarEvidencia", () => {
  it("carrega idempotência, recebimento e metadados no formulário", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resposta({ id: "e1" }, 201)));
    const arquivo = new File([new Uint8Array([1, 2, 3])], "foto.jpg", {
      type: "image/jpeg",
      lastModified: 1700000000000,
    });

    await enviarEvidencia(
      BASE,
      "obra-1",
      {
        arquivo,
        tipo: "material",
        origem: "camera",
        recebimentoId: "rec-1",
        capturadaEm: "2026-11-04T10:00:00Z",
        chaveIdempotencia: "chave-1",
      },
      "csrf-x",
    );

    const { opcoes } = ultimaChamada();
    const form = opcoes.body;
    expect(form).toBeInstanceOf(FormData);
    expect(form.get("idempotency_key")).toBe("chave-1");
    expect(form.get("recebimento_id")).toBe("rec-1");
    expect(form.get("tipo")).toBe("material");
    expect(form.get("origem")).toBe("camera");
    expect(form.get("capturada_em")).toBe("2026-11-04T10:00:00Z");
    expect(form.get("arquivo").name).toBe("foto.jpg");
    // multipart: o browser precisa definir o boundary sozinho.
    expect(opcoes.headers?.["Content-Type"]).toBeUndefined();
    expect(opcoes.headers["X-CSRF-Token"]).toBe("csrf-x");
  });
});

describe("listagens", () => {
  it("desembrulha {itens} uma única vez", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resposta({ itens: [{ id: "o1" }] })));

    await expect(minhasObras(BASE)).resolves.toEqual([{ id: "o1" }]);
  });

  it("lista vazia quando o servidor não manda itens", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resposta({})));

    await expect(minhasObras(BASE)).resolves.toEqual([]);
  });
});
