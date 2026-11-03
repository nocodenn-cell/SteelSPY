/**
 * Apenas URL pública da API — nunca armazene API key no cliente.
 * Em deploy, injete via JSON em #stellspy-config ou ajuste o template.
 */
export function getApiBaseUrl() {
  const el = document.getElementById("stellspy-config");
  if (!el?.textContent?.trim()) return "";
  try {
    const j = JSON.parse(el.textContent);
    return String(j.apiBaseUrl || "")
      .trim()
      .replace(/\/$/, "");
  } catch {
    return "";
  }
}
