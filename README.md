# GA4 Prometheus Exporter

[![CI Pipeline](https://github.com/ricardosaltmann/ga4-prometheus-exporter/actions/workflows/ci.yml/badge.svg)](https://github.com/ricardosaltmann/ga4-prometheus-exporter)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python: 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)

Exporter de nível de produção para **Google Analytics 4 (GA4)** utilizando oficialmente a **Google Analytics Data API v1**, expondo métricas operacionais e de negócio para o **Prometheus** através de um endpoint `/metrics`.

Substitui completamente exporters obsoletos baseados no Universal Analytics (como `ticketmaster/googleanalytics_exporter`), eliminando dependências descontinuadas como View IDs (`ga:XXXXXXXX`) e métricas `rt:*`.

---

## Índice

1. [Arquitetura](#1-arquitetura)
2. [Requisitos](#2-requisitos)
3. [Guia Passo a Passo no Google Cloud](#3-guia-passo-a-passo-no-google-cloud)
4. [Criação da Service Account](#4-criação-da-service-account)
5. [Concessão de Permissão no Google Analytics 4](#5-concessão-de-permissão-no-google-analytics-4)
6. [Obtenção do Property ID Numérico](#6-obtenção-do-property-id-numérico)
7. [Instalação e Execução Local](#7-instalação-e-execução-local)
8. [Execução com Docker e Docker Compose](#8-execução-com-docker-e-docker-compose)
9. [Instalação via Systemd (Linux)](#9-instalação-via-systemd-linux)
10. [Implantação em Kubernetes](#10-implantação-em-kubernetes)
11. [Configuração (`config.yaml`)](#11-configuração-configyaml)
12. [Variáveis de Ambiente](#12-variáveis-de-ambiente)
13. [Endpoints HTTP](#13-endpoints-http)
14. [Configuração do Prometheus](#14-configuração-do-prometheus)
15. [Alertas do Prometheus e Alertmanager](#15-alertas-do-prometheus-e-alertmanager)
16. [Dashboard no Grafana](#16-dashboard-no-grafana)
17. [Monitoramento e Gestão de Quotas](#17-monitoramento-e-gestão-de-quotas)
18. [Controle Rigoroso de Cardinalidade e Privacidade](#18-controle-rigoroso-de-cardinalidade-e-privacidade)
19. [Ferramentas de Linha de Comando (CLI)](#19-ferramentas-de-linha-de-comando-cli)
20. [Guia de Troubleshooting](#20-guia-de-troubleshooting)
21. [Checklist de Implantação em Novos Clientes](#21-checklist-de-implantação-em-novos-clientes)

---

## 1. Arquitetura

O exporter adota uma **arquitetura totalmente desacoplada**:

```text
Google Analytics 4
        │
        │ Google Analytics Data API v1 (HTTPS/443)
        ▼
┌────────────────────────────────────────────────────────┐
│               ga4-prometheus-exporter                  │
│                                                        │
│  ┌───────────────────────┐  ┌───────────────────────┐  │
│  │  Collector Realtime   │  │    Collector Core     │  │
│  │  (runRealtimeReport)  │  │      (runReport)      │  │
│  │   Intervalo: 60s      │  │    Intervalo: 300s    │  │
│  └───────────┬───────────┘  └───────────┬───────────┘  │
│              │                          │              │
│              ▼                          ▼              │
│  ┌──────────────────────────────────────────────────┐  │
│  │     Cache Thread-Safe em Memória                 │  │
│  │     - Quota Monitoring                           │  │
│  │     - Política Stale (900s)                      │  │
│  │     - Distinção Zero vs Falha                    │  │
│  └──────────────────────────┬───────────────────────┘  │
│                             │                          │
│  ┌──────────────────────────▼───────────────────────┐  │
│  │  Prometheus Custom Collector & Registry          │  │
│  └──────────────────────────┬───────────────────────┘  │
└─────────────────────────────┼──────────────────────────┘
                              │
                              │ HTTP GET /metrics
                              ▼
                         Prometheus
                              │
                      ┌───────┴────────┐
                      ▼                ▼
                   Grafana        Alertmanager
```

### Por que o Scraping do Prometheus NÃO chama o Google:
Se o Prometheus efetuar scraping a cada 15 segundos (`scrape_interval: 15s`), o exporter responde instantaneamente a partir do **cache em memória** sem fazer qualquer requisição ao Google. As coletas externas ocorrem em segundo plano conforme os intervalos configurados (ex: 60s para Realtime e 300s para Core).

---

## 2. Requisitos

- **Python 3.12+**
- Conectividade HTTPS de saída (`TCP 443`) para `analyticsdata.googleapis.com`
- (Opcional) Docker 24+ e Docker Compose v2+

---

## 3. Guia Passo a Passo no Google Cloud

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Selecione ou crie um projeto (ex: `monitoring-ga4-prod`). Anote o `GCP_PROJECT_ID`.
3. Acesse **APIs e Serviços** → **Biblioteca**.
4. Pesquise por **Google Analytics Data API** (Nome técnico: `Google Analytics Data API v1`).
5. Clique em **Ativar**.
   > [!IMPORTANT]
   > Certifique-se de ativar a **Google Analytics Data API**. Não ative as APIs legadas do Universal Analytics.

---

## 4. Criação da Service Account

1. No Google Cloud Console, acesse **IAM e administração** → **Contas de serviço**.
2. Clique em **Criar conta de serviço**.
   - Nome: `ga4-prometheus-exporter`
   - ID: `ga4-prometheus-exporter` (E-mail gerado: `ga4-prometheus-exporter@PROJECT_ID.iam.gserviceaccount.com`).
3. **Princípio do Menor Privilégio**: Não é necessário conceder papéis de administração no GCP (Owner, Editor ou Administrador). Deixe os papéis no GCP vazios se a conta for usada exclusivamente para o GA4.
4. Conclua a criação da conta.
5. Clique na Service Account criada → aba **Chaves** → **Adicionar chave** → **Criar nova chave** → tipo **JSON**.
6. Guarde o arquivo com segurança em seu cofre de secrets (ex: `secrets/ga4.json`).

---

## 5. Concessão de Permissão no Google Analytics 4

> [!CAUTION]
> A existência da Service Account no Google Cloud **NÃO** concede acesso automático ao Google Analytics!
> O IAM do GCP e o Controle de Acesso do GA4 são sistemas separados.

1. Acesse o [Google Analytics](https://analytics.google.com/).
2. No canto inferior esquerdo, clique no ícone de engrenagem (**Administrador**).
3. Na coluna **Propriedade**, clique em **Gerenciamento de acesso à propriedade** (*Property Access Management*).
4. Clique no botão azul **+** no canto superior direito e selecione **Adicionar usuários**.
5. No campo de e-mail, cole o endereço completo da Service Account:
   ```text
   ga4-prometheus-exporter@PROJECT_ID.iam.gserviceaccount.com
   ```
6. Em **Funções padrão**, selecione apenas:
   - **Leitor** (*Viewer*)
7. Desmarque a opção de notificar por e-mail e clique em **Adicionar**.

---

## 6. Obtenção do Property ID Numérico

No GA4, existem múltiplos identificadores:
- `G-XXXXXXXXXX`: ID de medição (Measurement ID do fluxo web). **NÃO USAR**.
- `GTM-XXXXXX`: Container do Google Tag Manager. **NÃO USAR**.
- **Property ID Numérico (ex: `123456789`)**: **ESTE É O IDENTIFICADOR CORRETO**.

Para localizá-lo:
1. No GA4, acesse **Administrador** → **Detalhes da propriedade**.
2. No canto superior direito da tela, você verá o número da propriedade (ex: `123456789`).

---

## 7. Instalação e Execução Local

```bash
# 1. Clonar ou navegar até o diretório do exporter
cd ga4-prometheus-exporter

# 2. Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # No Windows: .venv\Scripts\activate

# 3. Instalar dependências
pip install -r requirements.txt
pip install -e .

# 4. Validar configuração antes de iniciar
ga4-exporter validate --config examples/config.example.yaml

# 5. Testar conectividade ao vivo com a API
ga4-exporter test-connection --config examples/config.example.yaml

# 6. Iniciar o servidor
ga4-exporter run --config examples/config.example.yaml
```

O exporter estará acessível em `http://localhost:9674/metrics`.

---

## 8. Execução com Docker e Docker Compose

### Usando Docker Compose:

```bash
# 1. Copie o arquivo de exemplo
cp examples/config.example.yaml config.yaml

# 2. Ajuste config.yaml com seu Property ID
# 3. Coloque a chave JSON em secrets/ga4.json

# 4. Suba o container
docker compose up -d
```

### Verificando logs estruturados:
```bash
docker compose logs -f ga4-exporter
```

---

## 9. Instalação via Systemd (Linux)

Para ambientes bare-metal ou VMs sem containers:

```bash
# 1. Criar usuário de sistema
sudo useradd -r -s /bin/false ga4-exporter

# 2. Criar diretórios e copiar arquivos
sudo mkdir -p /etc/ga4-exporter/secrets
sudo cp config.yaml /etc/ga4-exporter/
sudo cp secrets/ga4.json /etc/ga4-exporter/secrets/
sudo chown -R ga4-exporter:ga4-exporter /etc/ga4-exporter
sudo chmod 600 /etc/ga4-exporter/secrets/ga4.json

# 3. Instalar unit systemd
sudo cp deploy/systemd/ga4-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ga4-exporter
```

---

## 10. Implantação em Kubernetes

O diretório `deploy/kubernetes/` contém os manifestos prontos para produção:

```bash
# 1. Criar secret com a credencial
kubectl create secret generic ga4-exporter-credentials \
  --from-file=service-account.json=./secrets/ga4.json

# 2. Aplicar ConfigMap, Service e Deployment
kubectl apply -f deploy/kubernetes/configmap.yaml
kubectl apply -f deploy/kubernetes/service.yaml
kubectl apply -f deploy/kubernetes/deployment.yaml
```

---

## 11. Configuração (`config.yaml`)

```yaml
server:
  listen_address: "0.0.0.0"
  port: 9674

logging:
  level: "INFO"       # DEBUG, INFO, WARNING, ERROR
  format: "json"      # json ou text

google:
  credentials_file: "/run/secrets/ga4.json"
  timeout_seconds: 30

properties:
  - name: "portal"
    property_id: "123456789"
    enabled: true

collection:
  realtime:
    enabled: true
    interval_seconds: 60
  core:
    enabled: true
    interval_seconds: 300
    date_range:
      start_date: "today"
      end_date: "today"

cache:
  stale_after_seconds: 900

quota:
  enabled: true

metrics:
  realtime:
    - name: "activeUsers"
      prometheus_name: "ga4_realtime_active_users"
  core:
    - name: "sessions"
      prometheus_name: "ga4_sessions"
    - name: "screenPageViews"
      prometheus_name: "ga4_screen_page_views"
    - name: "engagementRate"
      prometheus_name: "ga4_engagement_rate"
```

---

## 12. Variáveis de Ambiente

As seguintes variáveis de ambiente substituem valores do arquivo de configuração:

| Variável | Padrão | Descrição |
|---|---|---|
| `GA4_CONFIG` | `config.yaml` | Caminho do arquivo de configuração YAML |
| `GOOGLE_APPLICATION_CREDENTIALS` | *(vazio)* | Caminho do arquivo JSON da Service Account |
| `GA4_LISTEN_ADDRESS` | `0.0.0.0` | Endereço IP de escuta do servidor HTTP |
| `GA4_PORT` | `9674` | Porta TCP do exporter |
| `GA4_LOG_LEVEL` | `INFO` | Nível de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `HTTPS_PROXY` / `HTTP_PROXY` | *(vazio)* | Proxy HTTP/HTTPS padrão para conexões externas |

---

## 13. Endpoints HTTP

| Rota | Método | Descrição | Status de Sucesso |
|---|---|---|---|
| `/metrics` | `GET` | Métricas no formato Prometheus | `200 OK` |
| `/health` | `GET` | Liveness probe (processo saudável) | `200 OK` |
| `/ready` | `GET` | Readiness probe (inicialização e primeira coleta concluídas) | `200 OK` (ou `503 Service Unavailable`) |
| `/status` | `GET` | Resumo operacional das coletas (sem dados sensíveis) | `200 OK` |

---

## 14. Configuração do Prometheus

Adicione ao seu `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: "google_analytics_ga4"
    scrape_interval: 30s
    scrape_timeout: 10s
    static_configs:
      - targets: ["ga4-exporter:9674"]
        labels:
          environment: "production"
          source: "google_analytics"
```

---

## 15. Alertas do Prometheus e Alertmanager

As regras prontas estão em `alerts/ga4-exporter.rules.yml`. Incluem:
- **`GA4ExporterDown`**: Disparado se o exporter parar de responder ao scrape.
- **`GA4CollectorDown`**: Disparado se a coleta falhar na API do GA4 (`ga4_exporter_collector_up == 0`).
- **`GA4DataStale`**: Disparado se os dados em cache tiverem mais de 15 minutos sem atualização.
- **`GA4QuotaTokensPerHourLow`**: Alerta quando restam menos de 20% da cota horária de tokens da API.
- **`GA4APIErrorRateHigh`**: Alerta sobre aumento na taxa de erros de API.

---

## 16. Dashboard no Grafana

Um dashboard completo pronto para importação está disponível em `examples/grafana_dashboard.json`.
Ele contém:
- **Painéis Operacionais**: Status do Exporter, Status da Coleta GA4, Idade do Cache, Quota de Tokens restante (hora/dia).
- **Painéis de Tráfego**: Usuários Ativos em Tempo Real, Sessões e Page Views acumuladas no dia, Total de Eventos.
- **Painéis de Qualidade**: Taxa de Engajamento (*Engagement Rate*) e Taxa de Rejeição (*Bounce Rate*).

---

## 17. Monitoramento e Gestão de Quotas

A Google Analytics Data API v1 possui cotas por propriedade e por projeto. O exporter ativa `returnPropertyQuota=True` nas consultas e expõe automaticamente as seguintes métricas Prometheus:

- `ga4_api_quota_tokens_per_hour_remaining{property="...", quota_type="..."}`
- `ga4_api_quota_tokens_per_hour_consumed{property="...", quota_type="..."}`
- `ga4_api_quota_tokens_per_day_remaining{property="...", quota_type="..."}`
- `ga4_api_quota_tokens_per_day_consumed{property="...", quota_type="..."}`
- `ga4_api_quota_concurrent_requests_remaining{property="...", quota_type="..."}`
- `ga4_api_quota_server_errors_remaining{property="...", quota_type="..."}`

---

## 18. Controle Rigoroso de Cardinalidade e Privacidade

Prometheus não é banco de dados analítico. Para prevenir a explosão de séries:
- Dimensões de alta cardinalidade (`pagePath`, `userPseudoId`, `transactionId`) **nunca** são transformadas em labels indiscriminadamente.
- Suporte a **Top-N Páginas**: Coleta no máximo `limit: 20` páginas mais acessadas.
- Eventos customizados são filtrados via parâmetro de consulta na API (`eventName in ['login', 'purchase']`).
- Limite global de séries: `max_series_per_query: 100`. Qualquer série excedente é descartada de forma controlada e contabilizada em `ga4_exporter_series_dropped_total`.
- **Privacidade (LGPD/GDPR)**: Nenhum identificador pessoal (User ID, IP, Client ID, e-mail) é coletado ou exposto.

---

## 19. Ferramentas de Linha de Comando (CLI)

O exporter vem com comandos de diagnóstico:

```bash
# Validar arquivo de configuração e credenciais
ga4-exporter validate --config config.yaml

# Testar conectividade ao vivo com a API do GA4
ga4-exporter test-connection --config config.yaml

# Executar o exporter com opções customizadas
ga4-exporter run --config config.yaml --port 9674 --log-level INFO
```

---

## 20. Guia de Troubleshooting

### `403 PermissionDenied`
- **Causa**: A Service Account não foi adicionada à propriedade GA4 ou não possui papel de `Viewer`.
- **Solução**: No GA4, vá em *Administrador* → *Gerenciamento de acesso à propriedade* → adicione o e-mail da Service Account como **Leitor (Viewer)**.

### `401 Unauthenticated`
- **Causa**: Arquivo JSON da Service Account inválido, corrompido ou relógio do sistema desincronizado (skew de NTP).
- **Solução**: Verifique o arquivo JSON ou gere uma nova chave no Google Cloud Console. Verifique o relógio do servidor (`timedatectl`).

### `429 ResourceExhausted / Quota Exceeded`
- **Causa**: Limite de tokens da API do GA4 foi atingido para a hora ou dia.
- **Solução**: Aumente os intervalos de coleta no `config.yaml` (ex: `interval_seconds: 120` para realtime e `600` para core).

### `Timeout / Connection Reset`
- **Causa**: Bloqueio de rede ou firewall corporativo impedindo saída na porta 443.
- **Solução**: Verifique se o host consegue resolver e conectar a `analyticsdata.googleapis.com:443`. Configure as variáveis `HTTPS_PROXY` e `HTTP_PROXY` caso sua rede utilize proxy.

---

## 21. Checklist de Implantação em Novos Clientes

Antes de subir o exporter no ambiente do cliente, valide os seguintes itens:

- [ ] Google Cloud Project ID identificado
- [ ] Google Analytics Data API v1 ativada no projeto
- [ ] Service Account criada com chave JSON gerada
- [ ] Service Account adicionada ao GA4 com permissão **Leitor (Viewer)**
- [ ] Property ID numérico obtido (ex: `123456789`)
- [ ] Host com conectividade de saída liberada na porta `TCP 443`
- [ ] Arquivo `config.yaml` preenchido com o nome do cliente e Property ID
- [ ] Prometheus configurado com o target `:9674`
- [ ] Regras de alertas e dashboard importados no Grafana
