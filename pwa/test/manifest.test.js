// B6: instalação do PWA exige ícones 192 e 512 com arquivo existente.
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const raiz = join(dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(readFileSync(join(raiz, "manifest.json"), "utf8"));

describe("manifest.json (B6)", () => {
  it.each(["192x192", "512x512"])("declara ícone %s com arquivo existente", (tamanho) => {
    const icone = (manifest.icons || []).find((i) => i.sizes === tamanho && i.type === "image/png");
    expect(icone, `falta ícone ${tamanho}`).toBeDefined();
    expect(existsSync(join(raiz, icone.src)), `arquivo ausente: ${icone.src}`).toBe(true);
  });
});
