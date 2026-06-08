# Indique e Ganhe - Programa de Afiliados 90s

Programa de afiliados com tema Windows 95 para barbearia e lava rápido. Backend Flask + frontend vanilla JS + SQLite.

## Funcionalidades

- **Cadastro/Login** com autenticação por token (Bearer), validação server-side e rate limiting
- **Dashboard** com estatísticas, níveis (Bronze/Prata/Ouro/Diamante), metas mensais, gráficos Chart.js
- **Tracking de cliques** via link de indicação (`click.html?ref=RETRO-XXXX`)
- **Conversão** pós-clique com modal "Já Comprei" na landing page
- **Financeiro**: saldo, solicitação de saque (mín. R$10), aprovação admin
- **Painel Admin**: aprovar/rejeitar saques, definir metas, gerenciar afiliados
- **Recuperação de senha** com token expirável (1h) e envio de email SMTP
- **Exportar CSV** dos afiliados (admin)
- **Páginas LGPD**: Termos de Uso e Política de Privacidade
- **Modo escuro** com tema retrô Windows 95
- **Responsivo**: desktop, tablet e mobile

## Começando

```bash
# Instalar dependências
cd backend
pip install -r requirements.txt

# Rodar servidor de desenvolvimento
python app.py
```

Acesse [http://localhost:5000](http://localhost:5000)

### Docker

```bash
docker-compose up -d
```

### Testes

```bash
cd backend
pytest test_api.py -v
```

## Configuração (.env)

Copie `.env.example` para `.env` e preencha:

| Variável | Padrão | Descrição |
|---|---|---|
| `SECRET_KEY` | _(obrigatório)_ | Chave secreta Flask (gere com `secrets.token_urlsafe(32)`) |
| `PORT` | `5000` | Porta do servidor |
| `FLASK_DEBUG` | `0` | Modo debug (1 ativa) |
| `MAX_LOGIN_ATTEMPTS` | `10` | Tentativas de login antes do rate limit |
| `RATE_LIMIT_WINDOW` | `60` | Janela do rate limit (segundos) |
| `MIN_PAYOUT` | `10` | Valor mínimo para saque (R\$) |
| `CORS_ORIGIN` | — | Origem CORS (vazio = mesma origem) |
| `SMTP_HOST` | — | Servidor SMTP (vazio = simula no console) |
| `SMTP_PORT` | `587` | Porta SMTP |
| `SMTP_USER` | — | Usuário SMTP |
| `SMTP_PASS` | — | Senha SMTP |
| `SMTP_FROM` | `noreply@indiqueeganhe.com.br` | Email remetente |
| `CONVERSION_WEBHOOK` | — | URL de webhook para conversões |
| `DISABLE_SEED` | `1` | Desabilita rota /api/seed |
| `PUBLIC_AFFILIATES` | `1` | Lista pública oculta email/telefone/saldo |

## Estrutura do Projeto

```
├── backend/
│   ├── app.py              # Flask: rotas, auth, CORS, rate limiting, email
│   ├── database.py         # SQLite: schema, queries, auth, níveis, saques
│   ├── test_api.py         # Testes pytest (58+ testes)
│   ├── conftest.py         # Fixtures pytest (cliente, rate limiter)
│   ├── promote.py          # CLI para promover usuário a admin
│   └── requirements.txt    # Dependências Python
├── deploy/
│   ├── nginx.conf          # Configuração de produção (nginx + SSL)
│   └── Caddyfile           # Alternativa Caddy (auto-SSL)
├── scripts/
│   ├── backup_db.sh        # Backup do banco (Linux/macOS)
│   └── backup_db.bat       # Backup do banco (Windows)
├── src/
│   ├── auth.js             # Login/register/logout
│   ├── storage.js          # API + localStorage dual-mode
│   ├── affiliates.js       # CRUD de afiliados
│   ├── dashboard.js        # Dashboard, stats, leaderboard
│   ├── tracking.js         # Click & conversion tracking
│   ├── main.js             # Tema, toast, import/export
│   └── utils.js            # Utilitários (formatCurrency, etc.)
├── *.html                  # index, dashboard, admin, signup, login,
│                           # forgot, reset-password, click, termos, privacidade
├── styles.css              # Tema Windows 95 + dark mode
├── Dockerfile              # Container Flask otimizado
├── docker-compose.yml      # Orquestração com healthcheck + volume
└── .env.example            # Template de configuração
```

## Produção

### Requisitos mínimos

- **Proxy reverso**: nginx ou Caddy (configs em `deploy/`)
- **SSL**: Let's Encrypt (via Certbot ou Caddy auto-SSL)
- **Secret Key**: gere com `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- **Rate limiter**: atual em memória — para multi-worker, migre para Redis
- **Banco**: SQLite para baixa concorrência. Para escala, migre para PostgreSQL

### Pipeline de deploy recomendado

1. Configure DNS apontando para o servidor
2. Sincronize os arquivos via rsync/git
3. Configure o proxy reverso (deploy/nginx.conf)
4. Obtenha certificado SSL (Certbot ou Caddy auto-SSL)
5. Ajuste .env com chaves e SMTP reais
6. Inicie com Docker ou systemd

```bash
# Exemplo com Docker
docker-compose up -d

# Backup manual
./scripts/backup_db.sh
```

## Admin

Para promover um usuário a admin:

```bash
python backend/promote.py "email@usuario.com"
```

## Licença

Livre para usar, modificar e compartilhar.
