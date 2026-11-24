# TraceOPME — Rastreabilidade de OPME (HC-UFPE)

> **Do almoxarifado ao paciente: cada órtese, prótese e material especial rastreado por unidade, lote e validade.**
> Versão **18.4.4** · Autoria: **Camila Corrêa de Melo** · Construído sobre o **Framework-SETISD-HC-UFPE**
> (FastAPI + Vue 3 / Vite, AD/LDAP + RBAC local, JWT com refresh HttpOnly, trilha `audit_logs`).

---

## 🏛️ O que é

O TraceOPME acompanha o OPME em todo o fluxo do hospital:

| Etapa | Onde no sistema |
|---|---|
| Entrada por NF-e (XML), planilha de lotes do AGHU ou cadastro manual, etiquetas QR | **Almoxarifado** |
| Envio às farmácias (Bloco Cirúrgico / Hemodinâmica), conferência e recebimento | **Almoxarifado → Farmácia** |
| Caixas de consignado (montagem, etiqueta, conferência, devolução) e caixas na sala | **Farmácia** |
| Agenda / abertura de procedimento, solicitação de OPME, dispensação para a sala | **Procedimentos · Farmácia** |
| Confirmação do recebimento, registro de uso por bipagem, estorno, finalização, não utilizados | **Sala de procedimento** |
| Empenhos e vínculo de consignados | **Consignados** |
| Contagem de estoque por local | **Inventário** |
| Prontuário (descritivo cirúrgico), lote, recall, validades, dispensas, histórico | **Consultas** |
| Fluxo, desperdício, financeiro, qualidade e metas | **Indicadores** |
| Usuários (AD + perfil local), catálogo AGHU, entrega ao paciente, backup, diagnóstico | **Administração** |

Todas as funcionalidades da versão 17 (Jinja + sessão) foram mantidas na íntegra; a
mudança é de **arquitetura**, não de regra de negócio. O mapeamento completo está em
[`docs/TRACEOPME_MIGRACAO.md`](./docs/TRACEOPME_MIGRACAO.md).

### Perfis (RBAC local)

| Perfil | Módulos |
|---|---|
| Administrador | todos |
| Almoxarifado | Painel, Almoxarifado, Consignados, Inventário, Consultas, Indicadores |
| Sala de procedimento | Painel, Procedimentos, Sala de procedimento, Consultas, Indicadores |
| Farmácia | Painel, Procedimentos, Farmácia, Consultas, Inventário |
| Supervisão | Painel, Procedimentos, Sala de procedimento, Consultas, Indicadores — e autoriza reabertura/exceções com a própria senha |
| Gestão / Coordenação | Painel, Procedimentos, Consignados, Inventário, Consultas, Indicadores |
| Somente consulta | Painel, Consultas |

### Autenticação

- **Produção (AD configurado — `AD_URL`)**: o usuário entra com o **login e a senha de rede**;
  o TraceOPME só confere no seu banco se o usuário está **ativo** e qual o **perfil**.
  O administrador inclui pessoas em *Administração → Incluir usuário* com **Consultar AD**
  (nome, e-mail e setor vêm do AD). Supervisão confirma exceções com a senha de rede.
- **Reserva (sem `AD_URL`)**: vale a senha local do TraceOPME, exatamente como na v17
  (solicitar acesso, esqueci a senha, troca de senha no perfil).

---

## 📂 Estrutura do Projeto

```text
TraceOPME_Framework/
├── .env.example          # Modelo de variáveis de ambiente (inclui as OPME_*)
├── AGENTS.md             # Diretrizes universais para Agentes de IA (Gemini, Claude, ChatGPT, Cursor)
├── audit_framework.py    # Auditor de Conformidade Arquitetural
├── Dockerfile            # Receita de build multi-estágio (opcional para Podman / Docker)
├── compose.yaml          # Orquestração de contêiner para VMs (opcional)
├── pyproject.toml        # Dependências e configurações do projeto Python (uv)
├── requirements.txt      # Lista congelada de pacotes Python
├── dev.sh                # Script de execução paralela para desenvolvimento
├── start.sh              # Script de build e execução local do servidor
├── docs/                 # Documentação detalhada da arquitetura e manuais
│   ├── especificacao/    # Gabarito oficial de Especificação de Software (Visão, Requisitos, SDD)
│   ├── ARCHITECTURE.md   # Arquitetura em camadas e padrão Provider
│   ├── AUTHENTICATION.md # Sistema de Autenticação (AD / Mock / JWT)
│   ├── GUIA_DESENVOLVIMENTO.md # Tutorial passo a passo para criar novas telas/rotas
│   └── SETUP.md          # Guia de instalação, testes e deploy
├── frontend/             # Aplicação SPA Vue 3 (Vite + TypeScript)
│   ├── src/
│   │   ├── components/   # Componentes visuais reusáveis (DataTable, Modal, etc.)
│   │   ├── layouts/      # Layouts de página (DefaultLayout, LoginLayout)
│   │   ├── router/       # Roteamento e guards de autenticação
│   │   ├── services/     # Cliente HTTP Axios com interceptadores de token
│   │   ├── stores/       # Gerenciamento de estado Pinia (auth, ui)
│   │   ├── components/opme/  # Componentes do TraceOPME (resultado do bip, solicitação, caixas...)
│   │   └── views/        # Login, PaginaOpme (roteador de telas) e views/opme/* (72 telas)
│   └── package.json      # Dependências do frontend (Node.js)
├── src/                  # Backend em Python FastAPI
│   ├── auth/             # Módulos de autenticação AD, JWT e Mock
│   ├── controllers/      # Casos de uso de cada módulo do TraceOPME (*_controller.py)
│   ├── helpers/          # Funções utilitárias (sql_helper)
│   ├── models/           # Modelos de dados SQLAlchemy (banco local)
│   ├── providers/        # Interface + implementação SQLite do TraceOPME
│   │   └── implementations/opme/  # Regras de negócio da v17 (services, domain, db, security)
│   ├── resources/        # Conexões: app.db (framework) e opme_sqlite.py (banco do TraceOPME)
│   ├── routers/          # 190 endpoints /api/* (um router por módulo), todos default-private
│   └── main.py           # Ponto de entrada FastAPI e servidor SPA
└── tests/                # Testes automatizados assíncronos (pytest)
    ├── conftest.py       # Fixtures de teste do FastAPI TestClient
    ├── test_opme_api.py  # Login, RBAC, envelopes de tela, auditoria
    ├── test_opme_suite.py # Roda as suítes de regra de negócio da v17 (489 verificações do fluxo completo, importação, catálogo e correção de lote)
    └── opme/             # Suítes portadas da v17 + renderizador dos templates antigos sobre a API
```

---

## 🚦 Início Rápido (Quick Start)

### 1. Configuração do Ambiente
```bash
cd TraceOPME_Framework

# Copie o arquivo de exemplo de ambiente e ajuste (JWT_SECRET, OPME_ADMIN_SENHA, AD_URL...)
cp .env.example .env

# Para continuar com os dados da versão 17, aponte OPME_DB para o opme.db antigo
# (ou copie-o para data/opme.db). As tabelas novas são criadas na inicialização.
```

### 2. Executar em Modo Desenvolvimento (Hot Reload)
Executa o Backend (`http://localhost:8000`) e o Frontend Vite (`http://localhost:5173`) em paralelo:
```bash
./dev.sh
```

### 3. Rodar a Suíte de Testes Automatizados
```bash
uv run pytest          # 20 testes, incluindo as suítes de regras de negócio da v17
```

### 4. Primeiro acesso
Entre com `OPME_ADMIN` (sem AD: senha `OPME_ADMIN_SENHA`; com AD: senha de rede) e
cadastre os usuários em **Administração**.

---

## 🚀 Opções de Deploy em Servidores e VMs

O framework oferece flexibilidade total para colocar o sistema no ar:

### 1. Implantação Direta na VM (Sem Contêineres / Systemd)
Para quem prefere rodar direto no sistema operacional sem overhead de contêiner:
```bash
# 1. Instalar dependências e compilar frontend
uv sync && cd frontend && npm install && npm run build && cd ..

# 2. Teste rápido manual (opcional)
./start.sh

# 3. Execução permanente como serviço do Linux (systemd)
sudo systemctl enable traceopme && sudo systemctl start traceopme
```

### 2. Implantação em Contêineres (Podman / Docker)
Para quem prefere isolamento completo:
```bash
# 1. Build da imagem e inicialização do contêiner em background
podman compose up -d --build
# (ou com docker: docker compose up -d --build)

# 2. Verificar os logs da aplicação
podman compose logs -f
```

A aplicação ficará disponível consolidada em `http://IP-DA-VM:8000/`. Para o passo a passo completo da configuração do arquivo de serviço do Linux (`systemd`), consulte o [Guia de Instalação e Deploy (`docs/SETUP.md`)](./docs/SETUP.md).

---

## 🔍 Auditoria Automatizada de Conformidade Arquitetural

Para garantir que o desenvolvimento (seja feito por programadores ou com auxílio de copilotos de IA) esteja **100% conforme** com as diretrizes do hospital, o repositório disponibiliza o script auditor [`audit_framework.py`](./audit_framework.py).

O auditor inspeciona automaticamente **11 pilares mandatórios**:
1. Stack Backend (Python 3.12+ / FastAPI / Uvicorn).
2. Autenticação Corporativa (AD/LDAP Ebserh + RBAC Híbrido).
3. Conectividade Híbrida / Multi-provedor (Interfaces desacopladas PostgreSQL / CSV / Mocks).
4. Autenticação Persistente e Cookies `HttpOnly` para Refresh Token.
5. Proteção de Rotas por Padrão (*Default-Private Router Pattern* no `APIRouter`).
6. Middleware de Security Headers HTTP (Defense-in-Depth contra XSS, Clickjacking e Cache).
7. Governança de Segredos (`src/config.py` e `.env.example` sem hardcode).
8. Trilha de Auditoria Imutável (`audit_logs` com `dados_anteriores`, `dados_novos` e `ip_origem`).
9. Layout Frontend Vue 3 SPA & Versionamento (SidebarNav à esquerda + Marca + Versão **SemVer** no rodapé).
10. Suíte de Testes Automatizados (Testes de status HTTP e auth com `pytest`).
11. Monitoramento Zabbix (`/api/health`) e Manifesto para IA ([`AGENTS.md`](./AGENTS.md)).

### Como executar a verificação:
```bash
# Auditar o próprio Framework ou o seu projeto em desenvolvimento:
uv run python audit_framework.py /caminho/para/o/seu/projeto
```
*(O script exibirá o relatório detalhado com a **Taxa de Conformidade (%)** e apontará o que precisa ser ajustado em caso de pendências).*

---

## 📚 Documentação Detalhada

Para se aprofundar nos padrões arquiteturais do hospital, consulte a documentação oficial na pasta `docs/`:

- **[ TraceOPME: migração da v17 para o framework (`docs/TRACEOPME_MIGRACAO.md`)](./docs/TRACEOPME_MIGRACAO.md)**
- **[ Guia de Instalação, Execução e Deploy (`docs/SETUP.md`)](./docs/SETUP.md)**
- **[ Gabarito de Especificação de Requisitos - SDD (`docs/especificacao/README.md`)](./docs/especificacao/README.md)**
- **[ Diretrizes e Regras para Agentes de IA (`AGENTS.md`)](./AGENTS.md)**
- **[ Arquitetura em Camadas e Padrão Provider (`docs/ARCHITECTURE.md`)](./docs/ARCHITECTURE.md)**
- **[ Manual de Autenticação AD, Mock e JWT (`docs/AUTHENTICATION.md`)](./docs/AUTHENTICATION.md)**
- **[ Padrão de Configurações e Gestão de Segredos (`docs/SECRETS_E_CONFIGURACOES.md`)](./docs/SECRETS_E_CONFIGURACOES.md)**
- **[ Padrão de Auditoria e Trilha de Mudanças (`docs/AUDITORIA_E_LOGS.md`)](./docs/AUDITORIA_E_LOGS.md)**
- **[ Tutorial de Criação de Novas Funcionalidades (`docs/GUIA_DESENVOLVIMENTO.md`)](./docs/GUIA_DESENVOLVIMENTO.md)**

---

**TraceOPME — Camila Corrêa de Melo · Escritório de Processos | HC-UFPE (EBSERH)**
