# tests/test_opme_suite.py
"""Executa as suítes de regras de negócio do TraceOPME (portadas da versão 17).

Cada suíte roda em processo separado, com banco temporário próprio, como na v17:
    - test_v17               (489 verificações: fluxo completo + telas via API)
    - test_importacao        (módulos, rotas essenciais e imports internos)
    - test_catalogo_materiais (atualização do catálogo MasterTools)
    - test_correcao_lote     (correção em lote segura)
    - test_ajustes_nov2026   (excluir/ajustar cadastro, busca GS1, consignado, aviso de validade)
    - test_ajustes_nov2026_b (cancelar envio, devolução ao almoxarifado, romaneio, empenho por consignado)
"""
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

SUITES = ["test_v17", "test_importacao", "test_catalogo_materiais", "test_correcao_lote",
          "test_ajustes_nov2026", "test_ajustes_nov2026_b"]


@pytest.mark.parametrize("suite", SUITES)
def test_suite_traceopme(suite):
    resultado = subprocess.run(
        [sys.executable, "-m", f"tests.opme.{suite}"], cwd=RAIZ,
        capture_output=True, text=True, timeout=1800,
    )
    saida = resultado.stdout[-4000:] + resultado.stderr[-2000:]
    assert resultado.returncode == 0, saida
    assert "FALHA" not in resultado.stdout, saida
