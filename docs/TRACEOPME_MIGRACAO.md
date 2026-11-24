# TraceOPME: da versão 17 (Jinja) para o Framework SETISD

Este documento registra como a aplicação TraceOPME v17 (pasta
`TraceOPME_ATUALIZACAO_SERVIDOR_28-10-2026_caixas_na_sala`) foi levada para o modelo do
Framework-SETISD-HC-UFPE, **sem perder funcionalidade**.

## 1. O que mudou e o que não mudou

| Assunto | v17 | Agora (framework) |
|---|---|---|
| Regras de negócio | `app/services/*`, `app/domain.py` | **as mesmas**, em `src/providers/implementations/opme/` |
| Banco de dados | SQLite `data/opme.db` | **o mesmo arquivo e esquema** (`OPME_DB`); migrações automáticas da v17 continuam rodando na inicialização |
| Rotas HTTP | `app/routers/*` (HTML + Jinja) | `src/routers/*` → `src/controllers/*` (JSON em `/api/...`), 190 endpoints, todos privados por padrão |
| Telas | 75 templates Jinja + `app.js` | 72 views Vue 3 (`frontend/src/views/opme`) + componentes em `components/opme`; mesmas URLs, mesmos campos e textos |
| Login | usuário/senha local, sessão em cookie | **AD/LDAP** (senha de rede) + perfil local (RBAC). Sem `AD_URL`, senha local (reserva) |
| Sessão | cookie de sessão do Starlette | JWT de acesso (10 h) + refresh token em cookie HttpOnly |
| Unidade/farmácia escolhida | sessão do servidor | navegador (Pinia), enviada no cabeçalho `X-Sessao` |
| Auditoria | `eventos` (por item) + log técnico | **mantidos**, e toda ação que altera dado também vai para `audit_logs` (usuário, categoria, ação, recurso, antes/depois, IP) |
| Configuração | `app/config.py` com valores fixos | `src/config.py` + `.env` (variáveis `OPME_*`, ver `.env.example`) |
| Monitoramento | — | `GET /api/health` (inclui o banco do TraceOPME) |
| Visual | `app.css` próprio | layout do framework (menu lateral, versão no rodapé); o CSS da v17 foi mantido dentro de `.opme`, com a paleta do framework |

## 2. Correspondência de pastas

```text
v17                                   framework
app/main.py                    →      src/main.py (lifespan inicializa o banco, backup e caixas)
app/config.py                  →      src/config.py (Settings) + providers/implementations/opme/config.py
app/db.py                      →      src/resources/opme_sqlite.py + providers/implementations/opme/db.py
app/security.py                →      providers/implementations/opme/security.py + src/auth/auth.py (AD)
app/services/*.py              →      providers/implementations/opme/services/*.py
app/routers/<modulo>.py        →      src/routers/<modulo>.py + src/controllers/<modulo>_controller.py
app/templates/<modulo>/*.html  →      frontend/src/views/opme/<Modulo><Tela>.vue  (registro em telas.ts)
app/templates/_*.html          →      frontend/src/components/opme/*.vue
app/static/app.js (bipagem)    →      views/opme/Bipagem.vue + composables/useLeitor.ts
app/static/app.css             →      frontend/src/assets/opme.css
testes/*                       →      tests/opme/* (rodam no pytest via tests/test_opme_suite.py)
```

## 3. Como as telas conversam com a API

1. O navegador abre, por exemplo, `/farmacia/estoque?farmacia=BLOCO%20CIRURGICO`.
2. `PaginaOpme.vue` pede `GET /api/farmacia/estoque?farmacia=...`.
3. O controller devolve `{"tela": "farmacia/estoque.html", "dados": {...}}` — o mesmo
   contexto que a v17 passava ao template.
4. A view registrada para `farmacia/estoque.html` desenha a tela.
5. Formulários e links continuam sendo HTML comum: `PaginaOpme` intercepta e envia
   `POST /api/...` (multipart). A resposta pode trazer `aviso` (faixa verde/vermelha ou
   janela), `redirecionar` e `sessao`.

Arquivos (PDF, CSV, TXT, PNG das etiquetas) e as respostas JSON da bipagem saem sem envelope.

## 4. Autenticação e usuários

Com `AD_URL` preenchida, o login segue esta ordem (nov/2026, versão 17.2.0):

1. O usuário digita o **login e a senha do AD**, e o sistema confere no AD.
2. Se o AD **não confere** → “Usuário ou senha inválidos.” (conta as tentativas para o bloqueio).
3. Se o AD confere e a pessoa **tem perfil ativo** na tabela `usuarios` → entra com esse perfil
   (nome, e-mail e setor são atualizados com os do AD).
4. Se o AD confere e a pessoa **não tem perfil** → o sistema registra sozinho uma
   **solicitação de acesso** com nome, e-mail e setor do AD e avisa na tela. Uma nova tentativa
   não duplica: avisa que a solicitação já está com o administrador.
5. O administrador aprova (escolhendo o perfil) ou recusa em *Administração → Solicitações
   pendentes*. Aprovada, a pessoa entra com a senha de rede.
6. Se o AD estiver fora do ar, a tela diz isso (não diz “senha inválida”).

Outros pontos:

- *Administração → Incluir usuário*: digite o login, **Consultar AD**, escolha o perfil (cadastro direto).
- Com AD, a aba “Solicitar acesso” sai da tela de login (o pedido é automático no primeiro login);
  “Esqueci a senha” e a troca de senha no perfil também só existem sem AD.
- Confirmações com senha (entrega, supervisão, material não cadastrado) aceitam a senha de rede;
  quem não tem perfil é recusado ali — não vira solicitação.
- Desativar um usuário em Administração bloqueia o acesso mesmo com a senha de rede correta.
- Bloqueio por tentativas (`OPME_TENTATIVAS`, `OPME_MINUTOS_BLOQUEIO`) continua valendo.
- Sem `AD_URL`, vale a senha local do TraceOPME (modo de reserva), como na v17.

## 5. Colocando no ar sobre os dados da v17

1. Pare a v17 e faça uma cópia do `data/opme.db`.
2. Em `.env`: `OPME_DB=<caminho do opme.db>`, `OPME_LOG_DIR`, `JWT_SECRET` forte,
   `OPME_ADMIN` (login de rede do administrador) e `AD_URL`/`AD_BASEDN`.
3. `cd frontend && npm install && npm run build && cd ..`
4. `uvicorn src.main:app --host 0.0.0.0 --port 8000` (ou o serviço systemd / `compose.yaml`).
5. Confira `GET /api/health` e entre com o administrador.

Usuários e senhas locais da v17 continuam no banco: sem AD, entram como antes; com AD,
entram com a senha de rede desde que o login seja o mesmo da rede.

## 6. Verificação

- `pytest`: 20 testes, incluindo `tests/opme/test_v17.py` (489 verificações do fluxo
  completo), importação de NF/planilha (89), catálogo de materiais e correção de lote. O
  arquivo `tests/opme/legado.py` desenha os **templates originais da v17** com os dados que
  a API devolve, provando que nada do contexto das telas se perdeu.
- `python audit_framework.py .` → 11/11 pilares (100%).
- Navegação automatizada (Playwright) por todas as telas com os perfis admin, sala,
  farmácia e supervisão, sem erro de console nem de API.

## 7. Ajustes de novembro/2026 (versão 17.1.0)

| # | Pedido | Onde |
|---|---|---|
| 1 | Excluir item cadastrado por engano | *Almoxarifado → Corrigir cadastro*: “Excluir este item” (uma unidade) ou “Excluir cadastro errado” (as unidades marcadas do grupo). Motivo obrigatório. Só sai o que ainda está parado no almoxarifado, sem nenhum movimento além da entrada. Nada é apagado: a unidade fica *Baixado* com o evento `cadastro_excluido` (não conta como perda nos indicadores). Se veio por NF, volta a ficar pendente na nota. |
| 2 | Corrigir a quantidade | *Corrigir cadastro*: “Corrigir a quantidade”. Para menos, saem as últimas unidades cadastradas (mesmas regras da exclusão); para mais, entram unidades com os mesmos dados (só cadastro manual). |
| 3 | Achar o item pelo código bipado | As buscas (Consultas → Itens, Rastreio por lote, Corrigir cadastro, estoque, envio, seleção na bipagem) entendem a etiqueta GS1 inteira: procuram pelo GTIN e mostram o lote/série da etiqueta. A ficha do item explica que o código de barras guardado é o GTIN e mostra como ele aparece na etiqueta. |
| 4 | Código consignado | Campo novo `codigo_consignado` (unidades), obrigatório quando a classificação é *Consignado* no cadastro manual e na entrada por NF; corrigível em *Corrigir cadastro*; aparece na ficha, na busca e no relatório por classificação (tela e CSV). |
| 5 | Quantidade em branco e obrigatória | Cadastro manual: a quantidade começa vazia e é obrigatória; o Enter do leitor só passa para o próximo campo (o cadastro só sai pelo botão). |
| 6 | Aviso de validade mais próxima | Envio almoxarifado → farmácia e dispensação farmácia → sala: se, no mesmo estoque, há lote do mesmo material (AGHU) que vence antes, a tela avisa e pede ciência. Não trava: com a ciência a leitura é registrada e a ciência fica no histórico (`ciencia_validade`). Para passar a travar, mude `services/validade_aviso.py`. |

Testes: `tests/opme/test_ajustes_nov2026.py` (roda dentro do `pytest`).

## 8. Ajustes de novembro/2026 — segunda leva (versão 17.3.0)

| # | Pedido | Onde |
|---|---|---|
| 1 | NF que traz o número de série no campo lote | Na importação do XML, quando o mesmo produto (descrição + cEAN) vem com 2 ou mais lotes, todos com quantidade 1, o lote é tratado como número de série (`nf_itens.lote_e_serie`). Na entrada, o valor vai também para `numero_serie` (o lote continua igual ao da NF). A tela da NF avisa. A etiqueta que traz só a série (`21`) acha a unidade mesmo nas notas antigas (a busca compara a série com o lote, sem a letra do começo). |
| 2 | Cancelar o envio antes da ciência | *Almoxarifado → Enviar para a farmácia → (envio)*: “Cancelar este envio”, com motivo, enquanto a farmácia não deu ciência. Tudo volta ao estoque do almoxarifado; evento `envio_cancelado` em cada item. |
| 3 | Farmácia devolve ao almoxarifado | *Farmácia → Devolver ao almoxarifado*: a farmácia bipa (sai do estoque dela: “Em devolução para o Almoxarifado”, `transito_almoxarifado`) e finaliza. *Almoxarifado → Devoluções das farmácias*: o almoxarifado confere **bipando** ou **pela lista** (“Dar ciência do recebimento”). O não recebido vira pendência: o almoxarifado marca “recebi” se chegou depois; a farmácia registra “voltou ao estoque da farmácia” ou divergência. A farmácia pode cancelar a devolução antes da ciência. Mesma estrutura do envio (`remessas.sentido = 'farmacia_almox'`). |
| 4 | Romaneio da devolução ao fornecedor | *Almoxarifado → Romaneio de devolução ao fornecedor* (também na bipagem “Devolver ao fornecedor”): filtra por período e fornecedor, marca os itens e baixa o PDF com AGHU, código consignado, lote, série, validade, NF, valor e motivo, mais a declaração e a assinatura **pelo hospital** e **pelo fornecedor** (nome, matrícula/documento e data). Um romaneio por fornecedor. |
| 5 | Empenho pelo código consignado | *Consignados → Código consignado × AGHU*: cadastro, edição, busca e importação por planilha da associação (um código consignado → um AGHU). *Cadastrar empenho*: informa os códigos consignados; o AGHU vem da associação (ou é digitado ao lado e a associação é criada). A tabela de empenhos, o detalhe, os vínculos e o PDF mostram os dois números. O débito automático usa o código consignado da unidade; empenhos antigos (só AGHU) continuam valendo. A planilha de empenhos ganhou a coluna “Código consignado”. |

Testes: `tests/opme/test_ajustes_nov2026_b.py` (roda dentro do `pytest`).

### 17.3.1
- Cadastro manual e entrada por NF: ao digitar (ou bipar) o código consignado, o AGHU associado preenche o campo sozinho; se o AGHU digitado for outro, a tela avisa e oferece trocar (`GET /api/almoxarifado/consignado-aghu`).
- Login com AD: texto “Use o mesmo login e senha da rede. No primeiro acesso, se você ainda não tiver perfil, o pedido de acesso será liberado pelo administrador.”
- Rodapé do login e do menu: “Desenvolvido por Camila Corrêa de Melo” e o e-mail de suporte (camila.melo.3@hubrasil.gov.br).


### Planilha da NF para o AGHU (17.3.2 / 17.4.1)
Na tela da nota fiscal (*Cadastro por NF → abrir a nota*), o quadro **Planilha para lançar no AGHU** baixa um Excel com
uma linha por material + lote + validade (quantidade somada): Código AGHU, Código consignado, Lote, Validade, Fornecedor,
Marca e Quantidade. Só entra o que já deu entrada por aquela nota (cadastro excluído não conta). Códigos, lote e
validade vão como texto (o zero à esquerda do lote é mantido; validade dd/mm/aaaa). Serviço: `services/planilha_aghu.py`.

### Paleta "Clínico claro" (17.3.3)
Menu lateral branco com borda fina, fundo `#F4F7F9`, cartões brancos, botões e item ativo no verde-água da marca
`#0F766E` (item ativo com fundo `#E3F2EF`), títulos no marinho `#0C3A67`, texto `#1E2B3A` e login claro em degradê.
As cores de status não mudaram. Tokens em `frontend/src/index.css` e `frontend/src/assets/opme.css`.


## Agenda automática do relatórios (17.3.4 / 17.5.1)
*Procedimentos → Buscar agenda no relatórios*: busca no Metabase (modelo 1703, "Escala prévia definitiva") os
procedimentos do dia escolhido e importa pelo mesmo caminho do CSV (não duplica; completa o pedido de OPME).
Sem usuário de serviço no `.env`, a tela pede a senha de rede (não é gravada). Rotina diária: `AGENDA_AUTOMATICA=1`,
`METABASE_USUARIO`, `METABASE_SENHA`, `AGENDA_HORARIOS` (ex.: 06:00,12:00) e `AGENDA_DIAS` (0 = hoje, 1 = amanhã); se o
sistema for ligado depois de um horário, busca na hora. Cada busca fica em `agenda_buscas` e aparece em "Últimas buscas".
A importação de CSV passou a aceitar nomes de coluna com espaço ou sem acento (ex.: "Dthr Inicio Cirg").
Serviço: `services/agenda_metabase.py`; testes: `tests/test_agenda_metabase.py`.

### 17.3.5 / 17.5.2
Com o AD ligado, o login de rede em `OPME_ADMIN` passa a ser criado como administrador também num banco que já tem
usuários (antes só no banco vazio). Se o usuário já existe, nada muda.


### 17.3.6 / 17.5.3
- Cartões das páginas dos módulos na paleta Clínico claro: fundo branco, título marinho, faixa à esquerda indica o tipo
  (ação, consulta, correção, caixas); pendência em vermelho.
- *Farmácia → Cadastro manual* (`/farmacia/manual`): mesmo formulário do almoxarifado, com o estoque de destino
  (Bloco Cirúrgico ou Hemodinâmica); as unidades entram direto no estoque da farmácia (`em_estoque_farmacia`). Etiqueta
  QR em `/farmacia/etiquetas`.
- Empenhos: com mais de um empenho para o mesmo material, o débito vai primeiro para o de fim de vigência mais próximo
  (sem fim de vigência fica por último).
- Etiqueta GS1 com o lote “grudado” no campo seguinte (ex.: (10)21680129 (91)048, cadastrado como 21680129048) acha só a
  unidade certa; lote igual tem preferência sobre lote parecido.


## v17.3.7 / v17.5.4 — Caixas de consignado no almoxarifado (nov/2026)

- **Almoxarifado → Caixas de consignado** (`/almoxarifado/caixas`): cria a caixa (mesmo código CX-FORN-NN), imprime a etiqueta e bipa para dentro **somente itens do estoque do almoxarifado**.
- **Dispensar para a farmácia**: escolhe Bloco ou Hemodinâmica; os itens vão para `transito_farmacia` e a caixa fica "a caminho". Enquanto está a caminho ninguém mexe no conteúdo; o almoxarifado pode **cancelar o envio** (com motivo) e a caixa volta ao estoque dele.
- **Farmácia dá ciência**: a caixa aparece em "Chegando do almoxarifado — dar ciência" (lista de caixas e aviso na página da Farmácia). Ao dar ciência, os itens entram no estoque daquela farmácia e a caixa passa a ser da farmácia — que completa a caixa e envia para as salas como já fazia.
- Regras: farmácia não edita caixa que está no almoxarifado; almoxarifado só consulta caixa que já está na farmácia; caixa vazia não é dispensada; só a farmácia de destino dá ciência.
- Eventos novos no histórico: `caixa_enviada_farmacia` e `caixa_recebida_farmacia`. Colunas novas em `caixas`: local, envio_farmacia, enviada_em/por, recebida_em/por/nome (criadas sozinhas na inicialização).
- Código: `services/caixas_almox.py`; rotas em `routers/almoxarifado.py` (reaproveitam as funções de caixa do `farmacia_controller` com `modulo`/`base`); `POST /farmacia/caixas-consignado/{id}/receber`. Testes: `tests/test_caixas_almox.py`.

- **v17.3.8 / v17.5.5**: importação da agenda decide o separador (";", tab ou ",") pela linha do cabeçalho. Corrige "Faltam colunas obrigatórias" na busca do relatórios, quando as vírgulas dentro dos campos confundiam a detecção automática.

- **v17.3.9 / v17.5.6**: busca no relatórios — colunas de lista (solicitacao_especial, opme) agora são gravadas no formato do AGHU e o pedido de OPME é reconhecido (aspas simples ou duplas; coluna `opme` própria). Buscar de novo o mesmo dia completa o OPME dos atendimentos já importados. A última busca fica salva em data/ultima_agenda_relatorios.csv para conferência.

- **v17.3.10 / v17.5.7**: tela Procedimentos mostra todos os procedimentos importados, de todas as unidades (Endoscopia, Centro Obstétrico, Bloco Dermato, Cardiologia PDT inclusive), com ou sem OPME. O filtro "só com OPME" saiu da tela; o seletor de unidade lista todas. Sala de procedimento e Farmácia continuam com Bloco e Hemodinâmica.

- **v17.3.11 / v17.5.8**: tela Procedimentos ganha o botão "Cancelado" (mesma regra da Sala de procedimento: atendimento aberto, sem uso registrado; abre a ficha no cancelamento).

- **v17.3.12 / v17.5.9**: seleção sem bipar ("Selecionar pelo código AGHU ou nome") — o campo aceita o código AGHU ou o nome do material; as opções aparecem enquanto se digita (a partir de 3 letras; cada palavra precisa estar na descrição do hospital ou do fornecedor). Grupos por AGHU + lote + validade, até 40 opções.
- Mesma versão: "Material não cadastrado no sistema" simplificado — pesquisa o material pelo nome/AGHU (preenche descrição, AGHU, fornecedor e marca a partir do estoque ou do catálogo) e a sala só informa lote, validade, quantidade e motivo ("Detalhe" só aparece em "Outro"). "Não achou?" abre os campos à mão. Etiqueta passa a ser colada no formulário de rastreabilidade. Rota GET /sala-procedimento/nao-cadastrado/buscar.

- **v17.3.13 / v17.5.10**: Almoxarifado reorganizado em 3 linhas de 4 — (1) entrada e cadastro em verde-água: NF, manual, planilha, corrigir cadastro; (2) farmácias: enviar e devoluções em marinho, caixas (lilás) e etiquetas (verde-água); (3) devolver ao fornecedor e romaneio em âmbar, estoque e relatório de dispensas em azul-acinzentado. Nova cor `cor-marinho` e classe `linha-cartoes`. Na versão submenu, o menu do Almoxarifado segue a mesma ordem.

- **v17.3.14 / v17.5.11**: Farmácia reorganizada em linhas — (1) receber do almoxarifado (marinho), solicitações e dispensar (verde-água), aguardando a sala (azul-acinzentado); (2) procedimentos a concluir, usos sem dispensação, não utilizados e conciliação (âmbar); (3) caixas de consignado (lilás), caixas nas salas e bloqueadas (vinho, `cor-vinho`); (4) estoque, cadastro manual, devoluções recebidas, devolver ao almoxarifado e relatório de dispensas (cores de antes; linha de 5). Submenu: menu da Farmácia na mesma ordem.
- **v17.3.15 / v17.5.12**: "Devolver ao almoxarifado" passa para a 3ª linha da Farmácia (ao lado das caixas); a 4ª linha volta a ter 4 cartões.
- **v17.3.16 / v17.5.13**: cartões pintados com um tom claro da sua cor (verde-água, marinho, azul-acinzentado, lilás, vinho, âmbar), faixa esquerda de 5px; pendência ("alta") em rosa claro com faixa vermelha.
- **v17.3.17 / v17.5.14**: cadastro manual (almoxarifado e farmácia) recusa validade anterior a hoje (calendário com mínimo = hoje e conferência no servidor); saiu o texto sobre linhas de números de série. Entrada por NF: item com validade em menos de 30 dias (ou vencido) fica em vermelho, em menos de 1 ano em amarelo.
- **v17.3.18 / v17.5.15**: (a) foto da etiqueta pela câmera, opcional, no "Material não cadastrado" (componente `FotoEtiqueta.vue`: câmera do computador quando o navegador permite — https ou 127.0.0.1 — senão escolher imagem; reduzida para JPEG ~1400px). Com a foto, a caixinha "etiqueta colada" passa a ser opcional. Foto em data/fotos_etiquetas, coluna `nao_cadastrados.foto`, visível na Sala e em Almoxarifado → Material não cadastrado. (b) "Reportar problema": botão no topo de todas as telas; o usuário descreve, anexa imagem (opcional) e vira chamado (tabela `chamados`, imagens em data/chamados). Administração → card Chamados → /chamados: responder e mudar a situação (aberto, em andamento, resolvido); quem abriu vê a resposta na janela. Imagens não entram na trilha de auditoria.
- **v17.3.19 / v17.5.16**: Material não cadastrado — a sala só precisa de lote e validade (+ quantidade, motivo, etiqueta/foto e senha da supervisão). A pesquisa pelo nome ficou opcional e saíram os campos de descrição, AGHU, fornecedor, marca e código de barras. Sem material escolhido, grava "MATERIAL NÃO IDENTIFICADO (ver etiqueta)" / fornecedor "NÃO INFORMADO"; o almoxarifado completa descrição, fornecedor e marca ao regularizar (descrição obrigatória nesse caso).
- **v17.3.20 / v17.5.17**: Material não cadastrado não exige mais a senha da supervisão (fica registrado quem lançou; `autorizado_por` = o próprio usuário).
- **v17.3.21 / v17.5.18**: planilha "Planilha para lançar no AGHU" ganha as colunas Nº NF, Série (tirada da chave da NF-e), Valor unitário e Valor total (linhas agrupadas também por valor unitário). Usada pelo robô `robo_nota_aghu` (fora do TraceOPME), que lança a Nota de Recebimento sem AF no AGHU — material, marca do TraceOPME, almoxarifado 1, unidade UN, valor e lotes/validades — e para antes de gravar.
- **v17.3.22 / v17.5.19**: login pelo AD mais robusto — a senha é provada pelo bind; se a busca dos dados da pessoa falhar (AD_BASEDN errado ou sem permissão de leitura) o login segue com dados mínimos e tenta também o defaultNamingContext do servidor. Senha expirada/conta bloqueada no AD contam como senha inválida. Falha de rede mostra o motivo real ("Detalhe técnico") na tela e no log; timeout de 10 s.
- **v17.3.23 / v17.5.20**: robô do AGHU integrado. Tela da NF ganha o cartão "Lançar no AGHU" (em destaque quando a entrada termina — ao dar entrada no último item o sistema já leva até ele). O botão gera a planilha em data/aghu, abre `ferramentas/robo_nota_aghu` numa janela própria (mesmo computador) com um código de uso único; no fim o robô pergunta se a nota foi gravada e responde em POST /api/robo-aghu/retorno (só 127.0.0.1 + código). A NF fica "lançada no AGHU" com data, quem lançou e nº da nota de recebimento; dá para marcar/desfazer à mão. Lista "Falta lançar no AGHU" na Entrada por NF e aviso no card do Almoxarifado. Instalação do robô: instalar_robo_aghu.bat (playwright, requirements-robo.txt). .env: AGHU_URL, AGHU_NAVEGADOR.
- **v17.3.24 / v17.5.21**: robô do AGHU — caminho da planilha passa a ser absoluto (o robô abre em outra pasta e não achava "data\\aghu\\..."); mesmo material com vários lotes entra UMA vez, com todos os lotes embaixo (agrupa só pelo código AGHU; avisa se a planilha tiver marcas diferentes); se o material já estiver na nota, não inclui de novo e só adiciona os lotes que faltam.
- **v17.3.25 / v17.5.22**: robô do AGHU passa a rodar no COMPUTADOR DE QUEM LANÇA (TraceOPME no servidor). O botão "Lançar no AGHU agora" pede ao servidor um link `traceopme-aghu://lancar/<bloco base64url>` (servidor como o navegador o enxerga, chave, código de uso único, AGHU_URL/AGHU_NAVEGADOR) e o navegador entrega ao robô. O robô baixa a planilha em GET /api/robo-aghu/planilha (código) e responde em POST /api/robo-aghu/retorno (código vale uma vez; aceita de qualquer computador da rede). Instalador do robô baixado na tela da NF (/almoxarifado/robo-aghu/instalador): instalar.bat cria o ambiente, instala playwright+openpyxl e registra o protocolo traceopme-aghu no Windows do usuário (HKCU). No servidor não se instala nada do robô (saíram instalar_robo_aghu.bat e requirements-robo.txt).
- **v17.3.26 / v17.5.23**: instalador do robô do AGHU sem depender de .bat (o Controle de Aplicativo Inteligente do Windows 11 bloqueia .bat baixado): instalar.py (py instalar.py pelo cmd) cria o .venv, instala playwright/openpyxl e registra o protocolo traceopme-aghu apontando direto para o python.exe do robô; instalar.bat só chama o instalar.py.

## v18.0.0 — melhorias pedidas em nov/2026 (documento "melhorias no sistema")

Itens 1 e 2 (procedimentos pelo AGHU e nome do paciente pelo prontuário) ficaram para depois, a pedido.

| Item | O que mudou |
|---|---|
| 3 | Validade obrigatória no cadastro manual e na entrada por NF (saiu a opção "material sem validade"). |
| 4 | Busca por código: quando algum material tem exatamente o código bipado/digitado, só ele aparece ("abc" não traz mais "abc2"). `busca.preferir_exatos`. |
| 5/6 | Devolução ao fornecedor com número (`DEV-AAAA-NNNN`), uma por fornecedor. Lista por devolução (período, fornecedor, situação), ficha com os itens, PDF do romaneio por devolução, finalizar, tirar item e cancelar a devolução inteira (itens voltam ao estoque de onde saíram). Tabelas `devolucoes_fornecedor` e `devolucao_fornecedor_itens`; o histórico antigo é agrupado por fornecedor + dia + usuário. |
| 7 | Procedimento cancelado depois da ciência da sala: o material vai para "Não utilizados — dar ciência" da farmácia (não cai direto no estoque). Sem a ciência da sala, volta direto ao estoque da farmácia. |
| 8 | Estorno depois de encerrado (ex.: bip em duplicidade) não precisa mais da supervisão: o item volta pela farmácia, que dá ciência. |
| 9 | Bipagem da sala: "O material caiu ou veio com problema?" antes do bip, e "⚠ sinalizar problema" em cada item depois do bip (motivo + detalhe). Evento `avaria_sinalizada` e alerta para o almoxarifado. |
| 10 | Consulta por prontuário com filtro por dia/período e "Abrir ficha". |
| 11 | Estornar uso por paciente: lista por prontuário/período → ficha do paciente → estornar cada item. |
| 12 | Transferência entre farmácias (Bloco ↔ Hemodinâmica): `remessas.sentido = 'farmacia_farmacia'`, coluna `remessas.farmacia_origem`. A origem bipa e finaliza; o destino confere e dá ciência em "Receber material"; a origem cancela antes da ciência e trata os não recebidos (voltou à origem / divergência). |
| 13 | Código master: a tela de Administração aceita também a planilha só com "Código AGHU" → "Código master". O master aparece na ficha do item, entra na planilha da NF para o AGHU (2ª coluna) e o robô procura o material no AGHU pelo master (sem master, usa o AGHU). |
| 14 | Etiqueta GS1 dividida em duas: o material cadastrado pela etiqueta completa é achado bipando só a etiqueta do GTIN `(01)` ou só a de validade/lote `(17)(10)(91)`. Corrigida a leitura do GTIN sozinho sem parênteses (`01` + 14 dígitos). |

Testes novos: `tests/test_v18_*.py`.

## v18.1.0 — Central das salas e alerta de solicitação por farmácia

* **Alerta de "Solicitar OPME" por farmácia.** Com a unidade da farmácia escolhida, o alerta mostra só os pedidos dela (já era assim). Sem unidade escolhida, em vez de somar Bloco + Hemodinâmica num alerta só, aparece um alerta por farmácia, com o botão "Atender (…)" — que escolhe a unidade e abre os pedidos dela. Daí em diante aquele navegador só vê os pedidos daquela farmácia.
* **Central das salas** (menu novo, módulo `monitoramento`; perfis: admin, farmácia, sala, supervisão e gestão). Só leitura, montada com o que já é registrado (`services/monitoramento.py`):
  * um cartão por sala (Bloco 01–10, 12, 17; Hemodinâmica 01), com a cor da situação: sem procedimento, agendado, sala aberta, aguardando a farmácia, material na sala, em uso (bipando), finalizado (falta a farmácia), concluído;
  * em cada cartão: paciente (primeiro nome + inicial), prontuário, especialidade, as 6 etapas com a hora de cada uma, há quanto tempo a sala está aberta, quantos itens foram bipados e o último bip, e os procedimentos do dia da sala;
  * alertas: pedido de OPME sem atendimento há 30 min ou mais, dispensação não confirmada pela sala há 30 min ou mais, material com problema sinalizado e não utilizados aguardando a farmácia;
  * números do momento, linha do tempo do dia (uma barra por procedimento, tracinhos = bips, linha vermelha = agora) e painel lateral com tudo o que aconteceu no procedimento;
  * atualiza sozinha a cada 30 s, filtro por unidade e dia, e **Modo TV** (tela cheia, fundo escuro) para deixar num monitor.
  * "Sala aberta" = a primeira ação registrada no procedimento (pedido, dispensação, recebimento, bip...). Não há botão próprio de abrir sala.

## v18.2.0 — ciência do retorno com a lista inteira (usado × voltou)

* **Não utilizados — dar ciência** (`/devolucoes/{id}`): a farmácia vê tudo o que foi para o paciente (dispensado, inclusive itens de caixa, e o que foi usado sem dispensação), agrupado por material. Cada item vem marcado: **usado no paciente** (hora e quem bipou), **voltando** (conferir pela lista ou bipando), **volta na caixa**, **já voltou antes** ou **sem destino** (não usado e não está voltando — alerta). Contadores no topo: foram para o paciente, usados, conferidos de volta, sem destino. Na caixa da lista, mostra a contagem da sala × o que o sistema espera. `devolucoes.balanco()`.
* **Caixa na sala — conferir o retorno** (`/farmacia/caixas-sala/{id}`): uma lista só, por material, com o que a caixa levou; o usado já vem marcado (prontuário, paciente, hora, quem). Confere-se o resto pela lista (tudo marcado; desmarca o que não voltou) ou **bipando** cada item que voltou (`/farmacia/caixas-sala/{id}/identificar`). O que não voltar bloqueia a caixa, como antes.

## v18.3.0 — Abrir sala, etapas novas na Central e chamados para o QG da enfermagem

* **Abrir sala** (ficha do procedimento na Sala de procedimento): botão "▶ Abrir sala"; colunas `atendimentos.sala_aberta_em/por/auto`. Logo abaixo, a trilha das 6 etapas e o "próximo passo" (dar ciência do material recebido → registrar uso → finalizar a sala). Se a sala der ciência ou bipar sem ter clicado, a abertura é registrada sozinha naquele momento e marcada como automática.
* **Etapas da Central** (`services/monitoramento.py`): 1 Sala aberta · 2 Ciência do material · 3 Uso do material · 4 Sala finalizada · 5 Conferência da farmácia · 6 Concluído. Pedido de OPME em aberto é alerta (amarelo; vermelho depois de 30 min), não etapa.
* **Sobreposição**: depois que a sala finaliza, o procedimento sai do cartão principal e vai para a faixa "conferência da farmácia" da mesma sala. O cartão mostra o paciente que está na sala agora (ou o próximo agendado) e, à parte, os que a farmácia ainda confere. Sem ninguém na sala: "Sala livre · farmácia conferindo".
* **Chamados (maqueiro / limpeza)**: na ficha do procedimento, "Chamar maqueiro" e "Chamar limpeza", com motivo e observação; a sala acompanha a situação e pode cancelar. Tabela `chamados_sala`, serviço `services/chamados_sala.py` (o `services/chamados.py` continua sendo o "Reportar problema").
* **QG da enfermagem** (menu novo `/qg`, módulo `qg`; papel novo **"QG da enfermagem"**, e também admin, supervisão e gestão): quadro com Aguardando / A caminho / Hoje, atualiza a cada 15 s com aviso sonoro quando chega chamado novo; "Direcionar" (nome do maqueiro / da equipe, com sugestão dos nomes já usados), "Atendido", "trocar pessoa", "cancelar"; tempo de espera e tempo médio do dia. Os chamados abertos aparecem também nos cartões da Central das salas.

### v18.3.1 — a sala é aberta na aba da Sala de procedimento

* Card novo **"Abrir sala"** no início da Sala de procedimento → tela **Salas** (`/sala-procedimento/salas`): um cartão por sala; sala sem paciente mostra os agendados com "▶ Abrir sala"; sala aberta mostra o paciente, as etapas e os botões do próximo passo (dar ciência do material recebido, registrar uso, finalizar a sala) e "Chamar maqueiro / limpeza".
* Depois de "Abrir sala", o sistema vai direto para a **ciência do material recebido** (se a farmácia já mandou).
* A sala **só dá ciência do material com a sala aberta** (a tela de ciência mostra "1º passo: abrir a sala"). Uma sala abre para um paciente por vez: o anterior precisa ter sido finalizado pela sala (a conferência da farmácia pode continuar).
* Central das salas e QG: só acompanhamento — sem link para agir na ficha e sem o alerta de solicitação da farmácia no topo.

## v18.4.0 — Cópia de segurança diária e fora do servidor

* A cópia do banco passa a ser feita **todo dia no horário `BACKUP_HORA`** (padrão 02:00), por uma rotina que roda com a aplicação, mesmo que ela fique semanas sem reiniciar (antes, só ao abrir).
* Cada cópia é **conferida** (`PRAGMA integrity_check` + contagem de unidades); cópia com defeito é marcada `.defeito` e não vale.
* A cópia vai também para **`BACKUP_PASTA_EXTERNA`** (pasta de rede fora do servidor), guardando `BACKUP_EXTERNO_MANTER` cópias. Se a rede falhar, tenta de novo a cada 30 min.
* **Administração → Cópia de segurança** mostra as duas cópias (servidor e rede), com data, conferência e erro, em verde/vermelho. "Gerar cópia agora" faz as duas.
* Instruções de restauração em `RESTAURAR_BACKUP.txt`.

### v18.4.1 — correções da auditoria (concorrência e recall)

Reproduzidos em teste (falham na 18.4.0, passam na 18.4.1 — `tests/test_v18_4_concorrencia.py`):

* **Duas finalizações simultâneas** do mesmo atendimento gravavam duas vezes (2 eventos `uso_finalizado`, 2 linhas de devolução da mesma unidade). Agora a finalização confere, dentro da transação, que o atendimento ainda não foi finalizado; a segunda é recusada.
* **Duas bipagens simultâneas da mesma unidade** na remessa criavam 2 `remessa_itens` e 2 eventos de envio. Agora a unidade só se move se ainda estiver na origem (conferido dentro da transação); a segunda recebe "bipe de novo". A remessa também precisa estar aberta no momento da gravação.
* **Lote em recall era enviado à farmácia** pela remessa. Agora envio e transferência recusam lote bloqueado (a devolução ao almoxarifado continua liberada). Caixa com item de lote em recall não é dispensada nem enviada à sala.
* Encontrado na revisão: **duas ciências simultâneas da mesma devolução** (não utilizados) também processavam duas vezes. Corrigido do mesmo jeito.
* Segunda linha de defesa no banco: índices únicos impedem a mesma unidade "pendente" duas vezes em `remessa_itens` e em `devolucao_itens` (criados só se o banco não tiver duplicidade antiga; senão, aviso no log).
* Envio de caixa para a sala e dispensação de caixa passam a ler e gravar na mesma transação.

### v18.4.2 — segunda rodada da auditoria

Reproduzidos em teste (falham na 18.4.1, passam na 18.4.2):

* **Material vencido era enviado do almoxarifado para a farmácia.** Envio e transferência entre farmácias recusam lote vencido (devolução ao almoxarifado segue liberada). Caixa com item vencido não é dispensada nem enviada à sala.
* **Recall registrado entre a conferência e a gravação** ainda passava. A conferência do recall agora é feita de novo DENTRO da transação que move o material (remessa, caixa para a sala, caixa para o paciente).
* **Backup não incluía o `app.db`** (banco administrativo do framework). A cópia diária agora leva os dois (`opme_AAAA-MM-DD.db` e `app_AAAA-MM-DD.db`), no servidor e na pasta de rede; a Administração mostra a situação do app.db.
* **Rotas de estorno de uso e de tratamento de pendências quebravam** (erro 500: `EM_ESTOQUE_RECEBIMENTO` não importado nos routers). Corrigido, e um teste novo roda o pyflakes em todo o código para pegar nome indefinido antes de chegar ao servidor.

### v18.4.3 — orientação de senha padronizada e "não recebido" com conferência

* **Textos sobre senha**: a sala confirma o recebimento com o **usuário logado** (desde a v17), mas algumas telas ainda falavam em "digitar a própria senha". Padronizado para "Confira os materiais e confirme o recebimento com seu usuário" (sala, farmácia, bipagem). A senha continua só onde é de fato pedida: reabertura de procedimento pela supervisão.
* **Não recebido pela sala**: antes voltava direto ao estoque disponível da farmácia — um material extraviado no caminho reaparecia como disponível. Agora fica com o status novo **"Não recebido — aguardando conferência da farmácia"** (`nao_recebido_conferir`), fora do estoque disponível. A farmácia confere em **Farmácia → Não recebidos pela sala** (card aparece no menu quando há item): *localizado* (volta ao estoque), *estava na sala* (registra o recebimento, se o procedimento ainda está aberto) ou *não localizado* (extravio → divergência, com descrição obrigatória).

### v18.8.2 — solicitação cancelada não volta ao pedir de novo

- Depois que a sala cancela a solicitação de OPME, um pedido novo reabre a solicitação só com
  os materiais pedidos agora; os itens cancelados não voltam a ficar em aberto. Eles ficam
  registrados no evento do cancelamento (`solicitacao_cancelada`).

### v18.8.1 — robô da NF busca o material pelo código AGHU

- Na Nota de Recebimento sem AF, o robô passa a buscar o material pelo **código AGHU** (antes
  usava o código master quando a planilha tinha). A coluna "Código master" continua na
  planilha, só para consulta.

### v18.8.0 — Requisição de Material (RM) no AGHU, com lote

- Farmácia → **Nota de consumo e RM (AGHU)**: cada paciente tem dois documentos, cada um com a
  sua situação (não lançada / em lançamento / lançada) e o seu botão "Lançar no AGHU":
  **Nota de consumo** (como na 18.7) e **Requisição de material (RM)**. A tabela mostra a
  quantidade por lote ("GB2411 (1) · GB2415 (1)").
- Robô da RM (o mesmo robô instalado; link com `k = "rm"`; passos em
  `ferramentas/robo_nota_aghu/passos_rm.py`):
  1. **Geração/Alteração de Requisição de Material** — a pessoa preenche o cabeçalho (CA,
     almoxarifado, grupo) e vincula o paciente; o robô confere o prontuário e inclui cada
     material (sugestão pelo código AGHU + quantidade + botão Gravar do item). A pessoa clica
     em Confirmar e em Acessar Efetivação de RM.
  2. **Efetivar Requisição Material** — para cada material, o robô seleciona o item, marca no
     Controle de Validade o **lote usado no paciente** (bipado no TraceOPME) e preenche a
     quantidade atendida. Lote que não aparece no AGHU, ou com saldo menor, vira aviso para
     marcar à mão. A pessoa confere e clica em Efetivar.
- `GET /api/robo-aghu/consumo?tipo=rm` devolve, por material, os lotes e a quantidade de cada
  lote; `/api/robo-aghu/retorno` aceita `tipo = "rm"`. O código de uso único é separado por
  documento. Colunas novas em `atendimentos`: `aghu_rm_status`, `aghu_rm_iniciado_em/por`,
  `aghu_rm_lancado_em/por`, `aghu_rm_token`, `aghu_rm_token_expira`.
- Nos computadores: atualizar o robô (3 arquivos: `robo_nota_aghu.py`, `passos_consumo.py`,
  `passos_rm.py`) ou baixar o instalador de novo.

### v18.7.3 — sala cancela a solicitação de OPME; alerta de pedidos só na farmácia

- Ficha do paciente (Sala de procedimento) → Outras ações → **Cancelar a solicitação de OPME**,
  com motivo. O pedido sai da farmácia na hora (alerta e lista de solicitações); o que já foi
  dispensado continua com o paciente. Fica registrado (evento `solicitacao_cancelada`, quem,
  quando e motivo). Se a sala voltar a pedir, a solicitação reabre. Coluna nova:
  `solicitacoes.motivo_cancelamento`. Rota: `POST /sala-procedimento/atendimento/{id}/solicitacao/cancelar`.
- O aviso "solicitação(ões) de OPME em aberto" aparece **só nas telas da Farmácia** (farmácia,
  dispensação, devolução) — não mais na Sala de procedimento nem em Procedimentos, mesmo para
  quem também tem acesso à farmácia (admin).

### v18.7.2 — robô: clicar duas vezes não invalida mais o robô aberto

- "Lançar no AGHU" clicado de novo (ou o navegador abrindo o link duas vezes) gerava um código
  novo e o robô já aberto recebia "HTTP Error 403". Agora, enquanto o lançamento está aberto e o
  código vale, o mesmo código é reaproveitado (NF e nota de consumo).
- Quando o TraceOPME recusa o robô, a janela preta mostra o motivo (ex.: código já usado).

### v18.7.1 — robô: planilha travada não para mais o lançamento

- Se a planilha da NF de um lançamento anterior estiver aberta no Excel (o Windows trava o
  arquivo), o robô salva a nova com outro nome (com data e hora) ou na pasta temporária, em vez
  de parar com "PermissionError".

### v18.7.0 — robôs do AGHU de volta no computador de quem lança

- A tela do AGHU dentro do TraceOPME (robô no servidor, 18.5) ficou lenta. Os dois robôs voltam
  a rodar **no computador** (janela preta + navegador do próprio computador), como antes:
  - **NF**: "Lançar no AGHU agora" na tela da NF volta a chamar o robô instalado.
  - **Nota de consumo**: "Lançar no AGHU" em Farmácia → Nota de consumo chama o **mesmo** robô
    instalado (link `traceopme-aghu://lancar/…` com `k = "consumo"`). Ele busca os materiais em
    `GET /api/robo-aghu/consumo` (código de uso único) e avisa no fim em `/api/robo-aghu/retorno`
    (`tipo = "consumo"`). Passos em `ferramentas/robo_nota_aghu/passos_consumo.py`.
- Quem já instalou o robô da NF precisa **reinstalar uma vez** (baixar o instalador de novo e
  rodar instalar.bat) para ganhar a nota de consumo. Instalador também em Farmácia → Nota de consumo.
- O servidor não precisa mais do Playwright/Edge (saiu do requirements.txt e do instalar.bat). O
  código do robô no servidor continua no projeto, mas nenhuma tela o chama.
- Colunas novas em `atendimentos`: `aghu_consumo_token`, `aghu_consumo_token_expira`.

### v18.6.0 — Nota de Consumo no AGHU (farmácia)

- Nova tela **Farmácia → Nota de consumo (AGHU)** (`/farmacia/nota-consumo`): prontuários com
  material utilizado na data (da farmácia escolhida), com tudo o que foi bipado em cada
  paciente somado por código AGHU, lotes e situação (não lançada / em lançamento / lançada).
  Itens sem código AGHU aparecem em vermelho (o robô não lança; inclua à mão).
- **Lançar no AGHU** abre o robô no servidor (mesma tela da NF). A pessoa faz o login, abre a
  Nota de Consumo, pesquisa o prontuário, abre a cirurgia e clica em Materiais Consumidos.
  O robô confere paciente e data, e para cada material: se já está na lista do AGHU sem
  quantidade, preenche a quantidade; se não está, busca pelo código, escolhe a sugestão
  exata e clica em Adicionar. Não grava — no fim a pessoa confere e clica em Gravar.
- Usa o **código AGHU** do material (o mesmo digitado na tela de Materiais Consumidos).
- Colunas novas em `atendimentos`: `aghu_consumo_status`, `aghu_consumo_iniciado_em/por`,
  `aghu_consumo_lancado_em/por`. "Marcar à mão" (Já lancei / Desfazer) na lista.
- Cartão novo no painel da Farmácia com os prontuários do dia ainda não lançados.

### v18.5.1 — tela do AGHU maior e mais rápida

- A tela do AGHU ocupa a janela inteira (barra de cima com a pergunta do robô e os botões;
  log recolhido na barra de baixo) e tem o botão "Tela cheia". O navegador do servidor usa o
  tamanho da área da página, então a imagem aparece em tamanho real, nítida.
- A imagem vem em fluxo contínuo (`GET /almoxarifado/robo-web/{sessao}/fluxo`) e só quando a
  tela muda (screencast do navegador), em vez de a página pedir uma foto a cada instante.
- Passar o mouse também chega ao AGHU (menus que abrem ao passar o mouse).
- O robô continua sem navegar pelo menu do AGHU: a pessoa abre a tela da nota e escolhe a NF.

### v18.5.0 — robô do AGHU no servidor (sem instalar nada no computador)

- O botão "Lançar no AGHU agora" (tela da NF) abre a página **Lançar no AGHU**: o robô roda
  no servidor e a tela do AGHU aparece dentro do TraceOPME. A pessoa clica e digita nela (é
  assim que faz o login), responde às perguntas do robô em botões e acompanha o log ao lado.
  Sem Python, sem instalador e sem janela preta no computador.
- Os passos de preenchimento são os mesmos do robô instalado (`ferramentas/robo_nota_aghu`);
  só a conversa mudou (`services/aghu_remoto.py`). O robô continua sem gravar a nota.
- O que é digitado na tela do AGHU (senha) não vai para log, banco nem auditoria — as rotas de
  teclado/clique não são auditadas.
- Rotas: `GET /almoxarifado/nf/{chave}/aghu/web`, `POST …/aghu/web/iniciar`,
  `GET /almoxarifado/robo-web/{sessao}/estado|tela`, `POST …/entrada|responder|cancelar`.
- Servidor: precisa acessar o AGHU na rede e ter o Edge (ou Chrome) instalado; pacote
  `playwright` em requirements.txt. Variáveis: `AGHU_URL`, `AGHU_NAVEGADOR_SERVIDOR`, `AGHU_ROBO_MAX`.
- O robô instalado no computador continua disponível em "Robô instalado no computador (modo antigo)".

### v18.4.7 — problema na sala vira indicador; código master sem ponto; consignado pelo AGHU

- Material com problema na sala (caiu, danificado, defeito) continua registrado no histórico
  (`avaria_sinalizada`), mas **não gera mais alerta** para o almoxarifado. Novo bloco
  "Problemas com material na sala" em Indicadores → Qualidade (por motivo, material,
  fornecedor e sala, com os registros do período).
- Planilha MasterTools: o ponto do código master é ignorado ("1.234" → 1234, "22." → 22). Os
  códigos já gravados com ponto são limpos ao abrir o sistema.
- Entrada de consignado (NF e cadastro manual): o código consignado não é mais digitado. Vem
  da relação Código consignado × AGHU (Consignados → Código consignado × AGHU, com importação
  por planilha). Se o AGHU tiver mais de um código, usa o do fornecedor; se não der para decidir,
  a tela mostra a lista para escolher. Sem relação, a entrada é recusada com a orientação.

### v18.4.6 — lista de atendimentos sem cartão duplicado

- Atendimento com material ainda aguardando a confirmação da sala não entra mais em
  "falta finalizar" (`atendimentos.a_concluir`): o próximo passo dele é confirmar o recebimento.
- A tela de atendimentos (inclusive a de Registrar uso) não tem mais o cartão "Falta finalizar
  os materiais utilizados": a lista mostra a etiqueta "falta finalizar o registro de uso" e o
  botão "Finalizar" no próprio atendimento. Os de outras datas aparecem num aviso de uma linha.

### v18.4.5 — conferência do "não recebido", caixas e backup

- **Recebimento tardio** ("Estava na sala"): além da unidade, o item da dispensação passa a
  `recebido`, com `tratativa = recebido_na_conferencia` (a divergência inicial continua no
  evento `nao_recebido_sala`). Os demais desfechos gravam a tratativa (`localizado_farmacia`,
  `recolhido_apos_finalizacao`, `extravio`). Colunas novas em `dispensacao_itens`:
  `tratativa`, `tratativa_em`, `tratativa_por`.
- **Depois da finalização do registro de uso**, "Estava na sala" é recusado. Nova tratativa
  "Estava na sala, mas o uso já foi finalizado — recolhido à farmácia": exige o local/quem
  recolheu, devolve ao estoque e registra a conciliação no histórico.
- **Só a farmácia dona do material** (a farmácia em que o usuário está trabalhando) confere o
  não recebido.
- **Caixa não recebida** fica `nao_recebido_conferir` até todas as unidades serem conferidas.
- Relatório de dispensações: "sala não recebeu — aguardando conferência da farmácia" e o
  resultado da conferência.
- **Backup**: o indicador geral só fica verde com a cópia conferida do `app.db`; se ela falhar,
  o sistema tenta de novo a cada 30 min. Pasta externa não configurada gera aviso no log.
- **Ficha da sala**: um só painel de rotina ("Próxima ação"); solicitação de OPME e estorno em
  "Outras ações"; o cartão de baixo virou "Consultas e histórico" (horários da sala recolhidos).

### v18.4.4 — linguagem da finalização e rotina da enfermagem mais simples

* **Devolução ≠ retorno físico**: a finalização passa a dizer que os materiais selecionados "serão registrados como pendentes de devolução à farmácia — encaminhe-os fisicamente para conferência e confirmação do recebimento".
* **Um nome só para a mesma etapa**: botão "Finalizar registro de uso e devoluções" em todas as telas; conclusão "Sala liberada — aguardando conferência da farmácia"; na Central, etapa "Uso e devoluções finalizados".
* **Excluir bip**: a confirmação não promete mais "volta ao estoque do almoxarifado" (o item dispensado continua na sala); texto neutro: "O material retornará à situação anterior permitida pelo sistema. A correção ficará registrada no histórico."
* **Caixa conta pelas unidades**: a confirmação da finalização soma os itens de dentro da caixa (caixa com 20 itens = 20 materiais), tanto no que fica com o paciente quanto no que fica pendente de devolução.
* **Próxima ação na ficha do paciente**: Receber → Utilizar → Finalizar, com uma ação principal por vez (Abrir sala / Confirmar materiais recebidos; Registrar uso; Finalizar). Solicitar OPME, chamar maqueiro/limpeza e estornar ficam em "Outras ações" (aberto sozinho quando há chamado em andamento).

## v18.9.0 (nov/2026) — ajustes do documento "Considerações do aplicativo"

- Registrar uso só com a sala aberta (`fluxo.bipar` devolve `sala_fechada`; a tela leva para a ficha → "Abrir sala"). Acabou a abertura automática no primeiro bip.
- Solicitação cancelada: cada linha mostra "cancelado · N já dispensado(s)" e o aviso lembra que o dispensado continua com o paciente.
- Envio do almoxarifado: removido o texto de ajuda abaixo do campo de bipagem.
- Registrar uso: o quadro "O material caiu ou veio com problema?" fica acima do campo de código.
- Central: "Sala liberada — aguardando conferência" e "Sala livre · farmácia conferindo" viraram um só estado: "Sala liberada · farmácia conferindo" (roxo).
- Hubs: almoxarifado sem subtítulo e sem numeração; farmácia sem subtítulo, sem "Relatório de dispensas" (continua em Consultas) e com cartões na nova ordem.
- Sem mudança no robô local nem no banco.

## v18.10.0 (nov/2026) — usabilidade

- Atualização automática (45 s) nas telas de acompanhamento (hubs, receber, solicitações, dispensações, pendências da farmácia, salas, procedimentos, QG). Só troca os dados; pausa quando a pessoa está digitando, mexeu em campo, tem detalhe aberto ou a aba está escondida. Mudança nos números → selo "Houve mudança nesta tela" + som curto. Lista em `TELAS_AUTO` (frontend/src/views/opme/telas.ts).
- Registrar uso com a sala fechada: a tela abre com o campo travado e o botão "▶ Abrir sala agora" (POST /api/abrir-sala). Não redireciona mais para a ficha.
- Hubs (almoxarifado, farmácia, sala): textos dos cartões encurtados; sala sem subtítulo.
- Confirmação do bip: falha mostra título pelo tipo (MATERIAL VENCIDO, SALA NÃO ABERTA, OUTRO PACIENTE, LOTE DIFERENTE, CÓDIGO NÃO ENCONTRADO, JÁ REGISTRADO, BLOQUEADO) e o motivo em letra grande; registrado com alerta fica amarelo e fica 6 s.

## v18.10.1 — robô da RM

- O robô agora confere se CC Requisição, CC Aplicação e Almoxarifado foram ESCOLHIDOS na lista (campo oculto `_hinput` preenchido) antes de incluir material. Orienta a ordem: vincular o paciente primeiro, depois os CC (vincular depois apaga o CC).
- "Campo obrigatório" ao gravar item: pede para arrumar o cabeçalho e tenta o mesmo material de novo (até 3 vezes). Campo Material bloqueado não derruba mais o robô.
- Efetivação: escolhe a linha do lote pela validade quando o mesmo lote aparece duas vezes e avisa quando a validade do AGHU difere da do TraceOPME. O resumo mostra lote e validade.
- Navegador fechado: mensagem clara em vez de "erro inesperado".

## v18.10.2 — robô da RM preenche o cabeçalho

- Tela "Nova Requisição" em branco: o robô digita o prontuário, clica em Buscar, lista os atendimentos do paciente (pergunta qual se houver mais de um), clica em Selecionar e só DEPOIS escolhe CC Requisição, CC Aplicação e Almoxarifado (o vínculo troca o CC Aplicação pela unidade do paciente).
- Códigos padrão por unidade em `PADRAO_CABECALHO` (passos_rm.py): Hemodinâmica = 31011 / 31047 / 12. Sobrepõe com `[rm] cc_requisicao / cc_aplicacao / almoxarifado` no config.ini. Unidade sem código: a pessoa escolhe aquele campo à mão.
- Erro "selecionar o atendimento correspondente" ao gravar item: vincula e tenta o material de novo.

## v18.10.3 — robô da RM

- CA Requisição fica com a pessoa (escolhe à mão); o robô só confere. Hemodinâmica: CA Aplicação 31047 e Almoxarifado 12.
- "Este paciente não possui atendimentos para selecionar": o robô avisa claramente e espera a pessoa resolver/vincular à mão.
- Abrir o AGHU tenta de novo quando a rede oscila (ERR_NETWORK_CHANGED).

## v18.11.0 (nov/2026) — "Considerações do aplicativo 2"

- Envio/devolução/transferência: o resultado do bip (inclusive "Tirado") aparece logo abaixo do campo de bipar.
- Lote não diferencia maiúscula/minúscula: grupo de escolha = AGHU + lote normalizado + validade (data) — sem separar por marca. Lotes guardados em MAIÚSCULA (padronização dos antigos + gatilhos `trg_lote_mai_*`/`trg_carga_lote_mai_ins`), como no AGHU e nas NF. Planilha do AGHU sai em maiúscula.
- Etiqueta GS1 com lote inexistente: no envio, nunca escolhe sozinho (lista em vermelho "lote da etiqueta NÃO foi encontrado"); em Consultas → Itens rastreados, aviso "Código de barras não encontrado".
- "Unidades por bip": várias unidades do mesmo lote num bip (caixa fechada). Volta para 1 depois de cada bip.

## v18.11.1 — inventário com "Unidades por bip"

- Contagem (almoxarifado e farmácias): campo "Unidades por bip" — conta N unidades iguais num bip (caixa fechada); o resultado resume quantas conferem e quantas são excedente/divergência. Volta para 1 depois de cada bip. Etiqueta GS1 com lote conta primeiro as unidades daquele lote.

## v18.11.2 — caixa de consignado sem fornecedor

- Nova caixa (farmácia e almoxarifado): só o NOME. O código sai do nome (ex.: "CARDIOLOGIA - NID" → CX-CARD-01). A lista mostra "Fornecedores dos itens" (os fornecedores das unidades dentro da caixa). O campo `caixas.fornecedor` continua aceito (opcional) para dados antigos.

## v18.11.3 — caixa: lote exato e retirar

- Colocar na caixa com etiqueta GS1 cujo lote não existe no estoque: nada entra; a tela mostra em vermelho "Lote bipado não encontrado" com os outros lotes para escolher (antes, com um só lote disponível, entrava esse outro lote sozinho). Grupos de lote sem diferença de maiúscula/minúscula.
- Retirar item da caixa: motivo opcional (padrão "retirado na montagem/ajuste da caixa"); antes exigia 5+ caracteres e o erro aparecia no topo da página, fora da vista.

## v18.11.4 — consignado sem a relação AGHU × consignado

- Cadastro manual / NF de consignado: se o AGHU não tem código consignado na relação, NÃO trava — usa provisoriamente o próprio código AGHU como código consignado (aviso amarelo na tela). Corrige depois importando a relação ou em Corrigir cadastro. Para achar os provisórios: `codigo_consignado = codigo_aghu`.
- Caixa na farmácia (Hemodinâmica/Bloco) só recebe material do ESTOQUE DAQUELA FARMÁCIA (o unitário chega pelo envio + ciência, depois monta/repõe). Caixa no almoxarifado só recebe o estoque do almoxarifado. Antes, a caixa da farmácia aceitava item ainda no almoxarifado.

## v18.11.5 — consignado mostra a descrição do próprio material

- Unidade consignada: `descritivo_hospital` (o que as telas mostram) = descrição da relação consignado × AGHU; sem ela, a descrição da NF/cadastro (`xProd`) — é onde vem o tamanho do balão/stent. Demais materiais seguem com o descritivo do AGHU. Ao salvar/importar a relação com descrição, as unidades daquele código consignado são atualizadas. Migração única (`migracoes_feitas: v18_11_5_desc_consignado`) para os consignados já cadastrados. Corrigir o AGHU de um consignado não troca mais a descrição.

## v18.11.6 — sala bipa só o item; farmácia bipa a caixa para completar

- Registrar uso: item que está em caixa sai da caixa sozinho, sem bipar a caixa (a caixa precisa poder ser usada neste atendimento e não estar bloqueada). Só pede a caixa quando o mesmo material está em DUAS caixas usáveis. A caixa ativa continua funcionando para quem quiser bipá-la.
- Caixas de consignado (farmácia e almoxarifado): campo "Completar uma caixa: bipe a etiqueta da CAIXA" — abre a caixa com o campo de item pronto.

## v18.11.7 — caixas: estrutura de antes, saídas à parte, "colocados agora"

- Lista de caixas volta à estrutura anterior (sem o campo "bipe a caixa"); completar = "Abrir" e bipar os itens.
- Botão "Saídas" ao lado de "Abrir": tela própria `…/{id_caixa}/saidas?de=&ate=` (padrão: últimos 30 dias). A ficha da caixa não mostra mais as saídas.
- Ficha da caixa: o que entrou desde o "Abrir" aparece em "Colocados agora" (verde) e marcado como "novo" / "+N agora" nas listas, até "Concluir a caixa" (foto dos itens no sessionStorage do navegador, por caixa).

## v18.11.8

- Dispensar para a sala: a caixa aparece numa linha só ("Caixa CX-… — N item(ns)", com "tirar a caixa"), separada dos itens soltos; contagem "1 caixa e 1 item".
- Confirmar devolução (farmácia): "usado no paciente" em AZUL com etiqueta "USADO" — não confunde com o quadrado verde de "voltou".
- Nova tela Almoxarifado → "Reposição das caixas" (`/almoxarifado/reposicao-caixas?de=&ate=`, serviço `reposicao_caixas.a_repor`): usados por caixa e AGHU, já repostos (entradas na mesma caixa depois da 1ª saída), a repor, saldo livre no almoxarifado e a ação (enviar / parcial / pedir ao fornecedor).
- Saídas da caixa (404): rota nova da 18.11.7 — o servidor precisa ser reiniciado depois de trocar os arquivos.

## v18.12.1 — robô da RM pelo caminho real (HAR de 16/11/2026)

- Efetivação: a quantidade vai na **linha do item** (`sdTableItemRequisicaoMaterial:resultList:{ri}:qtdeEntregue`) — é ela que faz o AGHU preencher a "Quantidade Atendida" do lote (que fica readonly até o checkbox ser marcado). Com mais de um lote, o robô ainda digita lote a lote.
- Lote do TraceOPME que não existe no AGHU: o robô marca OUTRO lote (preferindo um com saldo) para a RM não travar e avisa no log + na lista de conferência.
- O robô espera a tela "Efetivar Requisição Material" abrir sozinha (até 4 min) em vez de pedir ENTER.
- Cabeçalho: o robô guarda o CA Requisição escolhido pela pessoa e repõe depois de vincular o atendimento (o AGHU dispara `sbCCReq:sgClear` ao digitar o prontuário).
- Mock `rm_efetivar.html` refeito fiel ao HAR; 5 testes do robô da RM.

## v18.12.2

- Nota de consumo / RM: a lista de materiais de cada paciente fica fechada ("N material(is) · M unidade(s) — ver os materiais e lotes").
- Solicitação cancelada: a farmácia não vê mais itens a atender — a tabela vira histórico fechado, somem os botões "marcar atendido" / "atendido com outro código" e o bloco "bipado sem estar na solicitação"; `unidade_nao_solicitada` deixa de alertar.

## v18.12.3 — conferência da devolução separada por situação

- "Não utilizados — conferir e dar ciência": três blocos com cor própria, na ordem **Usados no paciente** (azul, só leitura) → **Sem destino** (vermelho, se houver) → **Não utilizados, confira e marque o que voltou** (verde, logo acima do botão). Antes usado e não usado vinham misturados no mesmo grupo de material.

## v18.13.1 — passar a vez na sala (cada paciente com o seu material) + sala segue bipando até a farmácia conferir

- **Entrou outro paciente na frente**: o que troca é a **vez na sala**, não o material. Ficha do paciente que está na sala → "Outras ações" → "Entrou outro paciente na frente?": escolhe o atendimento de quem entrou, escreve o motivo e clica "Passar a sala". Serviço `atendimentos.candidatos_troca` / `atendimentos.passar_sala`:
  - **nenhuma unidade muda de atendimento**: o material dispensado/recebido continua vinculado a quem saiu, no mesmo status (`TRANSITO_SALA` / `EM_SALA`), sem voltar para a farmácia;
  - só `sala_aberta_em` / `sala_aberta_por` passam para o atendimento de quem entrou (que recebe também a `sala`, se estava cadastrado em outra); quem saiu volta a aguardar e não bipa uso até assumir a sala de novo;
  - volta pelo mesmo caminho: na ficha de quem saiu aparece **"Este paciente entrou na sala agora?" → "Assumir a sala"** (serviço `atendimentos.quem_esta_na_sala`, `sala_ocupada_por` na tela);
  - recusa: mesmo atendimento, atendimento fechado, unidades diferentes, motivo com menos de 5 caracteres, ou a sala não estar aberta com o paciente de origem;
  - grava os eventos `sala_passada` e `sala_assumida` nos dois atendimentos.
- `abrir_sala` com `automatico=True` (ciência do material / 1º bipe) **não** abre mais a sala quando ela está aberta com outro paciente — antes a ciência do material de quem estava esperando "roubava" a sala de quem estava operando. A mensagem do "Abrir sala" manual passa a indicar o caminho de passar a vez.
- **A sala não trava mais depois de "Finalizar materiais utilizados"**: continua bipando uso normalmente (inclusive material novo) e continua podendo excluir um bip errado enquanto o atendimento estiver aberto. A sala só fecha quando a farmácia conclui a conferência da devolução — e, aí sim, só a supervisão reabre.

## v18.14.0 — dispensação para outros procedimentos (farmácia e almoxarifado)

- Novo estado final `saida_outros` ("Dispensado para outro procedimento", local **Saída**): o item sai do estoque e não volta ao disponível (fora de `ESTOQUE_ATIVO`).
- Duas operações de bipagem, uma por módulo — sem atendimento e sem paciente:
  - `saida_outros` (Farmácia): de `EM_ESTOQUE_FARMACIA`, com escopo da farmácia da sessão;
  - `saida_outros_almox` (Almoxarifado): de `EM_ESTOQUE_RECEBIMENTO`.
  Ambas barram material vencido e entram em `BLOQUEADAS_POR_RECALL`. O **destino** (setor/procedimento) é obrigatório — `fluxo.bipar` recusa com menos de 3 caracteres — e vai no campo `motivo`, com 9 sugestões (`saidas_outros.DESTINOS`) em datalist; quem levou o material vai na observação.
- O uso nesses lugares **não** é acompanhado item a item: não há atendimento, dispensação, conferência da sala nem devolução. O que fica é o evento com destino, responsável e observação.
- Nova tela **"Saídas para outros procedimentos"** (`/farmacia/saidas-outros` e `/almoxarifado/saidas-outros`, tela `comum/saidas_outros.html`, serviço `saidas_outros.listar/resumo`): filtro de período e destino, totais por destino e a lista item a item (data, material, lote/validade, destino, quem retirou, observação). Card novo nos dois hubs.
- **Desfazer a saída** (bipado por engano): `saidas_outros.desfazer` → `POST {base}/saidas-outros/{id_unidade}/desfazer`, com motivo. O item volta para o estoque de onde saiu (farmácia dona do item ou almoxarifado) e a linha fica riscada na lista.
- Item dentro de uma caixa continua barrado pela regra geral das caixas: retire-o da caixa (com motivo) antes de dispensar para outro procedimento.
- Corrigido no `audit_framework.py`: `colorize` usava `ENDC` solto e quebrava o auditor (agora `Colors.ENDC`).

## v18.15.0 — indicadores separados por unidade (Bloco Cirúrgico x Hemodinâmica)

- Seletor **Unidade** no filtro de todas as abas de Indicadores (Resumo, Fluxo, Desperdício, Financeiro, Qualidade): "Bloco + Hemodinâmica" (padrão, como era) ou só uma delas. A escolha segue nas abas e no "Exportar CSV" (que ganha a coluna `local` e o nome do arquivo com a unidade).
- Regra única de pertencimento (`indicadores._f_unidades`): o item é da unidade quando **está na farmácia dela** ou **está vinculado a um procedimento dela**. Aplicada às três formas de consulta do módulo — `unidades`, `eventos` (pela unidade física do evento, `_f_eventos`) e `atendimentos` (`_f_atendimentos`). O que não tem farmácia nem procedimento de uma das duas só aparece na visão conjunta, e a tela diz isso.
- Todas as funções do serviço aceitam `unidade=""`: `calcular_valores`, `montar`, `exportar`, `tempos_por_etapa`, `gargalos_abertos`, `produtividade`, `cancelamentos`, `aproveitamento_por_especialidade`, `produtos_mais_devolvidos`, `vencimentos_por_faixa`, `baixas_por_motivo`, `consumo_por`, `evolucao_mensal`, `cobertura_por_produto`, `divergencias_por_fornecedor`, `problemas_na_sala`, `completude_por_campo`, `itens_sem_conferencia_sala`, `pendentes_ciencia_farmacia`, `utilizacao_dispensado` e `usos_sem_dispensacao.taxa_e_ciencia`.
- Cuidado registrado: na consulta sem apelido, a coluna precisa ser qualificada (`unidades.id_atendimento`) — `fa.id_atendimento = id_atendimento` compararia a subconsulta consigo mesma e o filtro passaria tudo.

## v18.16.0 — cartões dos hubs organizados em faixas (sem texto cortado)

- **Faixas com nome** (`<section class="faixa-acoes">` + `<h2>`) no lugar das linhas soltas de 4 cartões:
  - Almoxarifado: *Entrada e cadastro* · *Com as farmácias e caixas de consignado* · *Saídas e fornecedor* · *Consultas e relatórios*;
  - Farmácia: *Receber e cadastrar* · *Dispensar* · *Conferir e dar ciência* · *Caixas de consignado* · *Fechar o dia e consultar*.
  Cada faixa tem uma cor só (as cores deixaram de se misturar dentro da mesma linha).
- `.linha-cartoes` passou de `repeat(4, 1fr)` fixo para `repeat(auto-fill, minmax(190px, 1fr))` (`.cinco` usa 168px): a grade acompanha a largura da tela e **não sobra mais cartão sozinho** no fim do grupo.
- Cartões da mesma faixa ficam com a **mesma altura** (`align-items: stretch`, `.acao-card` em coluna flex, `min-height: 7.2rem`), com título e descrição juntos no topo.
- **Nada de texto cortado**: `overflow: visible` + `overflow-wrap: break-word` nos cartões, etiqueta dentro do cartão pode quebrar linha (antes `white-space: nowrap` passava da borda), nome do produto na lista de bipados e rótulo das barras dos indicadores quebram linha em vez de virar `...`.
- Cartão "Receber material" (Farmácia): o número grande agora é o que motiva o destaque — quando não há envio para conferir mas há item não recebido, mostra a pendência em vez de um `0` vermelho.

## v18.17.0 — busca pela etiqueta bipada: lote colado na validade, aviso falso e cartões repetidos

Três problemas que apareciam juntos ao bipar a etiqueta nas telas de busca (HC-UFPE, 17/11/2026):

- **O lote engolia a validade.** O AI 10 (lote) tem tamanho variável e termina no separador FNC1, que a maioria dos leitores não manda. `10 SP1124082036` + `17 270904` chegava como o lote `SP112408203617270904`, que não existe em cadastro nenhum — a busca caía no GTIN e trazia *todos os lotes do produto*. `gs1.interpretar` agora devolve também a leitura alternativa (`lote_curto` + `validade_do_lote`, em `_leitura_partida`), e `gs1.filtrar` tenta o lote inteiro e depois o curto. Não se escolhe uma leitura no parser de propósito: um lote que realmente termina em números de data (`9686013291005`) continua sendo achado inteiro.
- **"Código de barras não encontrado" com os itens certos logo abaixo.** `consultas_controller._lote_nao_encontrado` comparava só `cadastrado.startswith(lido)`; com o lote grudado na validade, o cadastro é que é prefixo do lido. Agora compara nos dois sentidos e considera a leitura alternativa.
- **Vários cartões iguais em "Corrigir cadastro".** `grupos_para_correcao` agrupava por "todos os campos iguais": o mesmo lote virava 3 cartões só porque o fornecedor estava escrito de dois jeitos ("GMI" / "Gabisa Medical") ou porque uma entrada tinha data de fabricação e a outra não. O agrupamento passou a ser por **produto + código AGHU + lote + validade**; os campos que divergem vêm vazios, com `misto` (valores e quantas unidades têm cada um) para a tela mostrar "hoje: Gabisa Medical (9) · GMI (5)" e a pessoa igualar de uma vez. O que ela não preencher fica como está em cada unidade.
- **Itens e grupos passam a sair juntos e coerentes** (`estoque.para_correcao`): quando a etiqueta aponta para unidades cadastradas, os grupos ficam restritos ao mesmo lote/série — antes a tela abria com grupos de outros lotes em cima e a unidade bipada escondida dentro de "Ou corrija uma unidade por vez". A tela mostra o que foi lido da etiqueta (produto, lote, validade, série) e o aviso quando o lote não confere.

## v18.17.1 — Caps Lock no leitor

- O prefixo de simbologia da etiqueta (`]C1`, `]d2`, `]Q3`) passou a ser reconhecido sem olhar maiúscula/minúscula. Com o Caps Lock ligado o leitor manda `]c1` e a etiqueta inteira deixava de ser tratada como GS1 (caía na busca por texto). Lote e código já eram insensíveis a maiúsculas (`lote_norm`/`gtin` normalizam, e o banco guarda o lote em maiúscula).

## v18.17.2 — tela "desregulada" depois de atualizar o servidor

- `main.ts` passou a ouvir `vite:preloadError`: quando o navegador está com a página antiga aberta e pede um pedaço de tela (JS/CSS) que não existe mais no servidor atualizado, a página se recarrega sozinha uma vez (trava em `sessionStorage` evita o laço). Era o que deixava a tela com os rótulos cortados e os botões sobrepostos em alguns computadores — só naqueles que não tinham recarregado desde a atualização.
- Lembrete: o rodapé mostra a versão do **servidor** (vem de `/api/health`), não a do que está carregado no navegador — por isso a tela quebrada podia exibir a versão nova.

## v18.18.0 — material extra depois de a sala finalizar

Três coisas que apareciam juntas quando o médico pedia material no meio do procedimento, depois de a sala já ter finalizado:

- **Aviso vermelho vencido.** A bipagem ainda dizia "Materiais utilizados já finalizados. Só é possível bipar o que a farmácia não recebeu de volta" — regra que saiu na v18.13. Agora o aviso é informativo: a sala continua bipando e só fecha quando a farmácia concluir a conferência; se houver material dispensado depois, traz o botão "Dar ciência dos N item(ns) que chegaram depois".
- **`finalizar_uso` não encerra mais o atendimento sozinho** (saiu o `encerrar_se_completo`). Sem sobra nenhuma o atendimento era fechado na hora e, a partir daí, a farmácia não conseguia nem dispensar o extra: a sala ficava sem ciência, sem bipe e sem caminho. Quem encerra é a farmácia ("Concluir procedimento"), como já valia quando havia devolução.
- **Dá para finalizar de novo** quando chegou material depois (`complemento_pendente` ou novas sobras): `_gravar_finalizacao(refazendo=True)` regrava a finalização, a ciência do que chegou depois continua obrigatória e o que não foi usado entra na lista da farmácia. Sem material novo, a recusa explica ("já foram finalizados e não há material novo para fechar"). A trava contra duplo clique continua valendo na primeira finalização.
- A tela `sala_procedimento/concluir.html` deixou de expulsar quem já finalizou: continua acessível enquanto houver material novo, com `ja_finalizado` no contexto (título e botão mudam para "Dar ciência e finalizar de novo").
- Verificação da suíte antiga atualizada: "sem material sobrando, finalizar deixa a sala aberta" + "e a farmácia conclui o procedimento".

## v18.19.0 — ordem da tela de finalizar: pendências de ciência primeiro

Cenário do HC-UFPE: 10 materiais com ciência, mais 2 dispensados no meio do procedimento sem ciência (um usado, um não).

- A tela `sala_procedimento/concluir.html` passou a seguir a ordem do trabalho: **1. pendências de ciência** (bloco novo no topo, borda vermelha, com tabela item a item e o checkbox de ciência) → **2. o que foi bipado** → **3. o que volta para a farmácia** → botão. Antes a lista de ciência ficava no último cartão, depois de tudo.
- `dispensacoes.complemento_pendente` devolve agora `status_unidade` e `destino` por item: a sala vê se aquele material **já foi bipado como utilizado** ou se **está na sala e volta se não for usado** — os dois casos convivem, porque bipar o uso nunca dependeu da ciência.
- Regras que já valiam e continuam: bipar o extra não exige ciência; a ciência é obrigatória para finalizar; o extra não usado entra na lista de devolução da farmácia.

## v18.20.0 — conferência do recebimento na estrutura do estoque

Tela `farmacia/recebimento.html` (serve ao envio do almoxarifado, à devolução da farmácia e à transferência entre farmácias):

- **Pela lista**: uma linha por material/lote, como a tela de estoque — AGHU · Material (com o código de barras embaixo) · Lote · Validade · Fornecedor/marca · Qtd. Antes eram N linhas idênticas de duas linhas de texto cada (um envio de 6 unidades do mesmo cateter ocupava a tela inteira). Grupo de 1 unidade tem caixinha "chegou"; grupo de 2+ tem campo de quantidade ("3 de 3") para o caso de chegar parte. O rodapé mostra "Selecionados: X de Y — Z vira(m) pendência".
- **Bipando**: a lista deixou de ficar parada. Em cima, **"Falta bipar (N)"** agrupado, que diminui a cada leitura; embaixo, **"Já bipados (M)"** recolhido num `details`. O retorno de cada bip passou a nomear o material e o lote e dizer quanto falta ("✔ BALAO · lote LB2 — recebido. Faltam 8."), em vez de repetir só o código lido.
- `remessas.itens` passou a trazer `u.fornecedor` (a coluna nova da tabela).
- A conferência continua item a item por baixo: o formulário envia os `id_item` conforme a quantidade marcada em cada grupo.

## v18.21.0 — uma leitura vale por várias unidades iguais

- Na conferência bipando (`farmacia/recebimento.html`), um campo **Quantidade** ao lado do campo de leitura: com 5 unidades iguais do mesmo código, escreve-se `5` e bipa-se **uma vez** — `bipar()` marca até essa quantidade de itens livres daquele código (`identificar` já devolvia todos os `id_item` que batem).
- O retorno diz o que entrou e quantos: "✔ 5 × CATETER BALÃO · lote LOTE5 — recebidos. Faltam 2."; quando se pede mais do que existe, marca o que há e avisa ("Só havia 1 deste código ainda não bipado(s)").
- A quantidade **volta para 1 depois de cada leitura**, de propósito: deixá-la em 5 marcaria 5 na leitura seguinte sem ninguém perceber.
- A conferência continua item a item por baixo — o que muda é quantas unidades uma leitura resolve.
