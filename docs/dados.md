# Dados

- `yfinance`: protótipo rápido, não oficial.
- `brapi`: provider REST para ativos da B3. Use `BRAPI_TOKEN` no `.env`; a chave nunca deve ser salva no código.
- `bcb_sgs`: provider macro para séries SGS do Banco Central. Retorna `timestamp` e `value` para filtros/relatórios; não envia ordem e não substitui candles OHLC.
- `stooq`: adapter complementar; nesta implementação exige `STOOQ_API_KEY`.
- `simulated`: testes automatizados.

## Confirmação de dados

O scanner grava auditoria em cada sinal:
- `data_provider`: fonte primária usada no candle.
- `data_source_status`: `confirmed`, `mismatch`, `unconfigured`, `unavailable`, `primary_only` ou `skipped`.
- `data_source_count`: quantidade de fontes consideradas.
- `data_source_reason` e `data_source_audit_json`: motivo legível e payload de auditoria.

Configuração:
```env
SIGNAL_DATA_CONFIRMATION_MODE=auto
SIGNAL_DATA_CONFIRMATION_PROVIDER=brapi
SIGNAL_DATA_CONFIRMATION_MARKETS=BR
SIGNAL_DATA_CONFIRMATION_MAX_CLOSE_DIFF_PCT=0.5
SIGNAL_DATA_CONFIRMATION_MAX_TIMESTAMP_DRIFT_HOURS=3
```

Modos:
- `off`: não confirma fonte secundária.
- `auto`: confirma quando possível; divergência bloqueia alerta importante, mas fonte sem token apenas registra auditoria.
- `strict`: `VERDE`/`AMARELO` só passa se a fonte secundária confirmar o último candle/preço.

Essa camada aumenta rastreabilidade e reduz erro de feed. Ela não promete lucro nem acerto futuro.
