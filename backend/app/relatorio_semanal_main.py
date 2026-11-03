"""

Job agendado: relatório CSV de NF-e conferidas + e-mail por obra.



Exemplo (cron semanal, domingo 06:00 UTC):

  cd backend && python -m app.relatorio_semanal_main



Variáveis: ver backend/.env.example (SMTP_*, RELATORIO_*).



RELATORIO_DRY_RUN=1 — gera CSV e loga sem enviar e-mail.

RELATORIO_FORCAR_REENVIO=1 — ignora idempotência (reenvia no mesmo dia).

RELATORIO_USAR_TZ_BR=1 — janela em dias corridos America/Sao_Paulo (chave idempotência por data BR).

"""



from __future__ import annotations



import logging

import os

import sys

from uuid import UUID



from app.db import SessionLocal

from app.services.email_smtp import destinatarios_globais_opcional, enviar_email_com_anexo

from app.services.relatorio_semanal import (

    atualizar_idempotencia_relatorio,

    corpo_email_pt,

    listar_logs_periodo_obra,

    montar_csv_bytes,

    nome_arquivo_csv,

    obras_com_relatorio_configurado,

    periodo_relatorio_job,

)



logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

logger = logging.getLogger(__name__)





def main() -> int:

    dry = os.getenv("RELATORIO_DRY_RUN", "").strip() == "1"

    forcar = os.getenv("RELATORIO_FORCAR_REENVIO", "").strip() == "1"

    inicio, fim, chave, etiqueta_tz = periodo_relatorio_job()

    copia = destinatarios_globais_opcional()



    db = SessionLocal()

    try:

        obras = obras_com_relatorio_configurado(db)

        if not obras:

            logger.info("Nenhuma obra com relatorio_email_destinos; nada a fazer.")

            return 0



        for ob in obras:

            obra_id = UUID(str(ob["id"]))

            destinos = [str(x).strip() for x in (ob.get("relatorio_email_destinos") or []) if str(x).strip()]

            if not destinos:

                continue



            ultima_chave = (ob.get("relatorio_ultimo_periodo_chave") or "").strip()

            if not forcar and ultima_chave == chave:

                logger.info(

                    "Relatório já enviado para esta chave (idempotência). obra=%s chave=%s — use RELATORIO_FORCAR_REENVIO=1 para repetir.",

                    ob.get("nome"),

                    chave,

                )

                continue



            linhas = listar_logs_periodo_obra(db, obra_id=obra_id, inicio_utc=inicio, fim_utc=fim)

            csv_bytes = montar_csv_bytes(linhas)

            fname = nome_arquivo_csv(obra_id, inicio, fim)

            obra_nome = str(ob.get("nome") or obra_id)



            if dry:

                logger.info(

                    "[DRY-RUN] obra=%s linhas=%s arquivo=%s bytes=%s destinos=%s bcc=%s chave=%s",

                    obra_nome,

                    len(linhas),

                    fname,

                    len(csv_bytes),

                    destinos,

                    copia,

                    chave,

                )

                continue



            assunto = (

                f"[SteelSpy] NF-e {obra_nome} — {inicio.date()} a {fim.date()} "

                f"({etiqueta_tz})"

            )

            corpo = corpo_email_pt(obra_nome, inicio, fim, len(linhas), etiqueta_tz=etiqueta_tz)



            try:

                enviar_email_com_anexo(

                    destinatarios=destinos,

                    assunto=assunto,

                    corpo_texto=corpo,

                    anexo_nome=fname,

                    anexo_bytes=csv_bytes,

                    copia_oculta=copia or None,

                )

            except Exception as e:  # noqa: BLE001

                logger.exception("Falha ao enviar relatório obra=%s: %s", obra_nome, e)

                continue



            atualizar_idempotencia_relatorio(db, obra_id, chave)

            logger.info("Relatório enviado obra=%s chave=%s", obra_nome, chave)



        return 0

    finally:

        db.close()





if __name__ == "__main__":

    sys.exit(main())

