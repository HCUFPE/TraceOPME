"""Tipos de erro compartilhados.

Módulo sem dependências de propósito: `db` precisa reconhecer o erro de regra
de negócio sem importar os serviços, que por sua vez importam `db`.

A distinção importa para o log. Uma recusa de regra — bipar na etapa errada,
material vencido, saldo esgotado — é comportamento esperado do sistema, não
defeito. Registrar isso como ERRO com traceback enche o log de ruído e esconde
as falhas técnicas de verdade, que é justamente quando o log precisa servir.
"""


class ErroDeNegocio(Exception):
    """Regra de negócio recusou a operação. A mensagem é para o operador ler."""
