# Agendamento do ETL

Execute `python iniciar.py` para preparar o ambiente e iniciar o painel local e o agendador. Use o botão **Configurar ETL** no final do menu lateral, ative o job, escolha a frequência e salve o horário de Brasília. Para execução semanal, selecione também o dia. A configuração começa desativada.

O agendador consulta a revisão atual do WildChat-1M. Se a base já usa a mesma revisão, registra **Fonte sem nova revisão**. Quando há uma revisão nova, processa os Parquet do Brasil e publica a base após a carga terminar. A cobertura da fonte aparece na visão geral; a última carga da base aparece no menu lateral. Configuração, estado da execução e auditoria ficam na página de ETL. Uma nova carga não implica conversas mais recentes se a fonte não mudou.

Na demonstração Opalstack, essa página é somente consulta e não há job de ETL configurado. O cron existente mantém o Streamlit disponível; não executa a carga. Em uma implantação futura, o worker pode ser executado com `python etl_job.py` a cada minuto, usando o Python do ambiente virtual. `ETL_ADMIN_PASSWORD` habilita alterações administrativas; esse acesso deve usar HTTPS. A configuração e o resultado da última execução ficam em `data/etl_job.sqlite`.

A publicação do SQLite é atômica: uma falha antes da substituição preserva a base anterior. Isso não é versionamento automático de cargas bem-sucedidas. As cópias históricas preservadas no servidor foram operacionais; para produção, a proposta é guardar snapshots versionados no S3 antes de promover a nova base.
