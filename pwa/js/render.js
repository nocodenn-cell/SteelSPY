let toastTimeout = null;

/**
 * Toast simples (remove após ~4s). Tipos: erro | sucesso | info
 * @param {string} mensagem
 * @param {'erro'|'sucesso'|'info'} [tipo]
 */
export function mostrarToast(mensagem, tipo = "erro") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const cores = {
    erro: "bg-red-600",
    sucesso: "bg-green-600",
    info: "bg-blue-600",
  };

  const toast = document.createElement("div");
  toast.setAttribute("role", "status");
  toast.className = `${cores[tipo] || cores.erro} text-white px-4 py-2 rounded-lg shadow-lg mb-2 text-sm border-2 border-black max-w-[min(100vw-2rem,24rem)]`;
  toast.textContent = mensagem;

  container.appendChild(toast);

  if (toastTimeout) clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    toast.remove();
  }, 4000);
}

export function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function conclusaoItem(i) {
  return i["conclusão"] || i.conclusao || "—";
}

export function onlyDigits(s) {
  return (s || "").replace(/\D/g, "");
}

export function renderizarResultado(data, base) {
  const area = document.getElementById("resultArea");
  const card = document.getElementById("statusCard");
  const icon = document.getElementById("statusIcon");
  const title = document.getElementById("statusTitle");
  const desc = document.getElementById("statusDesc");
  const resumoEl = document.getElementById("statusResumo");
  const details = document.getElementById("detailsArea");
  const btnPdf = document.getElementById("btnPdf");
  const btnPdfDiv = document.getElementById("btnPdfDiv");
  const pdfHint = document.getElementById("pdfHint");
  const msgFiscal = document.getElementById("statusMensagemFiscal");

  area.classList.remove("hidden");

  const st = (data.status || "PENDENTE").toUpperCase();
  const temas = {
    VERDE: { cls: "status-verde", icon: "✓", label: "LIBERADO" },
    AMARELO: { cls: "status-amarelo", icon: "!", label: "ATENÇÃO" },
    VERMELHO: { cls: "status-vermelho", icon: "✕", label: "BLOQUEADO" },
    PENDENTE: { cls: "status-pendente", icon: "…", label: "AGUARDANDO XML" },
  };
  const t = temas[st] || temas.PENDENTE;
  card.className = `status-card rounded-xl p-6 mb-4 text-center ${t.cls}`;

  icon.textContent = t.icon;
  title.textContent = t.label;
  const alerta = data.alerta || "";
  const msgPendente = data.mensagem || "";
  desc.textContent =
    st === "PENDENTE"
      ? msgPendente || "A nota ainda não está disponível na API. Tente de novo em alguns minutos."
      : alerta || "Conferência concluída.";

  if (msgFiscal) {
    const mf = data.mensagem_fiscal;
    if (typeof mf === "string" && mf.trim()) {
      msgFiscal.textContent = mf.trim();
      msgFiscal.classList.remove("hidden");
    } else {
      msgFiscal.textContent = "";
      msgFiscal.classList.add("hidden");
    }
  }

  if (data.resumo && typeof data.resumo === "object") {
    const r = data.resumo;
    resumoEl.textContent = `Itens: ${r.verdes || 0} ok · ${r.amarelos || 0} atenção · ${r.vermelhos || 0} crítico · ${r.total || 0} total`;
    resumoEl.classList.remove("hidden");
  } else {
    resumoEl.classList.add("hidden");
  }

  const detalhes = data.detalhes || [];
  if (detalhes.length === 0) {
    details.innerHTML =
      '<p class="font-bold text-gray-800">' +
      (st === "PENDENTE"
        ? "Itens aparecem após o XML ser obtido."
        : "Nenhum detalhe de linha retornado.") +
      "</p>";
  } else {
    details.innerHTML = detalhes
      .map(
        (i) => `
          <div class="flex flex-col gap-1 py-3 border-b-4 border-gray-200 last:border-0">
            <span class="font-black text-base">${escapeHtml(String(i.item || "—"))}</span>
            <span class="text-xs font-bold uppercase text-gray-600">Recebido / análise</span>
            <span class="font-bold">${escapeHtml(conclusaoItem(i))}</span>
          </div>`,
      )
      .join("");
  }

  let lastLaudoUrl = null;
  let lastDivergenciasUrl = null;
  if (st !== "PENDENTE" && data.nfe_log_id) {
    const rel = data.laudo_pdf || `/conferir/${data.nfe_log_id}/laudo.pdf`;
    lastLaudoUrl = rel.startsWith("http") ? rel : base + rel;
    const divRel =
      data.divergencias_pdf || `/conferir/${data.nfe_log_id}/divergencias.pdf`;
    lastDivergenciasUrl = divRel.startsWith("http") ? divRel : base + divRel;
    btnPdf.classList.remove("hidden");
    if (btnPdfDiv) btnPdfDiv.classList.remove("hidden");
    pdfHint.classList.remove("hidden");
  } else {
    btnPdf.classList.add("hidden");
    if (btnPdfDiv) btnPdfDiv.classList.add("hidden");
    pdfHint.classList.add("hidden");
  }

  return { lastLaudoUrl, lastDivergenciasUrl };
}
