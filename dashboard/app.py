"""
SteelSpy — Dashboard de economia & conformidade (Streamlit).

Métricas: volume em metros (estimado), taxa de itens conformes, divergências por bitola,
série temporal de NF-e. Não substitui ERP; apoia decisão no canteiro.

Execução (raiz do repo):
  set PYTHONPATH=backend
  streamlit run dashboard/app.py

Requer DATABASE_URL (igual à API) e, opcionalmente, DASHBOARD_PASSWORD.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.metros import metros_do_item
from dashboard.queries import carregar_nfes_resumo, carregar_nfe_itens_periodo, get_engine, listar_obras


@st.cache_data(ttl=300, show_spinner="Obras…")
def _cached_listar_obras(database_url: str):
    return listar_obras(get_engine(database_url))


@st.cache_data(ttl=120, show_spinner="Itens…")
def _cached_nfe_itens(database_url: str, obra_id: str, d0_iso: str, d1_iso: str):
    return carregar_nfe_itens_periodo(
        get_engine(database_url),
        obra_id=obra_id,
        d0=date.fromisoformat(d0_iso),
        d1=date.fromisoformat(d1_iso),
    )


@st.cache_data(ttl=120, show_spinner="NF-e…")
def _cached_nfes_resumo(database_url: str, obra_id: str, d0_iso: str, d1_iso: str):
    return carregar_nfes_resumo(
        get_engine(database_url),
        obra_id=obra_id,
        d0=date.fromisoformat(d0_iso),
        d1=date.fromisoformat(d1_iso),
    )


def _check_password() -> bool:
    pwd = os.getenv("DASHBOARD_PASSWORD", "").strip()
    if not pwd:
        return True
    if st.session_state.get("_auth_ok"):
        return True
    st.title("SteelSpy — Acesso")
    secret = st.text_input("Senha do dashboard", type="password")
    if st.button("Entrar"):
        ok = hmac.compare_digest(
            hashlib.sha256(secret.encode()).digest(),
            hashlib.sha256(pwd.encode()).digest(),
        )
        if ok:
            st.session_state._auth_ok = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    return False


def _adicionar_metros_est(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["metros_est"] = out.apply(
        lambda r: metros_do_item(
            {
                "bitola_recebida": r.get("bitola_recebida"),
                "quantidade_recebida": r.get("quantidade_recebida"),
                "unidade_recebida": r.get("unidade_recebida"),
            }
        ),
        axis=1,
    )
    return out


def _kpi_row(df_itens: pd.DataFrame) -> None:
    if df_itens.empty:
        st.info("Sem itens no período (ou só NF-e PENDENTE).")
        return

    total = len(df_itens)
    verde = (df_itens["status_item"] == "VERDE").sum()
    taxa = verde / total if total else 0.0

    m_ok = df_itens.loc[df_itens["status_item"] == "VERDE", "metros_est"].sum()
    m_all = df_itens["metros_est"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Itens analisados", f"{total}")
    c2.metric("Taxa itens VERDE", f"{taxa * 100:.1f}%", help="Itens em conformidade / total de linhas")
    c3.metric("Metros (VERDE, est.)", f"{m_ok:,.2f} m".replace(",", " "))
    c4.metric("Metros (total NF, est.)", f"{m_all:,.2f} m".replace(",", " "))


def main() -> None:
    st.set_page_config(
        page_title="SteelSpy — Economia",
        layout="wide",
        page_icon="📊",
        initial_sidebar_state="expanded",
    )

    if not _check_password():
        return

    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        st.error("Defina `DATABASE_URL` no ambiente (mesma string da API).")
        st.stop()

    st.sidebar.title("Filtros")
    obras = _cached_listar_obras(db_url)
    if obras.empty:
        st.warning("Nenhuma obra no banco.")
        st.stop()

    nome_por_id = dict(zip(obras["obra_id"], obras["nome"]))
    obra_sel = st.sidebar.selectbox(
        "Obra",
        options=obras["obra_id"].tolist(),
        format_func=lambda x: f"{nome_por_id.get(x, x)[:48]}",
    )

    hoje = date.today()
    col_a, col_b = st.sidebar.columns(2)
    with col_a:
        d0 = st.date_input("De", value=hoje - timedelta(days=30), max_value=hoje)
    with col_b:
        d1 = st.date_input("Até", value=hoje, max_value=hoje)

    if d0 > d1:
        st.error("Intervalo inválido.")
        st.stop()

    st.title("Economia & conformidade")
    st.caption(
        "Volume em metros é estimado a partir de quantidade × unidade (kg→m via tabela ABNT no núcleo conferente). "
        "Valores são indicativos para priorização, não custo financeiro."
    )

    d0s, d1s = d0.isoformat(), d1.isoformat()
    df_itens = _cached_nfe_itens(db_url, obra_sel, d0s, d1s)
    df_itens = _adicionar_metros_est(df_itens)
    df_nf = _cached_nfes_resumo(db_url, obra_sel, d0s, d1s)

    _kpi_row(df_itens)

    st.subheader("Distribuição por status (itens)")
    if not df_itens.empty:
        cnt = df_itens["status_item"].value_counts().reset_index()
        cnt.columns = ["status", "qtd"]
        fig_bar = px.bar(
            cnt,
            x="status",
            y="qtd",
            color="status",
            color_discrete_map={
                "VERDE": "#15803d",
                "AMARELO": "#ca8a04",
                "VERMELHO": "#b91c1c",
            },
            text="qtd",
        )
        fig_bar.update_layout(showlegend=False, height=360, yaxis_title="Linhas de item")
        st.plotly_chart(fig_bar, use_container_width=True)

        st.subheader("Conformidade por bitola (mm)")
        sub = (
            df_itens.groupby(["bitola_recebida", "status_item"], dropna=False)
            .size()
            .reset_index(name="qtd")
        )
        sub["bitola_recebida"] = sub["bitola_recebida"].fillna(0).astype(float)
        fig_stack = px.bar(
            sub,
            x="bitola_recebida",
            y="qtd",
            color="status_item",
            barmode="stack",
            color_discrete_map={
                "VERDE": "#15803d",
                "AMARELO": "#ca8a04",
                "VERMELHO": "#b91c1c",
            },
        )
        fig_stack.update_layout(height=400, xaxis_title="Bitola (mm)", legend_title="Status")
        st.plotly_chart(fig_stack, use_container_width=True)

        gap = df_itens.dropna(subset=["qtd_planejada_metros"])
        gap = gap[pd.to_numeric(gap["qtd_planejada_metros"], errors="coerce").fillna(0) > 0]
        if not gap.empty:
            gap = gap.copy()
            gap["delta_m"] = pd.to_numeric(gap["metros_est"], errors="coerce").fillna(0) - pd.to_numeric(
                gap["qtd_planejada_metros"], errors="coerce"
            )
            st.subheader("Economia de volume: planejado × recebido (metros)")
            st.caption("Cada ponto é uma linha de item com especificação vinculada. Útil para ver excesso/falta.")
            fig_gap = px.scatter(
                gap,
                x="qtd_planejada_metros",
                y="metros_est",
                color="status_item",
                hover_data=["chave_acesso", "bitola_recebida", "marca_recebida"],
                labels={
                    "qtd_planejada_metros": "Planejado na especificação (m)",
                    "metros_est": "Recebido na NF (est., m)",
                },
                color_discrete_map={
                    "VERDE": "#15803d",
                    "AMARELO": "#ca8a04",
                    "VERMELHO": "#b91c1c",
                },
            )
            max_ax = float(
                max(
                    gap["qtd_planejada_metros"].max() or 0,
                    gap["metros_est"].max() or 0,
                    1.0,
                )
            )
            fig_gap.add_shape(
                type="line",
                x0=0,
                y0=0,
                x1=max_ax,
                y1=max_ax,
                line=dict(dash="dash", color="rgba(248,250,252,0.35)"),
            )
            fig_gap.update_layout(height=420)
            st.plotly_chart(fig_gap, use_container_width=True)

        st.subheader("Volume estimado (m) × status")
        vol = df_itens.groupby("status_item")["metros_est"].sum().reset_index()
        vol = vol.dropna(subset=["metros_est"])
        vol = vol[vol["metros_est"] > 0]
        if not vol.empty:
            fig_vol = px.pie(
                vol,
                names="status_item",
                values="metros_est",
                hole=0.35,
                color="status_item",
                color_discrete_map={
                    "VERDE": "#15803d",
                    "AMARELO": "#ca8a04",
                    "VERMELHO": "#b91c1c",
                },
            )
            fig_vol.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig_vol, use_container_width=True)

    st.subheader("NF-e no período")
    if df_nf.empty:
        st.caption("Nenhuma NF concluída no intervalo.")
    else:
        df_nf["dia"] = pd.to_datetime(df_nf["processado_em"], utc=True).dt.date
        ts = df_nf.groupby("dia").size().reset_index(name="n_nf")
        fig_line = px.line(ts, x="dia", y="n_nf", markers=True, title="Volume diário de NF-e processadas")
        fig_line.update_layout(height=320, yaxis_title="NF-e", xaxis_title="Dia (UTC)")
        st.plotly_chart(fig_line, use_container_width=True)

        show = df_nf[
            ["chave_acesso", "processado_em", "status_conferencia", "tipo", "resumo_global"]
        ].head(200)
        st.dataframe(show, use_container_width=True, hide_index=True)

    if not df_itens.empty:
        csv = df_itens.to_csv(index=False, sep=";").encode("utf-8-sig")
        st.download_button(
            "Baixar itens (CSV)",
            data=csv,
            file_name=f"steelspy_itens_{obra_sel[:8]}_{d0}_{d1}.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
