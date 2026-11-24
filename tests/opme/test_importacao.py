"""Verifica que todos os módulos importam e que as rotas estão registradas.

Executar:  python -m tests.opme.test_importacao

Este teste existe porque um `ImportError` num router só aparecia quando o
servidor subia: `compileall` valida sintaxe, não importação, e os demais testes
exercitavam apenas os serviços. Um `from ..config import SALAS` apontando para
um nome que deixou de existir passava despercebido até o uvicorn quebrar.

Se as dependências web não estiverem instaladas, a parte de rotas é pulada com
aviso — os módulos de domínio continuam sendo verificados.
"""

import importlib
import os
import pkgutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))

_temp = tempfile.mkdtemp(prefix="opme_imp_")
os.environ["OPME_DB"] = str(Path(_temp) / "imp.db")
os.environ["OPME_LOG_DIR"] = _temp
os.environ["APP_DB_URL"] = f"sqlite+aiosqlite:///{Path(_temp) / 'app.db'}"

FALHAS: list[str] = []
TOTAL = 0


def conferir(condicao, descricao: str, detalhe: str = "") -> None:
    global TOTAL
    TOTAL += 1
    if condicao:
        print(f"  ok   {descricao}")
    else:
        print(f"  FALHA {descricao} {detalhe}")
        FALHAS.append(descricao)


def secao(titulo: str) -> None:
    print(f"\n== {titulo}")


def modulos_de(pacote: str) -> list[str]:
    caminho = RAIZ / pacote.replace(".", "/")
    return [f"{pacote}.{m.name}" for m in pkgutil.iter_modules([str(caminho)])]


def _nomes_definidos(arquivo: Path) -> set[str]:
    """Nomes que um módulo expõe no topo: variáveis, funções, classes e imports."""
    import ast

    nomes: set[str] = set()
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    for no in arvore.body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nomes.add(no.name)
        elif isinstance(no, ast.Assign):
            for alvo in no.targets:
                if isinstance(alvo, ast.Name):
                    nomes.add(alvo.id)
        elif isinstance(no, ast.AnnAssign) and isinstance(no.target, ast.Name):
            nomes.add(no.target.id)
        elif isinstance(no, (ast.Import, ast.ImportFrom)):
            for apelido in no.names:
                nomes.add(apelido.asname or apelido.name.split(".")[0])
    return nomes


def conferir_imports_internos() -> list[tuple[str, str, str]]:
    """Confere que cada `from .modulo import nome` aponta para um nome existente."""
    import ast

    definidos: dict[str, set[str]] = {}
    for arquivo in sorted((RAIZ / "src").rglob("*.py")):
        relativo = arquivo.relative_to(RAIZ).with_suffix("")
        modulo = ".".join(relativo.parts)
        if modulo.endswith(".__init__"):
            modulo = modulo[: -len(".__init__")]
        definidos[modulo] = _nomes_definidos(arquivo)

    quebrados: list[tuple[str, str, str]] = []
    for arquivo in sorted((RAIZ / "src").rglob("*.py")):
        relativo = arquivo.relative_to(RAIZ).with_suffix("")
        partes = list(relativo.parts)
        if partes[-1] == "__init__":
            partes.pop()
        origem = ".".join(partes)

        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.ImportFrom) or not no.level:
                continue

            # level=1 é o pacote do próprio módulo; cada nível a mais sobe um.
            base = partes[: len(partes) - no.level]
            if base and base[-1] == "":
                continue
            alvo = ".".join(base + ([no.module] if no.module else []))
            if alvo not in definidos:
                continue  # aponta para fora do projeto

            for apelido in no.names:
                if apelido.name == "*":
                    continue
                # Pode ser um nome definido no módulo/pacote alvo…
                if apelido.name in definidos[alvo]:
                    continue
                # …ou um submódulo dele, como `from .. import db`.
                if f"{alvo}.{apelido.name}" in definidos:
                    continue
                quebrados.append((origem, alvo, apelido.name))
    return quebrados


def main() -> int:
    secao("Módulos de domínio")
    for nome in ["src.providers.implementations.opme.config", "src.providers.implementations.opme.db", "src.providers.implementations.opme.domain", "src.providers.implementations.opme.security", "src.providers.implementations.opme.utils",
                 "src.providers.implementations.opme.log", "src.providers.implementations.opme.indicadores"] + modulos_de("src.providers.implementations.opme.services"):
        try:
            importlib.import_module(nome)
            conferir(True, nome)
        except Exception as erro:
            conferir(False, nome, f"{type(erro).__name__}: {erro}")

    secao("Aplicação web e rotas")
    try:
        import fastapi  # noqa: F401
    except ImportError:
        print("  (fastapi não instalado neste ambiente — parte de rotas pulada)")
        print("   Instale com: pip install -r requirements.txt")
    else:
        for nome in modulos_de("src.routers") + modulos_de("src.controllers"):
            try:
                importlib.import_module(nome)
                conferir(True, nome)
            except Exception as erro:
                conferir(False, nome, f"{type(erro).__name__}: {erro}")

        try:
            from src.main import app
            conferir(True, "src.main importa sem erro")

            caminhos = {r.path for r in app.routes}
            essenciais = [
                "/api/", "/api/login", "/api/logout", "/api/perfil", "/api/health",
                "/api/bipagem/{operacao}", "/api/bipar", "/api/desfazer",
                "/api/almoxarifado", "/api/almoxarifado/nf", "/api/almoxarifado/manual",
                "/api/sala-procedimento/agenda", "/api/sala-procedimento/atendimento/{id_atendimento}",
                "/api/sala-procedimento", "/api/sala-procedimento/atendimentos", "/api/sala-procedimento/estorno",
                "/api/consignados", "/api/consignados/pendentes", "/api/consignados/empenhos",
                "/api/consignados/empenhos/novo", "/api/consignados/empenhos/{id_empenho}",
                "/api/consultas", "/api/consultas/prontuario", "/api/consultas/utilizados",
                "/api/consultas/classificacao",
                "/api/almoxarifado/etiquetas", "/api/almoxarifado/qr/{codigo}.png",
                "/api/indicadores", "/api/indicadores/metas",
                "/api/admin", "/api/admin/diagnostico", "/api/admin/ad-user-search/{username}",
                "/api/alertas/{id_alerta}/resolver",
            ]
            faltando = [c for c in essenciais if c not in caminhos]
            conferir(not faltando, f"{len(essenciais)} rotas essenciais registradas",
                     str(faltando))
            conferir(len(caminhos) > 40, f"{len(caminhos)} rotas no total")

            # Toda operação de bipagem precisa de um módulo que exista de fato.
            from src.providers.implementations.opme.domain import OPERACOES
            from src.providers.implementations.opme.security import MODULOS
            invalidas = [o.codigo for o in OPERACOES.values() if o.modulo not in MODULOS]
            conferir(not invalidas, "toda operação aponta para um módulo existente",
                     str(invalidas))

            from src.providers.implementations.opme.security import PAPEIS
            modulos_invalidos = [
                (papel, m) for papel, (_, mods) in PAPEIS.items()
                for m in mods if m not in MODULOS
            ]
            conferir(not modulos_invalidos, "todo perfil referencia módulos existentes",
                     str(modulos_invalidos))
        except Exception as erro:
            conferir(False, "src.main importa sem erro", f"{type(erro).__name__}: {erro}")

    secao("Nomes importados entre módulos do projeto")
    # Verificação estática: funciona mesmo sem fastapi instalado e pega justamente
    # o caso do `from ..config import SALAS` apontando para um nome removido.
    problemas = conferir_imports_internos()
    for origem, alvo, nome in problemas:
        conferir(False, f"{origem} importa “{nome}” de {alvo}", "esse nome não existe lá")
    conferir(not problemas,
             "todo nome importado entre módulos do projeto existe de fato",
             f"{len(problemas)} import(s) quebrado(s)")

    secao("Configuração de unidades e salas")
    from src.providers.implementations.opme.config import (
        UNIDADES, UNIDADES_ATIVAS, cor_unidade, locais, rotulo_unidade,
        salas_da_unidade, todas_as_salas,
    )
    conferir(all("rotulo" in d and "salas" in d and "cor" in d for d in UNIDADES.values()),
             "toda unidade tem rótulo, cor e lista de salas")
    conferir(all(d["salas"] for d in UNIDADES.values()),
             "nenhuma unidade está sem salas")
    conferir(len(todas_as_salas()) > 0, "há salas cadastradas")
    # Só Bloco Cirúrgico e Hemodinâmica usam OPME — locais()/todas_as_salas() por
    # padrão mostram só essas, mas devolvem todas quando pedido explicitamente.
    conferir(0 < len(UNIDADES_ATIVAS) < len(UNIDADES),
             "há unidades ativas (OPME) e unidades fora do padrão, e são conjuntos distintos")
    conferir(all(d["usa_opme"] for d in UNIDADES_ATIVAS.values()),
             "toda unidade ativa realmente usa OPME")
    conferir(len(locais()) == sum(len(d["salas"]) for d in UNIDADES_ATIVAS.values()),
             "por padrão, locais() cobre só as unidades ativas")
    conferir(len(locais(apenas_ativas=False)) == sum(len(d["salas"]) for d in UNIDADES.values()),
             "locais(apenas_ativas=False) cobre todas as unidades")
    conferir(set(todas_as_salas()) <= set(todas_as_salas(apenas_ativas=False)),
             "todas_as_salas() padrão é subconjunto de todas_as_salas(apenas_ativas=False)")
    conferir(rotulo_unidade("INEXISTENTE") == "INEXISTENTE",
             "unidade desconhecida não quebra o rótulo")
    conferir(cor_unidade("INEXISTENTE") == "cinza",
             "unidade desconhecida devolve cor neutra")
    conferir(salas_da_unidade("INEXISTENTE"), "unidade desconhecida devolve salas genéricas")

    secao("Coerência do domínio")
    from src.providers.implementations.opme.domain import ESTADOS, OPERACOES
    for op in OPERACOES.values():
        conferir(op.para in ESTADOS, f"destino de “{op.titulo}” é um estado válido", op.para)
    origens_invalidas = [
        (o.codigo, s) for o in OPERACOES.values() for s in o.de if s not in ESTADOS
    ]
    conferir(not origens_invalidas, "todas as origens são estados válidos",
             str(origens_invalidas))

    print("\n" + "=" * 60)
    if FALHAS:
        print(f"  {len(FALHAS)} de {TOTAL} verificações FALHARAM:")
        for f in FALHAS:
            print(f"   - {f}")
        return 1
    print(f"  Todas as {TOTAL} verificações passaram.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
