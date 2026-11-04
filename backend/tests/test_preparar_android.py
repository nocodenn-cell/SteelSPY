"""Contrato do preparador de Android (adb reverse).

O script é a parte barata do teste físico: ele prepara o caminho de custo zero
(localhost via adb) e diz o que falta. Estes testes cobrem a leitura da saída do
adb e as recusas — nunca "aprovam" câmera, que depende de execução humana.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
from typing import Any

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]


def _carregar() -> Any:
    caminho = RAIZ / "scripts" / "preparar_android.py"
    spec = importlib.util.spec_from_file_location("_preparar_android", caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


preparar = _carregar()


def test_interpreta_device_pronto_e_pendentes() -> None:
    saida = (
        "List of devices attached\n"
        "R58M123ABC\tdevice\n"
        "emulator-5554\tunauthorized\n"
        "ZX1G22\t\toffline\n"
        "* daemon started successfully\n"
    )

    lido = preparar.interpretar_dispositivos(saida)

    assert lido["prontos"] == ["R58M123ABC"]
    assert lido["pendentes"] == ["emulator-5554 (unauthorized)", "ZX1G22 (offline)"]


def test_interpreta_saida_vazia() -> None:
    assert preparar.interpretar_dispositivos("List of devices attached\n") == {
        "prontos": [],
        "pendentes": [],
    }


def test_localizar_adb_por_caminho_explicito() -> None:
    assert preparar.localizar_adb("C:/sdk/platform-tools/adb.exe", existe=lambda p: True) == (
        "C:/sdk/platform-tools/adb.exe"
    )
    assert preparar.localizar_adb("C:/nao/existe/adb.exe", existe=lambda p: False) is None


def test_localizar_adb_pelo_android_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preparar.shutil, "which", lambda _: None)

    achado = preparar.localizar_adb(
        None,
        ambiente={"ANDROID_HOME": "C:/Android/Sdk"},
        existe=lambda p: str(p).replace("\\", "/").endswith("platform-tools/adb"),
    )

    assert achado is not None
    assert "platform-tools" in achado


def test_sem_adb_explica_e_sai_com_2(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setattr(preparar, "localizar_adb", lambda _: None)

    assert preparar.main([]) == 2
    saida = capsys.readouterr().out
    assert "ADB NÃO ENCONTRADO" in saida
    assert "HTTPS" in saida


def test_sem_aparelho_explica_e_sai_com_3(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setattr(preparar, "localizar_adb", lambda _: "adb")
    monkeypatch.setattr(
        preparar,
        "_executar",
        lambda comando, timeout=20.0: subprocess.CompletedProcess(comando, 0, "List of devices attached\n", ""),
    )

    assert preparar.main([]) == 3
    assert "NENHUM APARELHO PRONTO" in capsys.readouterr().out


def test_varios_aparelhos_exigem_serial(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setattr(preparar, "localizar_adb", lambda _: "adb")
    monkeypatch.setattr(
        preparar,
        "_executar",
        lambda comando, timeout=20.0: subprocess.CompletedProcess(
            comando, 0, "List of devices attached\nA\tdevice\nB\tdevice\n", ""
        ),
    )

    assert preparar.main([]) == 3
    assert "--serial" in capsys.readouterr().out


def test_caminho_feliz_liga_as_duas_portas(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    chamadas: list[list[str]] = []

    def fake_executar(comando: list[str], timeout: float = 20.0) -> subprocess.CompletedProcess:
        chamadas.append(comando)
        if "devices" in comando:
            return subprocess.CompletedProcess(comando, 0, "List of devices attached\nSERIAL1\tdevice\n", "")
        return subprocess.CompletedProcess(comando, 0, "", "")

    monkeypatch.setattr(preparar, "localizar_adb", lambda _: "adb")
    monkeypatch.setattr(preparar, "_executar", fake_executar)
    monkeypatch.setattr(preparar, "_http_ok", lambda url, timeout=3.0: (True, "HTTP 200"))

    assert preparar.main([]) == 0

    reverses = [c for c in chamadas if "reverse" in c]
    assert reverses == [
        ["adb", "-s", "SERIAL1", "reverse", "tcp:8080", "tcp:8080"],
        ["adb", "-s", "SERIAL1", "reverse", "tcp:8000", "tcp:8000"],
    ]
    saida = capsys.readouterr().out
    assert "http://localhost:8080" in saida
    assert "NÃO aprova nada" in saida


def test_falha_no_reverse_nao_e_sucesso(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    def fake_executar(comando: list[str], timeout: float = 20.0) -> subprocess.CompletedProcess:
        if "devices" in comando:
            return subprocess.CompletedProcess(comando, 0, "List of devices attached\nSERIAL1\tdevice\n", "")
        return subprocess.CompletedProcess(comando, 1, "", "error: more than one device")

    monkeypatch.setattr(preparar, "localizar_adb", lambda _: "adb")
    monkeypatch.setattr(preparar, "_executar", fake_executar)
    monkeypatch.setattr(preparar, "_http_ok", lambda url, timeout=3.0: (True, "HTTP 200"))

    assert preparar.main([]) == 1
    assert "FALHOU" in capsys.readouterr().out
