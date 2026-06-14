# Deploy isolado no VPS

## Princípios de isolamento
- usuário Linux dedicado: `supertrader`;
- diretório dedicado: `/opt/super_trader_quant`;
- banco dedicado: `/opt/super_trader_quant/data/super_trader_quant.db`;
- backups dedicados: `/opt/super_trader_quant/data/backups`;
- trava exclusiva do scheduler: `/opt/super_trader_quant/data/scheduler.lock`;
- logs dedicados: `/opt/super_trader_quant/logs`;
- porta dedicada da API: `8010`;
- serviços isolados:
  - `super-trader-quant-api.service`
  - `super-trader-quant-scheduler.service`
  - `super-trader-quant-watchdog.service` acionado por `super-trader-quant-watchdog.timer`
- unidades `systemd` com `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome=true` e escrita liberada apenas em `data/` e `logs/`.

Isso evita misturar processo, banco, logs e configuração com outros serviços do VPS.

O scheduler também usa uma trava de processo. Se por erro operacional duas instâncias forem iniciadas, a segunda encerra sem escanear mercado nem duplicar alertas.

O watchdog roda a cada 5 minutos no VPS e gera alerta Telegram quando encontra scheduler sem heartbeat fresco, fila Telegram travada, falha de notificação, memória inconsistente ou universo diferente do esperado (100 BR, 50 US e 50 UK). Sinais abertos velhos isolados ficam como aviso interno; eles só viram alerta Telegram quando chegam ao limiar `WATCHDOG_STALE_OPEN_SIGNALS_ALERT_MIN_COUNT`.
Ele respeita `SCHEDULER_STARTUP_GRACE_SECONDS` para não marcar restart curto como “startup travado” cedo demais.

O scheduler também executa manutenção operacional diária. Essa manutenção cria backup, rotaciona backups antigos do padrão `super_trader_quant-*.db` e remove apenas notificações antigas já encerradas (`sent`/`failed`), preservando sinais, memória histórica e notificações pendentes.

O watchdog e o preflight também verificam recursos do VPS: tamanho do SQLite e espaço livre em `data/`, `logs/` e `backups/`. Os limites padrão são `MAX_DATABASE_SIZE_MB=2048` e `MIN_FREE_DISK_MB=512`.

Para endpoints operacionais mutáveis via HTTP, o VPS também deve definir `OPS_ADMIN_TOKEN`. Assim, `POST /ops/scan-now` não fica aberto nem mesmo no loopback.

Para situações em que a outbox acumulou pendências antigas, existe também `scripts.dispatch_notifications_now`, que tenta drenar a fila em lotes controlados e pode falhar explicitamente se ela não zerar.
Se esse acúmulo aconteceu antes do primeiro `TELEGRAM_BOT_TOKEN` real, use `scripts.suppress_pending_notifications` para marcar backlog velho como `suppressed` e evitar disparo tardio em massa na entrada em produção.

O provider `yfinance` também foi ajustado para usar cache em `data/cache/py-yfinance`, evitando tentativa de escrita em `/home/supertrader` e mantendo o `ProtectHome=true` das units.
Ele aceita `H1`/60 minutos, `D1` diário e `W1` semanal. Para swing trade multi-timeframe, a configuração recomendada é scanner a cada 60 minutos em `H1`, usando `D1` e `W1` como filtros de contexto.

Se um provider deixar um sinal aberto sem nenhum candle posterior por tempo demais, o resolvedor expira esse sinal automaticamente com nota `expired_without_post_signal_data`. Isso evita falso verde no scheduler com sinais presos em `open` por falta de follow-up do feed.

## Instalação recomendada com systemd
Se o código já estiver copiado para `/opt/super_trader_quant`, o caminho mais seguro é:
```bash
sudo bash /opt/super_trader_quant/deploy/install_vps.sh
```

Depois, edite o `.env`, reinicie os serviços e valide:
```bash
sudo systemctl restart super-trader-quant-api.service super-trader-quant-scheduler.service
sudo bash /opt/super_trader_quant/deploy/verify_vps.sh
```

Se esse VPS precisar manter um bot geral e um bot so de Brasil, configure no `.env`:
```env
TELEGRAM_BOT_TOKEN=<bot-geral>
TELEGRAM_CHAT_IDS=123456789
TELEGRAM_BR_BOT_TOKEN=<bot-brasil>
TELEGRAM_BR_CHAT_IDS=123456789
```
Assim, `BR` vai para os dois bots e `US/UK` ficam apenas no bot geral.

O filtro de qualidade dos sinais tambem roda no VPS. Com `SIGNAL_ALERT_MIN_LEVEL=yellow`, apenas alertas `VERDE` e `AMARELO` chegam no Telegram; `VERMELHO` fica salvo no banco para memoria e auditoria, mas sem disparo.

Para confirmar dados de mercado antes de Telegram importante, configure a Brapi no `.env` do VPS:
```env
BRAPI_TOKEN=<sua-chave-gratis>
SIGNAL_DATA_CONFIRMATION_MODE=strict
SIGNAL_DATA_CONFIRMATION_PROVIDER=brapi
SIGNAL_DATA_CONFIRMATION_MARKETS=BR
SIGNAL_DATA_CONFIRMATION_MAX_CLOSE_DIFF_PCT=0.5
```
Com `strict`, um `VERDE`/`AMARELO` do Brasil vira `VERMELHO` se a fonte secundaria não confirmar o último candle/preço, e por isso não é enviado. Se ainda não houver token, mantenha `SIGNAL_DATA_CONFIRMATION_MODE=auto` para registrar a falta de confirmação sem travar todo o universo.

Para o modo Semanal + Diário + 60 minutos, configure:
```env
SCAN_INTERVAL_MINUTES=60
SCAN_TIMEFRAME=H1
SCAN_INTRADAY_PERIOD=3mo
SCAN_DAILY_PERIOD=1y
SCAN_WEEKLY_PERIOD=2y
OUTCOME_CHECK_INTERVAL_MINUTES=60
SCAN_MARKETS=BR
```
Nesse modo, o candle de entrada é `H1`/60 minutos. O robô usa `W1` para tendência principal e `D1` para contexto intermediário; se a tendência maior bloquear, o sinal fica `VERMELHO` e não é enviado ao Telegram.

Se a intencao for restringir o scanner inteiro ao Brasil, use:
```env
SCAN_MARKETS=BR
```

O `verify_vps.sh` gera automaticamente um `RUN_ID` UTC (ou reaproveita `RUN_ID` se você exportar antes) e grava esse mesmo identificador em todos os recibos da rodada.
Os recibos também carregam `hostname` e `app_env`, e o aceite final exige coerência no mesmo host com `APP_ENV=production`.
Esses recibos são gravados de forma atômica. Se uma execução for interrompida e algum JSON ficar inválido, o `goal_acceptance_report` bloqueia a conclusão com motivo explícito.
Além disso, o aceite final exige que os recibos reflitam a configuração isolada esperada da rodada, incluindo `APP_DIR`, `APP_USER`, `.env` e `http://127.0.0.1:8010`.
O fluxo também gera `logs/verification_manifest_last.json`, que registra os hashes SHA-256 dos recibos obrigatórios da rodada. O aceite final compara os hashes atuais contra esse manifest antes de concluir.
Depois do aceite, o fluxo também gera `logs/verification_bundle_last.zip` e o recibo `logs/verification_bundle_last.json`, juntando os recibos finais da rodada e um resumo legível para auditoria/arquivamento.
Na sequência, o fluxo roda `scripts.verify_verification_bundle` e grava `logs/verification_bundle_check_last.json`, provando que o ZIP ainda bate com o recibo do bundle e com os arquivos live atuais da rodada.
Por fim, o fluxo roda `scripts.verify_verification_round` e grava `logs/verification_round_last.json`, consolidando que o aceite operacional, o bundle e a checagem do bundle fecharam na mesma rodada.

### Passos manuais equivalentes
```bash
sudo useradd --system --create-home --shell /bin/bash supertrader
sudo mkdir -p /opt/super_trader_quant
sudo chown -R supertrader:supertrader /opt/super_trader_quant
sudo chmod 755 /opt/super_trader_quant

sudo -u supertrader python3 -m venv /opt/super_trader_quant/.venv
sudo chmod 755 /opt/super_trader_quant/.venv
sudo -u supertrader /opt/super_trader_quant/.venv/bin/pip install -r /opt/super_trader_quant/requirements.txt
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.backup_db --label pre-install --allow-missing

cp /opt/super_trader_quant/.env.vps.example /opt/super_trader_quant/.env
mkdir -p /opt/super_trader_quant/data /opt/super_trader_quant/logs /opt/super_trader_quant/data/backups
sudo chown -R supertrader:supertrader /opt/super_trader_quant
sudo chmod 755 /opt/super_trader_quant/data /opt/super_trader_quant/logs /opt/super_trader_quant/data/backups
sudo chmod 600 /opt/super_trader_quant/.env

sudo cp /opt/super_trader_quant/deploy/systemd/*.service /etc/systemd/system/
sudo cp /opt/super_trader_quant/deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now super-trader-quant-api.service
sudo systemctl enable --now super-trader-quant-scheduler.service
sudo systemctl enable --now super-trader-quant-watchdog.timer
```

## Verificações depois da instalação
```bash
export RUN_ID="vps-$(date -u +%Y%m%dT%H%M%SZ)"
cd /opt/super_trader_quant
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.seed_demo
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.production_preflight --strict --app-dir /opt/super_trader_quant --env-file /opt/super_trader_quant/.env --run-id "${RUN_ID}" --output /opt/super_trader_quant/logs/production_preflight_last.json
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.check_deploy_readiness --strict
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.verify_filesystem_isolation --app-dir /opt/super_trader_quant --app-user supertrader --run-id "${RUN_ID}" --output /opt/super_trader_quant/logs/filesystem_isolation_last.json
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.verify_systemd_runtime --run-id "${RUN_ID}" --output /opt/super_trader_quant/logs/systemd_runtime_last.json
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.verify_process_runtime --app-user supertrader --app-dir /opt/super_trader_quant --api-port 8010 --run-id "${RUN_ID}" --output /opt/super_trader_quant/logs/process_runtime_last.json
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.backup_db --label before-runtime-test
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.run_maintenance
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.scan_now --timeframe H1
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.send_telegram_test
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.send_telegram_test --route br
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.send_telegram_canary --run-id "${RUN_ID}"
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.send_telegram_canary --route br --run-id "${RUN_ID}"
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.verify_ops_http_protection --base-url http://127.0.0.1:8010 --run-id "${RUN_ID}" --output /opt/super_trader_quant/logs/ops_http_protection_last.json
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.build_verification_manifest --run-id "${RUN_ID}" --log-dir /opt/super_trader_quant/logs --output /opt/super_trader_quant/logs/verification_manifest_last.json
curl http://127.0.0.1:8010/health
curl http://127.0.0.1:8010/ops/status
curl "http://127.0.0.1:8010/ops/watchdog?strict=true"
curl -X POST -H "X-Ops-Admin-Token: ${OPS_ADMIN_TOKEN}" "http://127.0.0.1:8010/ops/auth-check"
curl -X POST -H "X-Ops-Admin-Token: ${OPS_ADMIN_TOKEN}" "http://127.0.0.1:8010/ops/scan-now?timeframe=H1"
systemctl status super-trader-quant-api.service
systemctl status super-trader-quant-scheduler.service
systemctl status super-trader-quant-watchdog.timer
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.dispatch_notifications_now --run-id "${RUN_ID}" --max-batches 20 --require-empty --output /opt/super_trader_quant/logs/notification_drain_last.json
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.check_deploy_readiness --strict --runtime
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.watchdog_once --strict --notify-ok
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.goal_acceptance_report --strict --runtime --require-canary --require-preflight --require-ops-protection --require-systemd-runtime --require-filesystem-isolation --require-process-runtime --require-notification-drain --require-verification-manifest --expected-run-id "${RUN_ID}" --expected-app-dir /opt/super_trader_quant --expected-app-user supertrader --expected-env-file /opt/super_trader_quant/.env --expected-api-base-url http://127.0.0.1:8010 --expected-api-port 8010 --output /opt/super_trader_quant/logs/goal_acceptance_last.json
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.build_verification_bundle --run-id "${RUN_ID}" --log-dir /opt/super_trader_quant/logs --output-zip /opt/super_trader_quant/logs/verification_bundle_last.zip --output-receipt /opt/super_trader_quant/logs/verification_bundle_last.json
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.verify_verification_bundle --expected-run-id "${RUN_ID}" --log-dir /opt/super_trader_quant/logs --bundle-zip /opt/super_trader_quant/logs/verification_bundle_last.zip --bundle-receipt /opt/super_trader_quant/logs/verification_bundle_last.json --check-live-files --output /opt/super_trader_quant/logs/verification_bundle_check_last.json
sudo -u supertrader /opt/super_trader_quant/.venv/bin/python -m scripts.verify_verification_round --expected-run-id "${RUN_ID}" --log-dir /opt/super_trader_quant/logs --output /opt/super_trader_quant/logs/verification_round_last.json
```

`send_telegram_test` valida envio direto pelo Telegram. `send_telegram_canary` valida o caminho real de produção usado por sinais: grava na outbox, faz fan-out para cada ID da rota escolhida, despacha e exige status `sent`.

O `goal_acceptance_report` consolida as evidências finais. Com `--require-canary`, `--require-preflight`, `--require-ops-protection`, `--require-systemd-runtime`, `--require-filesystem-isolation`, `--require-process-runtime`, `--require-notification-drain` e `--require-verification-manifest`, ele só passa depois do canário Telegram real ter gravado `logs/telegram_canary_last.json`, do preflight real ter gravado `logs/production_preflight_last.json`, da verificação HTTP protegida ter gravado `logs/ops_http_protection_last.json`, da auditoria do runtime systemd ter gravado `logs/systemd_runtime_last.json`, da auditoria de ownership/permissões ter gravado `logs/filesystem_isolation_last.json`, da auditoria de processo/bind ter gravado `logs/process_runtime_last.json`, da drenagem da outbox ter gravado `logs/notification_drain_last.json` e do manifest hashado ter gravado `logs/verification_manifest_last.json`.

Além de existirem, esses recibos precisam estar **recentes**, pertencer à **mesma rodada** de verificação, ser coerentes no **mesmo host** com **`APP_ENV=production`**, refletir a **configuração isolada esperada** e bater com o **manifest hashado** da rodada. Se você tentar reutilizar um recibo antigo, misturar recibos de execuções diferentes, combinar recibos de hosts/ambientes distintos, validar parâmetros errados de `APP_DIR`/`APP_USER`/API ou alterar um recibo depois do manifest, o aceite final bloqueia e pede nova execução no VPS.

Depois que tudo passar, o `verification_bundle_last.zip` vira o artefato mais prático para guardar ou copiar para fora do servidor, porque já embala os recibos finais e um resumo da rodada. O `verification_bundle_check_last.json` é o recibo que prova que esse ZIP ainda está coerente com os hashes registrados e com os arquivos live do diretório `logs/`.
O `verification_round_last.json` é o ápice da rodada: ele prova que o aceite operacional passou, que o bundle foi gerado e que a checagem independente do bundle também fechou na mesma rodada.

Se o `dispatch_notifications_now --require-empty` falhar, isso normalmente significa que a outbox não conseguiu se esvaziar mesmo com Telegram configurado. Nesse caso, vale inspecionar `logs/notification_drain_last.json`, `GET /ops/status` e os `last_error` das notificações antes de insistir no aceite final.

## Alertas em tempo quase real
O ciclo do scheduler tenta enviar Telegram imediatamente depois de:
- criar novos sinais no scanner;
- resolver sinais abertos como `success`, `failure` ou `expired`.

Esse despacho imediato usa `IMMEDIATE_NOTIFICATION_BATCH_SIZE` para enviar um lote grande no próprio ciclo do scanner. O job periódico de notificações permanece ativo como fallback: se o token estiver ausente, a internet cair ou o Telegram recusar temporariamente, o alerta fica pendente na outbox e será reprocessado.

Para forçar uma varredura fora do horário do scheduler, use `python -m scripts.scan_now --timeframe H1` ou `POST /ops/scan-now`. Esse ciclo usa a mesma trava do scheduler para evitar dois scanners simultâneos.

No modo produção, `POST /ops/auth-check` e `POST /ops/scan-now` exigem `X-Ops-Admin-Token` (ou `Authorization: Bearer ...`). O `deploy/verify_vps.sh` já valida que a chamada sem token é rejeitada e que as formas autenticadas funcionam, gravando o recibo `logs/ops_http_protection_last.json`.

## Docker Compose
Se preferir containers, o arquivo `deploy/docker-compose.yml` sobe API, scheduler e watchdog em containers separados, com volumes próprios para `data/` e `logs/`.

Detalhes de isolamento do modo Docker:
- a API escuta em `0.0.0.0` **apenas dentro do container**;
- no host, a porta é publicada só em `127.0.0.1:8010`;
- isso evita expor o serviço diretamente na internet e reduz o risco de conflito com outros apps do VPS.
