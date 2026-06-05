---
name: super-trader-quant
description: Trabalhar no projeto SUPER_TRADER_QUANT sem violar as regras de paper trading, backtest e memória histórica.
---

# SUPER_TRADER_QUANT Skill

## Regras essenciais
- Nunca operar dinheiro real.
- Nunca prometer lucro.
- Toda entrada de backtest deve ocorrer no próximo candle.
- Toda alteração em setup ou backtester exige testes.
- Toda integração externa deve usar `.env`.
- Atualizar README quando novos comandos forem adicionados.

## Fluxo recomendado
1. Reproduzir o problema.
2. Alterar o menor conjunto de arquivos possível.
3. Rodar `pytest`.
4. Rodar `python -m scripts.run_scanner --provider simulated`.
5. Atualizar a documentação se o comportamento mudou.
