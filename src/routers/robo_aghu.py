"""Router — robô do AGHU (nov/2026).

O robô roda no computador de quem lança a nota e fala com o servidor do
TraceOPME. Sem login (o robô não tem a sessão da pessoa): cada chamada leva o
código de uso único gerado quando a pessoa clicou em "Lançar no AGHU".
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/api/robo-aghu", tags=["Robô AGHU"])


@router.get("/planilha")
async def planilha(chave: str = "", token: str = ""):
    """Planilha da NF para o robô (com o código)."""
    from ..providers.implementations.opme.services import aghu_robo
    conteudo, nome = await run_in_threadpool(aghu_robo.planilha_para_robo, chave, token)
    if conteudo is None:
        return JSONResponse({"ok": False, "mensagem": nome}, status_code=403)
    return Response(conteudo, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.get("/consumo")
async def consumo(chave: str = "", token: str = "", tipo: str = "consumo"):
    """v18.7: materiais usados no paciente, para a nota de consumo (com o código).
    v18.8: tipo=rm — requisição de material, com os lotes de cada material."""
    from ..providers.implementations.opme.services import nota_consumo
    tipo = tipo if tipo in nota_consumo.DOCUMENTOS else "consumo"
    dados = await run_in_threadpool(nota_consumo.para_robo, chave, token, tipo)
    return JSONResponse(dados, status_code=200 if dados.get("ok") else 403)


@router.post("/retorno")
async def retorno(request: Request):
    """O robô conta se a nota foi gravada no AGHU (o código vale uma vez)."""
    from ..providers.implementations.opme.services import aghu_robo
    try:
        corpo = await request.json()
    except Exception:
        corpo = {}
    if str(corpo.get("tipo") or "") in ("consumo", "rm"):   # v18.7: nota de consumo · v18.8: RM
        from ..providers.implementations.opme.services import nota_consumo
        ok, msg = await run_in_threadpool(nota_consumo.retorno, str(corpo.get("chave") or ""),
                                          str(corpo.get("token") or ""), bool(corpo.get("gravou")),
                                          str(corpo.get("tipo")))
        return JSONResponse({"ok": ok, "mensagem": msg}, status_code=200 if ok else 400)
    ok, msg = await run_in_threadpool(aghu_robo.retorno, str(corpo.get("chave") or ""), str(corpo.get("token") or ""),
                                      bool(corpo.get("gravou")), str(corpo.get("numero_nr") or ""))
    return JSONResponse({"ok": ok, "mensagem": msg}, status_code=200 if ok else 400)
