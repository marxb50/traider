# SUPER_TRADER_QUANT

MVP em Python para **paper trading** de swing/position trade com scanner de setups, backtest sem lookahead, memória histórica por ativo e alertas Telegram.

> **SIMULAÇÃO — NÃO É CONTA REAL**  
> Rentabilidade passada não garante resultado futuro. O sistema trabalha com **probabilidade histórica estimada**, nunca certeza.

## O que esta versão entrega
- 200 ativos demo: 100 do Brasil, 50 dos EUA e 50 do Reino Unido.
- 35 setups implementados:
  - IFR2
  - Setup 123
  - Inside Bar
  - Supertrend
  - Donchian
  - Bollinger
  - Trap na Média
  - PFR
  - EMA Cross
  - EMA20 Pullback
  - MACD Cross
  - Engulfing
  - Hammer/Star
  - Volume Breakout
  - RSI50 Retomada
  - SMA20/50 Cross
  - EMA9/21 Cross
  - VWAP Reclaim
  - VWAP Pullback
  - NR7 Breakout
  - Squeeze Breakout
  - Keltner Breakout
  - ADX Trend Pullback
  - CCI Reversal
  - Stochastic Cross
  - Williams %R Reversal
  - ROC Momentum
  - OBV Breakout
  - MFI Reversal
  - Gap Continuation
  - Gap Fade
  - Three Bar Reversal
  - Pin Bar Reversal
  - Marubozu Continuation
  - Double Top/Bottom Breakout
- Scanner de sinais de `COMPRA` e `VENDA` simulados; nenhuma ordem real é enviada.
- Registro automático do desfecho dos sinais.
- Memória histórica por ativo/setup.
- Identidade única de sinais no banco para evitar duplicidade.
- Backtester com entrada no próximo candle.
- Alertas Telegram com outbox durável, reprocessamento e fan-out por destinatário.
- Filtro técnico de sinais em `VERDE`/`AMARELO`/`VERMELHO`, com direção `COMPRA`/`VENDA`, chance de acerto histórica estimada, amostra, tempo médio até alvo, PnL médio e risco/retorno.
- Auditoria de fonte dos sinais: o robô grava provider, status, quantidade de fontes e motivo da confirmação de dados.
- Confirmação opcional por quorum de dados: em `strict`, alertas `VERDE`/`AMARELO` de mercados configurados só são enviados se a fonte secundária confirmar o último candle/preço.
- Modo multi-timeframe para swing trade: entrada em `H1`/60 minutos com filtro de contexto em `D1` diário e `W1` semanal.
- Scheduler para execução contínua, com ciclo inicial no boot, heartbeat operacional e trava exclusiva para evitar duas instâncias ao mesmo tempo.
- Envio Telegram imediato no ciclo do scanner/resolvedor, com lote alto próprio para não deixar sinais recém-criados esperando o job periódico; se o Telegram estiver indisponível, o alerta permanece na outbox para nova tentativa.
- Watchdog operacional para avisar no Telegram quando o scheduler parar, a fila travar, a memória ficar inconsistente ou o universo esperado (BR=100, US=50, UK=50) sair do esperado; sinais abertos velhos isolados entram como aviso interno e só viram alerta quando atingem `WATCHDOG_STALE_OPEN_SIGNALS_ALERT_MIN_COUNT`.
- Watchdog com janela de graça no startup para evitar falso alerta durante restart curto do scheduler.
- Backup consistente do SQLite antes de manutenção/deploy.
- Manutenção operacional com backup, retenção segura de notificações antigas e rotação de backups, sem apagar sinais nem memória histórica.
- Guardrails de recursos para alertar se o banco passar do limite ou se `data/`, `logs/` ou `backups/` ficarem com pouco espaço livre.
- Proteção por token nos endpoints operacionais mutáveis, para não depender só do loopback no VPS.
- Cache do `yfinance` redirecionado para dentro de `data/cache/`, compatível com o hardening `ProtectHome=true` no VPS.
- Sinais que ficarem velhos sem nenhum candle posterior disponível no provider passam a expirar automaticamente com nota operacional, evitando ficar presos em `open` indefinidamente.
- FastAPI + Streamlit.
- Testes automatizados.
- Arquivos de deploy isolado para VPS.
- Relatório premium em HTML e PDF a partir de planilhas locais ou Google Sheets, com logo, rodapé em todas as páginas, fotos otimizadas e 10 gráficos automáticos.

## Estrutura principal
```text
super_trader_quant/
  backend/app/
  frontend/
  deploy/
  scripts/
  tests/
```

## Instalação local
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m scripts.seed_demo
pytest
```

## Comandos úteis
```bash
python -m scripts.seed_demo
python -m scripts.run_scanner --provider simulated
python -m scripts.run_backtest_batch --provider simulated
python -m scripts.build_catalog_report --source https://docs.google.com/spreadsheets/d/SEU_ID/edit#gid=0 --logo "C:\\caminho\\SELIM AZUL (1).png"
python -m scripts.check_deploy_readiness
python -m scripts.check_deploy_readiness --strict --runtime
python -m scripts.goal_acceptance_report --strict --runtime
python -m scripts.build_verification_manifest
python -m scripts.build_verification_bundle
python -m scripts.verify_verification_bundle
python -m scripts.verify_verification_round
python -m scripts.dispatch_notifications_now --max-batches 20 --require-empty
python -m scripts.suppress_pending_notifications --older-than-minutes 5 --output logs/suppress_pending_notifications_last.json
python -m scripts.production_preflight --strict --app-dir /opt/super_trader_quant --env-file /opt/super_trader_quant/.env
python -m scripts.verify_ops_http_protection --base-url http://127.0.0.1:8010
python -m scripts.verify_systemd_runtime
python -m scripts.verify_filesystem_isolation --app-dir /opt/super_trader_quant --app-user supertrader
python -m scripts.verify_process_runtime --app-user supertrader --app-dir /opt/super_trader_quant --api-port 8010
python -m scripts.validate_deploy_artifacts
python -m scripts.validate_demo_assets
python -m scripts.send_telegram_test
python -m scripts.send_telegram_canary
python -m scripts.rebuild_memory
python -m scripts.backup_db --label manual
python -m scripts.run_maintenance
python -m scripts.watchdog_once --strict
python -m scripts.scan_now --provider simulated --timeframe H1
python -m scripts.run_watchdog_loop
python -m scripts.run_scheduler
python -m scripts.run_api
streamlit run super_trader_quant/frontend/streamlit_app.py
pytest
```

## Telegram
No `.env`:
```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_IDS=
TELEGRAM_BR_BOT_TOKEN=
TELEGRAM_BR_CHAT_IDS=
SCAN_MARKETS=BR,US,UK
SCAN_INTERVAL_MINUTES=60
SCAN_TIMEFRAME=H1
SCAN_INTRADAY_PERIOD=3mo
SCAN_DAILY_PERIOD=1y
SCAN_WEEKLY_PERIOD=2y
SIGNAL_ALERT_MIN_LEVEL=yellow
SIGNAL_ALERT_YELLOW_MIN_PROBABILITY=0.50
SIGNAL_ALERT_GREEN_MIN_PROBABILITY=0.58
OPS_ADMIN_TOKEN=
BRAPI_TOKEN=
SIGNAL_DATA_CONFIRMATION_MODE=auto
SIGNAL_DATA_CONFIRMATION_PROVIDER=brapi
SIGNAL_DATA_CONFIRMATION_MARKETS=BR
```

Depois basta incluir outros IDs separados por vírgula:
```env
TELEGRAM_CHAT_IDS=123456789,987654321
```

Se quiser duas rotas ao mesmo tempo, use assim:
```env
TELEGRAM_BOT_TOKEN=<bot-geral>
TELEGRAM_CHAT_IDS=123456789
TELEGRAM_BR_BOT_TOKEN=<bot-brasil>
TELEGRAM_BR_CHAT_IDS=123456789
```
Com isso, `BR` vai para os dois bots e `US/UK` vao apenas para o bot principal.

Por padrão, só alertas `VERDE` e `AMARELO` são enviados. O scanner ainda salva sinais `VERMELHO` no banco para acompanhamento e aprendizado, mas não dispara Telegram para eles. A mensagem do Telegram informa se o sinal é `COMPRA` ou `VENDA`; `VENDA` significa posição vendida simulada/paper trading, não operação real. A chance de acerto exibida é uma estimativa histórica do ativo/setup/timeframe com suavização estatística; não é promessa de acerto.

Para exigir confirmação externa antes de enviar alerta importante no Brasil, configure uma chave grátis da Brapi no `.env` e ative o modo estrito:
```env
BRAPI_TOKEN=<sua-chave-gratis>
SIGNAL_DATA_CONFIRMATION_MODE=strict
SIGNAL_DATA_CONFIRMATION_PROVIDER=brapi
SIGNAL_DATA_CONFIRMATION_MARKETS=BR
SIGNAL_DATA_CONFIRMATION_MAX_CLOSE_DIFF_PCT=0.5
```
No modo `auto`, a divergência entre fontes bloqueia o alerta, mas falta de token da fonte secundária apenas fica registrada na auditoria para não silenciar todo o universo por configuração incompleta. No modo `strict`, falta de confirmação derruba `VERDE`/`AMARELO` para `VERMELHO` e impede Telegram.

No modo swing multi-timeframe, o scheduler pode rodar a cada 60 minutos com `SCAN_TIMEFRAME=H1`. Nesse modo, o gatilho do sinal vem do candle de 60 minutos, mas ele só passa se o contexto maior estiver aceitável:
- `W1` semanal: tendência principal.
- `D1` diário: contexto/setup intermediário.
- `H1`/60 minutos: timing de entrada.

O filtro multi-timeframe é direcional: sinais de `COMPRA` favorecem contexto `bullish`/neutro em `W1` e `D1`, enquanto sinais de `VENDA` favorecem contexto `bearish`/neutro. Assim, venda simulada em tendência maior de baixa não é rebaixada indevidamente apenas por estar contra a regra de compra.

Para um robô focado apenas em Brasil, use:
```env
SCAN_MARKETS=BR
SCAN_INTERVAL_MINUTES=60
SCAN_TIMEFRAME=H1
OUTCOME_CHECK_INTERVAL_MINUTES=60
```
Com isso, o scanner roda de hora em hora e só envia Telegram quando encontrar sinal novo qualificado no universo BR.

Os alertas explicam o `timeframe` junto com o tempo em candles. No padrão multi-timeframe (`H1`), **1 candle = 1 hora de negociação**; então `3 candles H1` quer dizer aproximadamente 3 horas de pregão. Em `D1`, **1 candle = 1 pregão/dia útil**; em `W1`, **1 candle = 1 semana**.

Se quiser restringir o scanner inteiro aos mercados permitidos, ainda pode usar:
```env
SCAN_MARKETS=BR
```

No VPS, depois de rodar o canário real, gere o comprovante final:
```bash
python -m scripts.goal_acceptance_report --strict --runtime --require-canary --require-preflight --require-ops-protection --require-systemd-runtime --require-filesystem-isolation --require-process-runtime --require-notification-drain --require-verification-manifest --output logs/goal_acceptance_last.json
```

Os recibos exigidos pelo aceite final precisam ser **recentes**. O relatório agora rejeita recibos velhos mesmo que o arquivo exista.
Quando a validação roda pelo `deploy/verify_vps.sh`, os recibos também precisam pertencer à **mesma rodada** de verificação, identificada por um `RUN_ID` comum.
Além disso, os recibos obrigatórios precisam ser coerentes no **mesmo host** e em **`APP_ENV=production`**.
Os scripts de verificação agora gravam os recibos de forma **atômica**. Se algum recibo ficar corrompido, o aceite final bloqueia explicitamente em vez de aceitar silenciosamente.
O aceite final também verifica se os recibos obrigatórios refletem a **configuração isolada esperada** do VPS, como `APP_DIR`, `APP_USER`, `.env` e bind local da API.
Além disso, a rodada de validação agora gera um **manifest hashado** dos recibos obrigatórios, e o aceite final compara os hashes atuais com esse manifest.
Depois do aceite final, o VPS também pode gerar um **bundle ZIP da rodada** com os recibos e um resumo humano, por meio de `python -m scripts.build_verification_bundle`.

Para validar o caminho real dos alertas no VPS, use:
```bash
python -m scripts.send_telegram_canary
python -m scripts.send_telegram_canary --route br
```
Esse comando não cria operação real: ele cria uma notificação canario na outbox, despacha pelo mesmo mecanismo usado pelos sinais e confirma se todos os destinatarios da rota escolhida ficaram com status `sent`.

## Execução 24/7
Há duas opções preparadas:
1. `systemd` com dois serviços separados:
   - `deploy/systemd/super-trader-quant-api.service`
   - `deploy/systemd/super-trader-quant-scheduler.service`
2. `docker compose` com o arquivo em `deploy/docker-compose.yml`.

O serviço usa:
- banco próprio em `data/super_trader_quant.db`;
- `.env` próprio;
- diretório próprio;
- logs próprios.
- trava própria em `data/scheduler.lock`;
- backups próprios em `data/backups/`.
- watchdog próprio em `super-trader-quant-watchdog.timer`.

Assim ele pode rodar isolado dos demais sistemas do VPS.

Quando um ciclo 24/7 encontra novo sinal ou resolve um sinal aberto, o scheduler tenta enviar Telegram imediatamente no próprio ciclo. O job periódico de notificações continua existindo como rede de segurança para reprocessar alertas pendentes.

Se você acumulou backlog na outbox durante um período sem `TELEGRAM_BOT_TOKEN`, use `python -m scripts.suppress_pending_notifications` antes do primeiro go-live real. Esse comando **não apaga** o histórico: ele apenas marca pendências antigas como `suppressed` para evitar spam de alertas atrasados quando o bot entrar.

Para produção, use como base o arquivo `.env.vps.example` e siga o guia em `deploy/README.md`.
Há também scripts auxiliares:
- `deploy/install_vps.sh`
- `deploy/verify_vps.sh`

Ao final do `verify_vps.sh`, os artefatos principais esperados em `logs/` passam a incluir:
- `notification_drain_last.json`
- `goal_acceptance_last.json`
- `verification_manifest_last.json`
- `verification_bundle_last.json`
- `verification_bundle_last.zip`
- `verification_bundle_check_last.json`
- `verification_round_last.json`

Endpoints operacionais:
- `GET /health`
- `GET /ops/status` para consultar heartbeat do scheduler, sinais abertos, envelhecimento dos sinais, fila de notificações e consistência da memória.
- `GET /ops/watchdog` para ver a auditoria operacional pronta para alerta.
- `POST /ops/auth-check` para comprovar autenticação administrativa dos endpoints operacionais sem efeito colateral.
- `POST /ops/scan-now` para disparar scanner/resolução/Telegram imediatamente pelo mesmo pipeline seguro, usando trava para não colidir com o scheduler. Em produção, esse endpoint exige `X-Ops-Admin-Token` (ou `Authorization: Bearer ...`).

## Avisos de dados
- `yfinance` é usado apenas como protótipo rápido e **não é fonte oficial**.
- `brapi` consulta dados de ativos da B3 via `BRAPI_TOKEN` e pode ser usado como fonte principal ou confirmação secundária.
- `bcb_sgs` consulta séries macro do Banco Central do Brasil por ID de série SGS; não é provider OHLC do scanner, mas serve para filtros/relatórios macro.
- O provider `stooq` está preparado como alternativa complementar e exige `STOOQ_API_KEY`.
- O provider `simulated` existe para testes automatizados.
- Nenhuma fonte externa garante acerto de trade. A confirmação de dados reduz erro de feed, mas não transforma probabilidade histórica em certeza.

## Referências pesquisadas para setups
Esta expansão priorizou setups clássicos de tendência, reversão, rompimento, volume e volatilidade, inspirados por:
- John J. Murphy, `Technical Analysis of the Financial Markets`.
- Jack D. Schwager, série `Market Wizards`, com foco em processo, risco e disciplina.
- Van K. Tharp, `Trade Your Way to Financial Freedom`, com foco em sistema, expectativa e risco/retorno.
- Mark Douglas, `Trading in the Zone`, com foco em consistência e psicologia.
- StockCharts ChartSchool e TradingView Education, como bases práticas de padrões, indicadores e estudo de gráficos.
- B3/Bora Investir, Giro de Mercado e Scanner da Bolsa, como referências nacionais de análise técnica e setups populares no Brasil.

## Dashboard premium HTML/PDF
Para montar o pacote visual a partir das planilhas na nuvem ou arquivos locais:

```bash
python -m scripts.build_catalog_report \
  --source "https://docs.google.com/spreadsheets/d/SEU_ID/edit#gid=0" \
  --source "C:\\dados\\catalogo_complementar.xlsx" \
  --logo "C:\\imagens\\SELIM AZUL (1).png" \
  --footer "feito por marx bruno" \
  --title "SELIM AZUL | Dashboard Premium" \
  --expected-records 780 \
  --output-dir "data\\reports\\selim_azul"
```

O gerador aceita `CSV`, `TSV`, `XLSX`, `JSON` e link de `Google Sheets`, baixa todas as fotos referenciadas nas colunas de imagem/foto/logo, reduz a qualidade para um HTML mais leve, gera uma galeria visual e cria:
- `catalog_dashboard.html`
- `catalog_dashboard_offline.html`
- `catalog_dashboard.pdf`
- `summary.json`
- `dataset_normalized.csv`
- `assets/charts/` com 10 gráficos automáticos

Variáveis opcionais no `.env`:
```env
REPORT_DATA_SOURCES=
REPORT_LOGO_PATH=
REPORT_OUTPUT_DIR=./data/reports
REPORT_EXPECTED_RECORDS=780
```

## Próximos passos já previstos
- COTAHIST B3 completo.
- CVM fundamentos.
- Magic Formula real.
- Low Risk real.
- Full Factor real.
- MCP server.
- Alpaca paper broker.
- Walk-forward.
- Out-of-sample.
- Monte Carlo.
- Relatórios PDF.
