# Agendamento do ETL

Execute `python run.py` para iniciar o painel local e o agendador. Abra **Agendamento do ETL**, ative o job, escolha a frequência e salve o horário de Brasília. Para execução semanal, selecione também o dia. A configuração começa desativada.

O agendador consulta a revisão atual do WildChat-1M. Se a base já usa a mesma revisão, registra **Fonte sem nova revisão**. Quando há uma revisão nova, processa os Parquet do Brasil e publica a base após a carga terminar. A data de cobertura da fonte e o horário da última execução aparecem na visão geral.

No servidor, execute `python etl_job.py` a cada minuto pelo cron, usando o Python do ambiente virtual. Configure `ETL_ADMIN_PASSWORD` no ambiente do Streamlit para habilitar as alterações de agendamento. Use HTTPS para acessar a administração. A configuração e o resultado da última execução ficam em `data/etl_job.sqlite`.
