"""Comprueba que la fixture de ``conftest.py`` bloquea la red."""

import socket

import pytest


def test_dns_is_blocked() -> None:
    with pytest.raises(RuntimeError, match="red"):
        socket.getaddrinfo("api.esios.ree.es", 443)


def test_connect_is_blocked() -> None:
    # 192.0.2.1 es de un rango reservado para documentación: no hace falta resolver nombres.
    with pytest.raises(RuntimeError, match="red"):
        socket.create_connection(("192.0.2.1", 443), timeout=1)
