# Retenção em Assistentes de IA

Pipeline em Python e painel em Streamlit para analisar o retorno em até sete dias no recorte brasileiro do WildChat-1M. A base analítica em SQLite alimenta as coortes, os filtros e as estimativas dos fatores associados ao retorno.

No recorte analisado, 564 de 2.337 identidades elegíveis voltaram em até sete dias (24,1%). A análise usa IP com hash como aproximação de identidade. Os efeitos estimados descrevem associações. [Veja os resultados](RESULTADOS.md).

[Acesse a demonstração do painel](https://retencao.ox.opalstacked.com/).

A demonstração de portfólio está no Opalstack. Ela não é a implantação AWS solicitada no desafio: a entrega reproduzível é local, e a arquitetura proposta para produção na AWS está em [DECISOES.md](DECISOES.md). Essa diferença deve ser explicitada na avaliação.

No Opalstack, o proxy encaminha as requisições HTTPS ao Streamlit na porta interna do aplicativo. O cron do usuário do painel verifica o serviço a cada minuto e tenta iniciá-lo quando o processo está ausente. Os logs de execução ficam em `logs/streamlit.log` no servidor.

![Visão geral do painel com indicadores de retenção, série semanal e matriz de coortes](docs/painel.jpg)

## Como rodar

Com Python 3.13 instalado, execute na raiz do repositório:

```bash
python iniciar.py
```

O comando cria `.venv`, instala as dependências e chama `run.py`, que prepara a base quando ela não existe e inicia o painel e o agendador local (inicialmente desativado). É necessário acesso ao PyPI e ao Hugging Face e espaço para os arquivos temporários. Abra o [painel local](http://localhost:8501). A primeira carga baixa cerca de 3,36 GB de Parquet e filtra as conversas brasileiras. Para reprocessar, use `python iniciar.py --rebuild`.

Se as dependências já estiverem instaladas no Python ativo, `python run.py` continua disponível. Para rodar os testes no ambiente criado, use `.venv\\Scripts\\python -m unittest -v` no Windows ou `.venv/bin/python -m unittest -v` no Linux/macOS. O teste de integração usa Parquet sintético temporário, sem rede ou alteração da base real.

Consulte o [contrato dos indicadores e as consultas SQL](docs/indicadores.md) e a [operação do ETL](docs/agendamento-etl.md).

Consulte [as decisões de arquitetura e negócio](DECISOES.md) e [a investigação do incidente de retenção](INCIDENTE.md). Os dados vêm do Allen Institute for AI e estão sob a licença ODC-BY. [Fonte dos dados](https://huggingface.co/datasets/allenai/WildChat-1M)
