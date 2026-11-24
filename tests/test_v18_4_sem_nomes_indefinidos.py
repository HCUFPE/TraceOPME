# tests/test_v18_4_sem_nomes_indefinidos.py
"""v18.4.2: nenhum nome indefinido no código (pegaria import faltando antes do servidor)."""
import subprocess
import sys

import pytest


def test_sem_nomes_indefinidos():
    try:
        import pyflakes  # noqa: F401
    except ImportError:
        pytest.skip("pyflakes não instalado")
    r = subprocess.run([sys.executable, "-m", "pyflakes", "src"], capture_output=True, text=True)
    indefinidos = [l for l in r.stdout.splitlines() if "undefined name" in l]
    assert not indefinidos, "\n".join(indefinidos)
