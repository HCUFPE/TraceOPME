"""Instala o robô do AGHU neste computador (alternativa ao instalar.bat).

Use quando o Windows bloquear o .bat ("Controle de Aplicativo Inteligente"):
  1. Abra esta pasta no Explorador de Arquivos.
  2. Clique na barra de endereço, digite  cmd  e aperte ENTER.
  3. Na janela preta, digite  py instalar.py  e aperte ENTER.

O que faz: cria o ambiente (.venv) aqui, instala playwright e openpyxl e liga o
botão "Lançar no AGHU" do TraceOPME a este robô (protocolo traceopme-aghu, só para
o seu usuário do Windows). O protocolo chama o Python direto — sem arquivo .bat.
"""

from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path

PASTA = Path(__file__).resolve().parent
VENV = PASTA / ".venv"
PY = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def passo(msg: str) -> None:
    print(f"\n>> {msg}", flush=True)


def main() -> int:
    print("=" * 62)
    print(" Robô da Nota de Recebimento no AGHU — instalação neste PC")
    print("=" * 62)
    if not PY.exists():
        passo("Criando o ambiente do robô (.venv)...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    passo("Instalando os componentes (playwright e openpyxl). Pode levar alguns minutos...")
    r = subprocess.run([str(PY), "-m", "pip", "install", "--upgrade", "pip", "playwright", "openpyxl"])
    if r.returncode != 0:
        print("\nA instalação dos componentes falhou. Mande um print desta janela para a Camila.")
        return 1
    if sys.platform == "win32":
        passo("Ligando o botão “Lançar no AGHU” do TraceOPME a este robô...")
        import winreg
        comando = f'"{PY}" "{PASTA / "robo_nota_aghu.py"}" --link "%1"'
        base = r"Software\Classes\traceopme-aghu"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:Robo AGHU do TraceOPME")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, comando)
    print("\nPronto! Agora o botão “Lançar no AGHU agora” do TraceOPME abre o robô neste computador.")
    print("Na primeira vez o navegador pergunta se pode abrir: marque “Sempre permitir” e clique em Abrir.")
    print("Se mudar esta pasta de lugar, rode  py instalar.py  de novo.")
    return 0


if __name__ == "__main__":
    codigo = main()
    try:
        input("\nAperte ENTER para fechar...")
    except Exception:
        pass
    sys.exit(codigo)
