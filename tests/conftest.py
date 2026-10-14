"""Configuración común de los tests."""

import socket
from typing import NoReturn

import pytest


def _refuse_network(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError("los tests no pueden abrir conexiones de red")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bloquea la red en todos los tests.

    Ningún test puede llegar a e·sios ni a otra fuente, aunque falle un mock: el token es
    personal y sus condiciones prohíben peticiones redundantes. Los procesos hijos (como
    ``git`` en los tests de ``.gitignore``) no se ven afectados.
    """
    monkeypatch.setattr(socket, "getaddrinfo", _refuse_network)
    monkeypatch.setattr(socket.socket, "connect", _refuse_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse_network)
