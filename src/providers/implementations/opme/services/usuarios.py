"""Usuários, autenticação e solicitações de acesso."""

from datetime import datetime, timedelta

from .. import db, log
from ..config import MINUTOS_BLOQUEIO, TENTATIVAS_MAXIMAS
from ..security import PAPEIS, gerar_hash, modo_autenticacao, senha_confere, senha_forte, verificar_senha
from ..utils import data_hora_br, gerar_id, texto


def _registrar_falha(usuario: dict) -> None:
    """Conta a tentativa errada e bloqueia a conta ao passar do limite."""
    tentativas = (usuario["tentativas_falhas"] or 0) + 1
    ate = None
    if tentativas >= TENTATIVAS_MAXIMAS:
        ate = (datetime.now() + timedelta(minutes=MINUTOS_BLOQUEIO)).isoformat(timespec="seconds")
        log.aviso(f"conta bloqueada por {MINUTOS_BLOQUEIO} min após "
                  f"{tentativas} tentativas erradas", usuario["username"])
    db.executar(
        "UPDATE usuarios SET tentativas_falhas = ?, bloqueado_ate = ? WHERE username = ?",
        (tentativas, ate, usuario["username"]))


def desbloquear(username: str, quem: str) -> tuple[bool, str]:
    """Libera a conta antes do prazo — usado pelo administrador."""
    alterados = db.executar(
        "UPDATE usuarios SET tentativas_falhas = 0, bloqueado_ate = NULL WHERE username = ?",
        (texto(username),))
    if not alterados:
        return False, "Usuário não encontrado."
    log.info(f"conta desbloqueada manualmente · alvo={texto(username)}", quem)
    return True, "Conta desbloqueada."


def _minutos_restantes(bloqueado_ate: str) -> int:
    if not texto(bloqueado_ate):
        return 0
    try:
        limite = datetime.fromisoformat(bloqueado_ate)
    except ValueError:
        return 0
    faltam = (limite - datetime.now()).total_seconds()
    return max(0, int(faltam // 60) + 1) if faltam > 0 else 0


def autenticar(username: str, senha: str, criar_solicitacao: bool = False) -> tuple[bool, str | dict]:
    """Confere login e senha.

    Com o AD configurado (nov/2026), a ordem é a do framework:
      1. login e senha no AD — se não conferem: "Usuário ou senha inválidos.";
      2. perfil de acesso na tabela local `usuarios` — se a pessoa ainda não tem
         perfil e é o login da tela de entrada (`criar_solicitacao`), registra
         sozinha a solicitação de acesso com nome, e-mail e setor vindos do AD,
         para o administrador aprovar ou recusar. Nesse caso devolve
         ``(False, {"solicitacao_acesso": True, "mensagem": ...})``.
    Nas confirmações com senha (entrega, supervisão...), quem não tem perfil é
    só recusado — não vira solicitação.
    """
    username = texto(username).lower()
    if not username or not senha:
        return False, "Informe usuário e senha."

    usuario = db.consultar_um("SELECT * FROM usuarios WHERE LOWER(username) = ?", (username,))
    if modo_autenticacao() == "ad":
        return _autenticar_ad(username, senha, usuario, criar_solicitacao)

    if usuario:
        restam = _minutos_restantes(usuario["bloqueado_ate"])
        if restam:
            log.aviso(f"login recusado: conta bloqueada por tentativas · "
                      f"faltam {restam} min", usuario["username"])
            return False, (f"Conta temporariamente bloqueada por excesso de tentativas. "
                           f"Tente de novo em {restam} minuto(s), ou peça ao administrador "
                           f"para redefinir a sua senha.")

    # Framework SETISD: com o AD configurado, a senha é a da rede (conferida no
    # AD); o papel e a situação da conta continuam vindo desta tabela local.
    if not usuario or not senha_confere(usuario["username"], senha, usuario["senha_hash"]):
        if usuario:
            _registrar_falha(usuario)
        # Mensagem única: não revela se o usuário existe. O log guarda a tentativa
        # para que dá para perceber ataque de força bruta ou conta esquecida.
        log.aviso(f"tentativa de login sem sucesso · usuario informado={username}")
        return False, "Usuário ou senha inválidos."
    if usuario["status"] != "ativo":
        log.aviso("login recusado: conta inativa", usuario["username"])
        return False, "Seu acesso ainda não foi liberado pelo administrador."

    db.executar(
        "UPDATE usuarios SET ultimo_acesso = ?, tentativas_falhas = 0, bloqueado_ate = NULL "
        "WHERE username = ?",
        (db.agora(), usuario["username"]))
    log.info(f"login efetuado · perfil={usuario['papel']}", usuario["username"])
    return True, {
        "username": usuario["username"],
        "nome": usuario["nome"],
        "papel": usuario["papel"],
        "setor": usuario["setor"] or "",
    }


def _autenticar_ad(username: str, senha: str, usuario: dict | None,
                   criar_solicitacao: bool) -> tuple[bool, str | dict]:
    from ..security import AdIndisponivel, autenticar_externo
    if usuario:
        restam = _minutos_restantes(usuario["bloqueado_ate"])
        if restam:
            log.aviso(f"login recusado: conta bloqueada por tentativas · faltam {restam} min", usuario["username"])
            return False, (f"Conta temporariamente bloqueada por excesso de tentativas. "
                           f"Tente de novo em {restam} minuto(s).")
    try:
        dados_ad = autenticar_externo(username, senha)
    except AdIndisponivel as erro:
        detalhe = str(erro).strip()
        return False, ("Não foi possível falar com o Active Directory agora. Tente de novo em "
                       "instantes; se continuar, avise a TI."
                       + (f" Detalhe técnico: {detalhe[:220]}" if detalhe else ""))
    if dados_ad is None:
        if usuario:
            _registrar_falha(usuario)
        log.aviso(f"tentativa de login sem sucesso (AD) · usuario informado={username}")
        return False, "Usuário ou senha inválidos."

    if not usuario:
        if not criar_solicitacao:
            return False, "Este usuário ainda não tem perfil de acesso no TraceOPME."
        return False, solicitar_acesso_pelo_ad(username, dados_ad)
    if usuario["status"] != "ativo":
        log.aviso("login recusado: conta inativa", usuario["username"])
        return False, "Seu acesso ao TraceOPME está desativado. Fale com o administrador."

    # Mantém nome, e-mail e setor iguais aos do AD (só preenche o que veio).
    atualizar = {c: texto(dados_ad.get(c)) for c in ("nome", "email", "setor") if texto(dados_ad.get(c))}
    campos = "".join(f", {c} = ?" for c in atualizar)
    db.executar(
        f"UPDATE usuarios SET ultimo_acesso = ?, tentativas_falhas = 0, bloqueado_ate = NULL{campos} "
        "WHERE username = ?",
        (db.agora(), *atualizar.values(), usuario["username"]))
    log.info(f"login efetuado (AD) · perfil={usuario['papel']}", usuario["username"])
    return True, {
        "username": usuario["username"],
        "nome": atualizar.get("nome") or usuario["nome"],
        "papel": usuario["papel"],
        "setor": atualizar.get("setor") or usuario["setor"] or "",
    }


def solicitar_acesso_pelo_ad(username: str, dados_ad: dict) -> dict:
    """Primeiro login (AD válido, sem perfil): registra a solicitação de acesso.

    Os dados vêm do AD — a pessoa não digita nada. Se já há uma solicitação
    pendente, não cria outra: só avisa que ela continua com o administrador.
    """
    username = texto(username).lower()
    pendente = db.consultar_um(
        "SELECT criada_em FROM solicitacoes_acesso WHERE LOWER(username) = ? AND status = 'pendente' "
        "AND tipo = 'cadastro' ORDER BY criada_em DESC LIMIT 1", (username,))
    if pendente:
        return {"solicitacao_acesso": True, "nova": False,
                "mensagem": ("Seu login e senha foram confirmados no AD, mas você ainda não tem perfil de acesso. "
                             "Sua solicitação já está com o administrador (enviada em "
                             f"{data_hora_br(pendente['criada_em'])}). Aguarde a aprovação.")}
    from ..security import token
    db.executar(
        """INSERT INTO solicitacoes_acesso
           (id_solicitacao, tipo, username, nome, email, setor, papel, senha_hash, status, observacao, criada_em)
           VALUES (?, 'cadastro', ?,?,?,?, 'consulta', ?, 'pendente', ?, ?)""",
        (gerar_id("SOL"), username, texto(dados_ad.get("nome")) or username, texto(dados_ad.get("email")),
         texto(dados_ad.get("setor")), gerar_hash(token()),
         "Solicitação automática: primeiro login validado no AD", db.agora()),
    )
    log.info("solicitação de acesso registrada no primeiro login (AD)", username)
    return {"solicitacao_acesso": True, "nova": True,
            "mensagem": ("Seu login e senha foram confirmados no AD, mas você ainda não tem perfil de acesso "
                         "no TraceOPME. Enviamos uma solicitação de acesso ao administrador, com o seu nome, "
                         "e-mail e setor do AD. Você poderá entrar assim que ela for aprovada.")}


def confirmar_responsavel(
    usuario_operador: str, usuario_responsavel: str, senha_responsavel: str,
    *,
    papel_exigido: str = "sala-procedimento",
    quem: str = "responsável da sala",
) -> tuple[bool, str, dict | None]:
    """Autentica, na hora, quem está recebendo o material.

    Usada nos dois sentidos da entrega (bipagem e caixa): a farmácia dispensa e
    a sala confirma; a sala devolve e a farmácia confirma. Não é um login de
    sessão, é a prova de que a pessoa certa está fisicamente ali no momento da
    entrega. Por isso exige usuário e senha de novo (mesma regra de conta
    bloqueada/inativa do login normal), exige o papel de quem recebe, e exige
    que não seja a mesma pessoa que está operando o leitor — a confirmação é de
    quem recebe, não de quem entrega.
    """
    usuario_responsavel = texto(usuario_responsavel)
    if not usuario_responsavel or not texto(senha_responsavel):
        return False, (
            f"Antes de concluir, o {quem} precisa digitar o usuário e a senha "
            f"para confirmar que está recebendo o material."
        ), None

    ok_login, resultado = autenticar(usuario_responsavel, senha_responsavel)
    if not ok_login:
        # `resultado` já é a mensagem pronta do login (senha errada, conta
        # bloqueada, inativa etc.) — não precisa reformular.
        return False, resultado, None

    if resultado["papel"] != papel_exigido:
        return False, (
            f"{resultado['nome']} não está cadastrado(a) como {quem} e não pode "
            f"confirmar este recebimento."
        ), None

    if resultado["username"].lower() == texto(usuario_operador).lower():
        return False, (
            f"Quem confirma o recebimento precisa ser o {quem}, não quem está "
            f"operando o leitor."
        ), None

    return True, "", resultado


def confirmadores(papel: str, operador: str = "") -> list[dict]:
    """Quem pode confirmar um recebimento com a própria senha.

    A tela oferece a lista em vez de pedir o login digitado: são poucas pessoas,
    e digitar o usuário de outra pessoa, de pé, no computador de quem entrega, é
    onde o processo trava na prática. Quem está operando o leitor fica fora da
    lista — a confirmação é de quem recebe, e `confirmar_responsavel` recusaria
    essa escolha adiante de qualquer forma; melhor não oferecer.
    """
    if not texto(papel):
        return []
    return db.consultar(
        "SELECT username, nome, setor FROM usuarios "
        "WHERE papel = ? AND status = 'ativo' AND LOWER(username) <> LOWER(?) "
        "ORDER BY nome",
        (texto(papel), texto(operador)),
    )


def listar() -> list[dict]:
    linhas = db.consultar(
        "SELECT username, nome, email, setor, papel, status, criado_em, ultimo_acesso, "
        "       tentativas_falhas, bloqueado_ate "
        "FROM usuarios ORDER BY status, nome"
    )
    for linha in linhas:
        # Bloqueio vencido não é bloqueio: a tela não deve oferecer desbloquear.
        if not _minutos_restantes(linha["bloqueado_ate"]):
            linha["bloqueado_ate"] = None
    return linhas


def solicitar_cadastro(dados: dict) -> tuple[bool, str]:
    username = texto(dados.get("username")).lower()
    senha = texto(dados.get("senha"))
    if not username or not texto(dados.get("nome")):
        return False, "Informe nome completo e usuário."
    if len(username) < 3:
        return False, "O usuário precisa ter pelo menos 3 caracteres."
    if modo_autenticacao() == "ad":
        # Com o AD, a pessoa entra com a senha de rede: a solicitação não leva
        # senha. Guarda-se um hash aleatório só para preencher a coluna.
        from ..security import token
        senha = senha or token()
    else:
        ok, msg = senha_forte(senha)
        if not ok:
            return False, msg
    if db.consultar_um("SELECT 1 FROM usuarios WHERE LOWER(username) = ?", (username,)):
        return False, "Já existe um usuário com esse nome de acesso."
    if db.consultar_um(
        "SELECT 1 FROM solicitacoes_acesso WHERE LOWER(username) = ? AND status = 'pendente'",
        (username,),
    ):
        return False, "Já existe uma solicitação pendente para este usuário."

    papel = dados.get("papel") if dados.get("papel") in PAPEIS else "consulta"
    db.executar(
        """INSERT INTO solicitacoes_acesso
           (id_solicitacao, tipo, username, nome, email, setor, papel, senha_hash, status, criada_em)
           VALUES (?, 'cadastro', ?,?,?,?,?,?, 'pendente', ?)""",
        (gerar_id("SOL"), username, texto(dados.get("nome")), texto(dados.get("email")),
         texto(dados.get("setor")), papel, gerar_hash(senha), db.agora()),
    )
    return True, "Solicitação enviada. Um administrador precisa liberar seu acesso."


def solicitar_nova_senha(dados: dict) -> tuple[bool, str]:
    if modo_autenticacao() == "ad":
        return False, ("A senha é a mesma da rede (Active Directory da Ebserh). Para trocá-la "
                       "ou desbloqueá-la, procure a TI.")
    username = texto(dados.get("username")).lower()
    senha = texto(dados.get("senha"))
    ok, msg = senha_forte(senha)
    if not ok:
        return False, msg

    usuario = db.consultar_um("SELECT * FROM usuarios WHERE LOWER(username) = ?", (username,))
    # Resposta idêntica exista ou não o usuário.
    if usuario:
        db.executar(
            """INSERT INTO solicitacoes_acesso
               (id_solicitacao, tipo, username, nome, email, setor, papel, senha_hash, status, observacao, criada_em)
               VALUES (?, 'senha', ?,?,?,?,?,?, 'pendente', ?, ?)""",
            (gerar_id("SOL"), usuario["username"], usuario["nome"], texto(dados.get("email")),
             usuario["setor"], usuario["papel"], gerar_hash(senha),
             texto(dados.get("observacao")), db.agora()),
        )
    return True, ("Solicitação registrada. Se o usuário existir, um administrador "
                  "poderá liberar a nova senha.")


def solicitacoes_pendentes() -> list[dict]:
    return db.consultar(
        "SELECT * FROM solicitacoes_acesso WHERE status = 'pendente' ORDER BY criada_em"
    )


def aprovar(id_solicitacao: str, admin: str, papel: str = "") -> tuple[bool, str]:
    solicitacao = db.consultar_um(
        "SELECT * FROM solicitacoes_acesso WHERE id_solicitacao = ? AND status = 'pendente'",
        (id_solicitacao,),
    )
    if not solicitacao:
        return False, "Solicitação não encontrada ou já atendida."

    papel_final = papel if papel in PAPEIS else (solicitacao["papel"] or "consulta")

    with db.transacao() as conn:
        if solicitacao["tipo"] == "cadastro":
            conn.execute(
                """INSERT OR REPLACE INTO usuarios
                   (username, senha_hash, nome, email, setor, papel, status, criado_em)
                   VALUES (?,?,?,?,?,?, 'ativo', ?)""",
                (solicitacao["username"], solicitacao["senha_hash"], solicitacao["nome"],
                 solicitacao["email"], solicitacao["setor"], papel_final, db.agora()),
            )
            mensagem = f"Acesso de {solicitacao['username']} liberado."
        else:
            conn.execute("UPDATE usuarios SET senha_hash = ? WHERE username = ?",
                         (solicitacao["senha_hash"], solicitacao["username"]))
            mensagem = f"Senha de {solicitacao['username']} redefinida."

        conn.execute(
            "UPDATE solicitacoes_acesso SET status = 'aprovada', atendida_em = ?, atendida_por = ? WHERE id_solicitacao = ?",
            (db.agora(), admin, id_solicitacao),
        )
        db.registrar_evento(conn, tipo="acesso_aprovado", usuario=admin,
                            observacao=f"{solicitacao['tipo']} · {solicitacao['username']}")
    return True, mensagem


def rejeitar(id_solicitacao: str, admin: str, motivo: str = "") -> tuple[bool, str]:
    alterados = db.executar(
        """UPDATE solicitacoes_acesso SET status = 'rejeitada', observacao = ?,
           atendida_em = ?, atendida_por = ? WHERE id_solicitacao = ? AND status = 'pendente'""",
        (texto(motivo), db.agora(), admin, id_solicitacao),
    )
    if not alterados:
        return False, "Solicitação não encontrada ou já atendida."
    return True, "Solicitação rejeitada."


def alterar_papel(username: str, papel: str, admin: str) -> tuple[bool, str]:
    if papel not in PAPEIS:
        return False, "Perfil inválido."
    if username == admin and papel != "admin":
        return False, "Você não pode remover o próprio perfil de administrador."
    db.executar("UPDATE usuarios SET papel = ? WHERE username = ?", (papel, username))
    return True, f"Perfil de {username} atualizado."


def alterar_status(username: str, status: str, admin: str) -> tuple[bool, str]:
    if status not in ("ativo", "inativo"):
        return False, "Situação inválida."
    if username == admin and status == "inativo":
        return False, "Você não pode desativar o próprio acesso."
    if status == "inativo" and db.escalar(
        "SELECT COUNT(*) FROM usuarios WHERE papel = 'admin' AND status = 'ativo'"
    ) <= 1 and db.consultar_um(
        "SELECT 1 FROM usuarios WHERE username = ? AND papel = 'admin'", (username,)
    ):
        return False, "É preciso manter ao menos um administrador ativo."
    db.executar("UPDATE usuarios SET status = ? WHERE username = ?", (status, username))
    return True, f"Acesso de {username} agora está {status}."


def trocar_propria_senha(username: str, senha_atual: str, nova: str) -> tuple[bool, str]:
    if modo_autenticacao() == "ad":
        return False, ("A senha é a mesma da rede (Active Directory da Ebserh) e é trocada "
                       "pelos canais da TI, não por aqui.")
    usuario = db.consultar_um("SELECT * FROM usuarios WHERE username = ?", (username,))
    if not usuario or not verificar_senha(senha_atual, usuario["senha_hash"]):
        return False, "Senha atual incorreta."
    ok, msg = senha_forte(nova)
    if not ok:
        return False, msg
    db.executar("UPDATE usuarios SET senha_hash = ? WHERE username = ?",
                (gerar_hash(nova), username))
    return True, "Senha alterada."


def buscar(username: str) -> dict | None:
    """Usuário local (RBAC) pelo login, sem a senha. Usado a cada requisição da API."""
    linha = db.consultar_um(
        "SELECT username, nome, email, setor, papel, status, bloqueado_ate "
        "FROM usuarios WHERE LOWER(username) = ?", (texto(username).lower(),))
    return linha


def cadastrar_direto(dados: dict, admin: str) -> tuple[bool, str]:
    """Framework SETISD: o administrador inclui o usuário depois de "Consultar AD".

    Nome, e-mail e setor vêm do AD; o papel (RBAC) é escolhido aqui. Sem AD
    (modo local), a senha inicial é obrigatória e segue a mesma regra de força.
    """
    username = texto(dados.get("username")).lower()
    nome = texto(dados.get("nome"))
    papel = dados.get("papel") if dados.get("papel") in PAPEIS else ""
    if not username or not nome:
        return False, "Informe o usuário e o nome completo (use “Consultar AD”)."
    if not papel:
        return False, "Escolha o perfil de acesso."
    if db.consultar_um("SELECT 1 FROM usuarios WHERE LOWER(username) = ?", (username,)):
        return False, "Já existe um usuário com esse login."
    senha = texto(dados.get("senha"))
    if modo_autenticacao() == "ad":
        from ..security import token
        senha = senha or token()
    else:
        ok, msg = senha_forte(senha)
        if not ok:
            return False, msg
    with db.transacao() as conn:
        conn.execute(
            """INSERT INTO usuarios (username, senha_hash, nome, email, setor, papel, status, criado_em)
               VALUES (?,?,?,?,?,?, 'ativo', ?)""",
            (username, gerar_hash(senha), nome, texto(dados.get("email")),
             texto(dados.get("setor")), papel, db.agora()))
        db.registrar_evento(conn, tipo="acesso_aprovado", usuario=admin,
                            observacao=f"cadastro direto · {username}")
    log.info(f"usuário incluído pelo administrador · alvo={username} · perfil={papel}", admin)
    return True, f"Usuário {username} incluído com o perfil {PAPEIS[papel][0]}."
