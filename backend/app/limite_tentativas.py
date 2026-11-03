"""Limite de tentativas de login (por e-mail e por IP).

Problema que resolve: sem limite, um atacante testa senhas livremente. O scrypt
deixa cada tentativa cara, mas "cara" não é "impossível" — e o custo de CPU
também é um vetor de negação de serviço.

Implementação: janela deslizante em memória, por processo.

    LIMITE: no máximo N falhas dentro de uma janela de T segundos.
    Sucesso zera o contador daquela chave.

LIMITAÇÃO CONHECIDA E REGISTRADA
--------------------------------
O estado vive no processo. Com mais de um worker, cada um tem seu próprio
contador, então o limite efetivo é N × (nº de workers). Para produção
multi-instância, trocar o dicionário por Redis ou por uma tabela no Postgres —
a porta é o método `registrar_falha` / `bloqueado`, o chamador não muda.

Não é rate limit de borda (proteção contra volumetria bruta); é proteção
específica contra força bruta de credencial. As duas coisas são complementares.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

JANELA_PADRAO_SEGUNDOS = 300
MAX_FALHAS_PADRAO = 5
MAX_CHAVES = 10_000


def _env_int(nome: str, padrao: int, *, minimo: int = 1, maximo: int = 1000) -> int:
    bruto = (os.getenv(nome) or "").strip()
    if bruto.isdigit():
        return max(minimo, min(int(bruto), maximo))
    return padrao


def janela_segundos() -> int:
    return _env_int("AUTH_LOGIN_JANELA_SEGUNDOS", JANELA_PADRAO_SEGUNDOS, minimo=30, maximo=3600)


def max_falhas() -> int:
    return _env_int("AUTH_LOGIN_MAX_FALHAS", MAX_FALHAS_PADRAO, minimo=1, maximo=50)


class LimiteTentativas:
    """Janela deslizante de falhas por chave. Thread-safe."""

    def __init__(self) -> None:
        self._falhas: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _podar(self, chave: str, agora: float) -> deque[float]:
        fila = self._falhas[chave]
        limite = agora - janela_segundos()
        while fila and fila[0] < limite:
            fila.popleft()
        return fila

    def bloqueado(self, chave: str) -> tuple[bool, int]:
        """
        Retorna `(bloqueado, segundos_restantes)`.

        `segundos_restantes` é quanto falta para a tentativa mais antiga sair da
        janela — é o valor certo para o header `Retry-After`.
        """
        agora = time.monotonic()
        with self._lock:
            fila = self._podar(chave, agora)
            limite = max_falhas()
            if len(fila) < limite:
                return False, 0
            mais_antiga = fila[0]
            restante = int(max(1, (mais_antiga + janela_segundos()) - agora))
            return True, restante

    def registrar_falha(self, chave: str) -> None:
        agora = time.monotonic()
        with self._lock:
            # Poda defensiva: impede crescimento sem limite em ataque distribuído.
            if len(self._falhas) > MAX_CHAVES:
                self._falhas.clear()
            self._podar(chave, agora).append(agora)

    def limpar(self, chave: str) -> None:
        with self._lock:
            self._falhas.pop(chave, None)

    def resetar(self) -> None:
        with self._lock:
            self._falhas.clear()


_LIMITE = LimiteTentativas()


def limite() -> LimiteTentativas:
    return _LIMITE


def chave_login(email: str, ip: str | None) -> str:
    """
    Duas chaves independentes, avaliadas juntas:

    - por e-mail: impede ataque direcionado a uma conta;
    - por IP: impede varredura de muitas contas a partir do mesmo lugar.
    """
    return f"{(email or '').strip().lower()}|{(ip or 'sem-ip').strip()}"


def chave_email(email: str) -> str:
    return f"email:{(email or '').strip().lower()}"


def chave_ip(ip: str | None) -> str:
    return f"ip:{(ip or 'sem-ip').strip()}"
