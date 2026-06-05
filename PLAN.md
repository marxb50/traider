# PLAN — SUPER_TRADER_QUANT

## Objetivo da primeira entrega
Construir um MVP operacional, separado de qualquer outro serviço, com foco em swing/position trade em **paper trading**, capaz de:

1. monitorar 100 ativos demo do Brasil, 50 dos EUA e 50 do Reino Unido;
2. gerar sinais de setups diariamente;
3. registrar automaticamente se cada sinal terminou em **sucesso**, **falha** ou **expiração**;
4. manter memória histórica por ativo/setup;
5. enviar alertas simulados por Telegram;
6. rodar continuamente em um processo próprio, com banco, configuração e logs próprios.

## Decisões técnicas
- **Python 3.11+ / 3.12 compatível**.
- **FastAPI** para API e health checks.
- **Streamlit** para o MVP visual.
- **SQLite** para a primeira versão, em arquivo exclusivo do projeto.
- **SQLModel** para persistência.
- **APScheduler** para execução contínua do scanner e do resolvedor de sinais.
- **Adapters de dados** para evitar espalhar chamadas de API.
- **yfinance** como protótipo rápido; **Brapi** como fonte/confirmador BR; **BCB SGS** para macro; **Stooq** como adapter complementar; **simulated_provider** para testes.
- **Telegram Bot API** apenas para alertas simulados.
- **Quorum de dados configurável** para impedir alerta importante quando fontes de mercado divergirem.
- **Entrada no próximo candle** no backtest para reduzir lookahead bias.
- **Isolamento de deploy** via pasta própria, `.env`, banco próprio, unidade systemd e opção de Docker Compose.

## Mudanças pedidas nesta revisão
- Aumentar os ativos demo para **200 no total**: 100 do Brasil, 50 dos EUA e 50 do Reino Unido.
- Transformar a memória histórica em memória viva:
  - detectar o sinal;
  - acompanhar o resultado;
  - gravar se deu certo, deu errado ou expirou;
  - atualizar estatísticas por ativo/setup.
- Rodar 24/7 com scheduler recorrente.
- Enviar alertas inicialmente para os IDs configurados no `.env`.
- Preparar configuração para múltiplos IDs depois.
- Manter tudo separado dos outros serviços do VPS.

## Fases
### Fase 1 — Núcleo operacional
- Estrutura do projeto.
- Banco.
- 200 ativos demo.
- Providers.
- 35 setups.
- Scanner.
- Resolução de sinais.
- Memória histórica.
- Telegram.
- Testes principais.

### Fase 2 — Produto visível
- Dashboard Streamlit.
- Tela de ativos.
- Radar de setups.
- Tela de memória histórica.
- Backtest básico.
- Documentação completa.

### Fase 3 — Deploy e endurecimento
- Serviço contínuo.
- Logs rotativos.
- Health check.
- Heartbeat do scheduler e ciclo inicial no boot.
- Docker/systemd.
- Verificador de prontidão de deploy.
- Revisão final de falhas.

## Critérios de pronto
- `python -m scripts.seed_demo` popula 200 ativos.
- `python -m scripts.validate_demo_assets` confirma que os 200 ativos demo retornam histórico no provider real de protótipo.
- `python -m scripts.run_scanner --provider simulated` gera sinais sem erro.
- `pytest` passa.
- Sinais abertos são resolvidos em sucesso/falha/expiração.
- A memória por ativo/setup é atualizada automaticamente.
- Telegram envia quando `TELEGRAM_BOT_TOKEN` estiver configurado.
- Cada sinal novo registra auditoria de fonte de dados; em `SIGNAL_DATA_CONFIRMATION_MODE=strict`, `VERDE`/`AMARELO` só é enviado após confirmação secundária.
- API responde em `/health`.
- API expõe `GET /ops/status` com heartbeat do scheduler.
- `python -m scripts.check_deploy_readiness` confirma estrutura, ativos, jobs e configuração mínima.
- `python -m scripts.check_deploy_readiness --strict --runtime` confirma configuração de produção e heartbeat recente do scheduler.
- O projeto pode rodar em processo isolado sem depender de outros apps.
