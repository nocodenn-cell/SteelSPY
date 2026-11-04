"""Prepara um Android físico para testar o PWA local, sem depender de nuvem.

O caminho de custo zero para a câmera funcionar é `localhost`: o navegador do
Android só libera `getUserMedia` e service worker em HTTPS **ou** em
`localhost`. `adb reverse` faz o celular enxergar o servidor desta máquina em
`localhost:8080` (PWA) e `localhost:8000` (API) — sem domínio, sem certificado.

O que este script faz:
  1. encontra o `adb` (PATH ou ANDROID_HOME/ANDROID_SDK_ROOT);
  2. lista dispositivos e recusa seguir com mais de um sem `--serial`;
  3. executa `adb reverse` para as duas portas;
  4. confere se o PWA e a API respondem nesta máquina;
  5. imprime o roteiro, sem marcar nada como aprovado.

O que ele NÃO faz: instalar SDK, mexer em aparelho, aprovar teste de câmera.
A aprovação de câmera e permissões só existe depois de execução humana no
aparelho — e isso fica pendente até acontecer.

Uso (a partir de `backend/`):

    ..\\.venv\\Scripts\\python.exe scripts\\preparar_android.py
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ADB_PADRAO = "adb"


def localizar_adb(
    explicito: str | None = None,
    ambiente: dict[str, str] | None = None,
    existe=Path.is_file,
) -> str | None:
    """
    Acha o executável do adb, nesta ordem: --adb, PATH, ANDROID_HOME, ANDROID_SDK_ROOT.

    Devolve None em vez de levantar: sem SDK instalado o teste simplesmente não
    roda, e quem chamou decide a mensagem.
    """
    ambiente = ambiente if ambiente is not None else os.environ
    if explicito:
        return explicito if existe(Path(explicito)) else None

    no_path = shutil.which(ADB_PADRAO)
    if no_path:
        return no_path

    for variavel in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        raiz = (ambiente.get(variavel) or "").strip()
        if not raiz:
            continue
        candidatos = [Path(raiz) / "platform-tools" / "adb", Path(raiz) / "platform-tools" / "adb.exe"]
        for candidato in candidatos:
            if existe(candidato):
                return str(candidato)
    return None


def interpretar_dispositivos(saida: str) -> dict[str, list[str]]:
    """
    Lê a saída de `adb devices`.

    Linhas com estado `device` estão prontas. `unauthorized` e `offline` são
    aparelhos que existem mas não servem — listar separado evita "não achou
    celular" quando o problema é o aviso de depuração não aceito na tela.
    """
    prontos: list[str] = []
    pendentes: list[str] = []
    for linha in (saida or "").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("List of devices") or linha.startswith("*"):
            continue
        partes = linha.split()
        if len(partes) < 2:
            continue
        serial, estado = partes[0], partes[1]
        if estado == "device":
            prontos.append(serial)
        else:
            pendentes.append(f"{serial} ({estado})")
    return {"prontos": prontos, "pendentes": pendentes}


def _executar(comando: list[str], timeout: float = 20.0) -> subprocess.CompletedProcess:
    return subprocess.run(comando, capture_output=True, text=True, timeout=timeout, check=False)


def _http_ok(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resposta:
            return True, f"HTTP {resposta.status}"
    except urllib.error.HTTPError as exc:  # respondeu, só não era 200
        return True, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - a mensagem importa mais que o tipo
        return False, f"{type(exc).__name__}: {exc}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Prepara Android via adb reverse para testar o PWA local.")
    p.add_argument("--adb", default=None, help="caminho do adb (default: PATH/ANDROID_HOME)")
    p.add_argument("--serial", default=None, help="serial do aparelho, quando há mais de um")
    p.add_argument("--porta-pwa", type=int, default=8080, help="porta local do PWA")
    p.add_argument("--porta-api", type=int, default=8000, help="porta local da API")
    args = p.parse_args(argv)

    adb = localizar_adb(args.adb)
    if adb is None:
        print("ADB NÃO ENCONTRADO.")
        print("")
        print("Instale as platform-tools do Android SDK (gratuito) ou instale o app")
        print("'Android Platform Tools' do gerenciador de pacotes da sua máquina.")
        print("Depois confirme que `adb version` funciona no terminal.")
        print("")
        print("Sem adb, ainda é possível testar no Android publicando o PWA em HTTPS")
        print("(exige domínio/certificado) — decisão de custo do proprietário.")
        return 2

    dispositivos = interpretar_dispositivos(_executar([adb, "devices"]).stdout)
    if not dispositivos["prontos"]:
        print("NENHUM APARELHO PRONTO.")
        if dispositivos["pendentes"]:
            print("Aparelhos vistos, mas não liberados:")
            for item in dispositivos["pendentes"]:
                print(f"  - {item}")
            print("Aceite o aviso 'Permitir depuração USB?' na tela do celular e repita.")
        else:
            print("Conecte o celular por USB e ative 'Depuração USB' nas opções de desenvolvedor.")
        return 3

    if args.serial:
        if args.serial not in dispositivos["prontos"]:
            print(f"Serial {args.serial!r} não está entre os aparelhos prontos: {dispositivos['prontos']}")
            return 3
        serial = args.serial
    elif len(dispositivos["prontos"]) > 1:
        print("Mais de um aparelho conectado; escolha um com --serial:")
        for item in dispositivos["prontos"]:
            print(f"  - {item}")
        return 3
    else:
        serial = dispositivos["prontos"][0]

    print(f"Aparelho: {serial}")
    falhou = False
    for porta in (args.porta_pwa, args.porta_api):
        resultado = _executar([adb, "-s", serial, "reverse", f"tcp:{porta}", f"tcp:{porta}"])
        if resultado.returncode == 0:
            print(f"  adb reverse tcp:{porta} -> tcp:{porta}  OK")
        else:
            falhou = True
            print(f"  adb reverse tcp:{porta} FALHOU: {resultado.stderr.strip()}")

    print("")
    ok_pwa, detalhe_pwa = _http_ok(f"http://127.0.0.1:{args.porta_pwa}/index.html")
    print(f"PWA nesta máquina (porta {args.porta_pwa}): {'responde' if ok_pwa else 'NÃO responde'} — {detalhe_pwa}")
    ok_api, detalhe_api = _http_ok(f"http://127.0.0.1:{args.porta_api}/openapi.json")
    print(f"API nesta máquina (porta {args.porta_api}): {'responde' if ok_api else 'NÃO responde'} — {detalhe_api}")
    if not ok_pwa:
        print("Suba o PWA com: python -m http.server 8080 --directory pwa")
    if not ok_api:
        print("Suba a API com DATABASE_URL do banco demo e PWA_COOKIE_SECURE=0 (ver roteiro).")

    print("")
    print("No celular, abra: http://localhost:%d" % args.porta_pwa)
    print("A câmera e o service worker funcionam nesse endereço por ser localhost.")
    print("")
    print("Este script NÃO aprova nada. O roteiro de validação física ainda precisa")
    print("ser executado no aparelho e registrado em docs/sprint6/ROTEIRO_VALIDACAO_FISICA.md.")

    return 0 if not falhou and ok_pwa and ok_api else 1


if __name__ == "__main__":
    sys.exit(main())
