"""
Processa um lote da fila de retentativa de XML (adequado a cron a cada 1–5 minutos).

    cd backend && python -m app.fila_worker_main
"""

from __future__ import annotations

import logging
import sys

from app.db import SessionLocal
from app.services.conferencia_persist import aplicar_xml_disponivel_fila
from app.services.fila_retentativa import processar_tick_fila
from app.services.nfe_io import buscar_xml_ou_json_por_chave
from app.services.whatsapp_evolution import notificar_xml_pendente


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    db = SessionLocal()
    try:
        resultados = processar_tick_fila(
            db,
            buscar_xml=buscar_xml_ou_json_por_chave,
            ao_sucesso=aplicar_xml_disponivel_fila,
            notificar_aguardando=notificar_xml_pendente,
        )
        for r in resultados:
            logging.info("%s", r)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
