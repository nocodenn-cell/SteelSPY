"""
API de auditoria: NF-e × especificação (aço/concreto).
"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as TimeoutDePool

from app.cors import configurar_cors
from app.routers import auth_pwa, auth_usuario, conferencia, evidencias, pedidos

logger = logging.getLogger(__name__)

app = FastAPI(title="stellSPY Auditoria NF-e", version="0.1.0")

try:
    configurar_cors(app, os.getenv("CORS_ALLOW_ORIGINS"))
except ValueError as exc:
    # Falhar no boot é melhor que servir CORS ambíguo: o erro aparece no deploy,
    # não quando um navegador recusa a sessão em campo.
    raise RuntimeError(f"CORS_ALLOW_ORIGINS inválido: {exc}") from exc

app.include_router(auth_pwa.router)
app.include_router(auth_usuario.router)
app.include_router(conferencia.router)
app.include_router(evidencias.router)
app.include_router(pedidos.router)


@app.exception_handler(OperationalError)
@app.exception_handler(InterfaceError)
@app.exception_handler(TimeoutDePool)
async def _banco_indisponivel(request: Request, exc: Exception) -> JSONResponse:
    """
    Indisponibilidade temporária de banco vira 503, não 500.

    O cliente recebe uma mensagem genérica e um `Retry-After`. Nada de SQL,
    string de conexão, host ou credencial — nem no corpo, nem no log.

    Só estes três tipos são tratados aqui: são falhas de *conexão*. `TimeoutDePool`
    entra com os outros porque é o que a fila de requisições vê quando o banco cai:
    as conexões do pool se esgotam esperando um servidor que não responde, e cada
    pedido seguinte morreria em 500 — o PWA concluiria que o app está quebrado,
    quando na verdade é o banco que está indisponível. Erro de integridade,
    violação de constraint ou bug de consulta continuam sendo 500 ou 4xx, porque
    não são "tente de novo em instantes" — mascará-los seria esconder defeito real.
    """
    logger.error(
        "banco indisponível em %s %s (%s)",
        request.method,
        request.url.path,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Serviço temporariamente indisponível. Tente novamente em instantes."},
        headers={"Retry-After": "5"},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
