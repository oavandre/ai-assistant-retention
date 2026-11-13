# Decisões de arquitetura e de negócio

## ADR 01 · Aplicação local em Python

**Contexto.** O cliente precisa consultar coortes e entender as diferenças entre perfis. A entrega precisa rodar localmente a partir da fonte bruta.

**Opções.** Streamlit e SQLite em um serviço, ou frontend separado, API REST e PostgreSQL. A primeira opção reduz a infraestrutura e mantém o cálculo no mesmo ecossistema.

**Escolha.** Streamlit para navegação, filtros e gráficos. Funções Python e SQL constituem a camada de serviço. SQLite guarda `coortes` (uma linha por identidade observada e regra), `uso` (contagem por dimensão e grupo) e `auditoria` (contagens da carga e cobertura). O ETL publica um arquivo novo após o processamento completo.

```
WildChat-1M (Parquet) → PyArrow (Brasil) → Python (sessões e variáveis)
                                           ↓
Streamlit (duas telas) ← consultas e modelo ← SQLite (snapshot)
```

### Interface do backend

| Operação | Entrada | Saída |
|---|---|---|
| Consulta de coortes (`WEEKLY_SQL`) | Regra, semana inicial e final inclusivas | Semana, novos, elegíveis, retornos, taxa |
| `effects(rows)` | Coortes elegíveis no recorte | Contraste ajustado, IC 95%, grupo e referência |
| `weekly_change(rows)` | Coortes elegíveis no recorte | Par de semanas, variação total, composição, taxas e cobertura |
| Consulta a `uso` | Dimensão | Grupo e volume de conversas |

O servidor Streamlit entrega as duas telas em uma aplicação, com sessão WebSocket. As operações acima são chamadas internas do backend Python. As consultas reais estão em `analysis.py` e `app.py`.

### Operação na AWS

Agendar carga em ECS Fargate com EventBridge, leitura do Parquet em S3 privado e publicação do snapshot SQLite versionado em S3. O serviço Streamlit em ECS Fargate lê o snapshot para armazenamento local e recebe tráfego por ALB com TLS e autenticação. Um novo deploy fixa a versão do snapshot. IAM dá à carga escrita no bucket analítico e ao painel apenas leitura. CloudWatch recebe logs e métricas. O projeto não usa LLM na carga. Os custos recorrentes previstos são processamento, armazenamento, ALB, tráfego e logs.

Pré-calculamos sessões, elegibilidade e distribuições. O índice começa por regra e semana. Cache de consultas e modelo dura uma hora. O timestamp do arquivo invalida consultas quando a base muda. Em homologação, medir p50/p95 de SQL, ajuste e render, com cache frio e quente. Registrar duração e erro por operação, versão da carga e contagens, sem conteúdo ou identidade. Conciliar semanalmente novos, elegíveis e retornos contra cálculo independente sobre snapshot comum. Alertar para partição ausente, alterações de esquema, salto de volume ou quebra de `retornos ≤ elegíveis ≤ novos`. Promover o mesmo container e snapshot validados de homologação para produção. Versionar esquema e reverter pelo snapshot anterior.

Para outros países, parametrizar país, localização dos textos e fuso IANA do mercado. Comparar coortes com o mesmo horizonte de 168h e cobertura de observação. Uma semana é local a cada mercado e diferenças de composição devem aparecer ao lado da taxa. Avaliar partições por país e período com o aumento de volume.

## BDR 01 · Identidade, sessão e retorno

**Opções.** IP com hash é comparável ao relatório do incidente, mas agrupa pessoas em redes compartilhadas. IP e agente separam alguns dispositivos, mas dividem a mesma pessoa após troca de navegador ou versão. IP dinâmico também fragmenta histórico. Usamos IP com hash como proxy principal e mostramos IP + agente como sensibilidade.

**Sessão.** Agrupar conversas cujo início ocorre até 30 minutos após o maior término anterior. Mostrar 60 minutos como sensibilidade. A coorte é a semana da primeira sessão observada em America/Sao_Paulo. Um retorno é o início de outra sessão em até 168 horas, inclusive, desde o início da primeira. Incluímos somente identidades observáveis por toda a janela a partir da primeira sessão. A cobertura final é o maior timestamp observado no recorte Brasil. Lacunas na coleta podem reduzir a taxa e usuários de antes da coleta podem ser classificados como novos.

O WildChat registra timestamps principalmente nas respostas. Quando falta o horário da primeira mensagem do usuário, usamos o menor horário disponível na conversa. Para o término usamos o maior horário da linha e dos turnos. A latência da resposta pode deslocar sessões próximas ao limiar. Descartes, duplicatas, prompts vazios e agentes ausentes são contabilizados na auditoria. A edição pública também exclui conteúdo moderado e sensível, o que altera a cobertura da trajetória de uso.

**Indicadores.** Novos = contagem de identidades com primeira sessão na semana. Elegíveis = soma do indicador de janela completa. Retornos = soma de `voltou` entre elegíveis. Taxa = retornos ÷ elegíveis, com IC de Wilson de 95% na visão geral. Taxas ficam ocultas quando n < 30. A série temporal evidencia mudança de coorte e as barras mostram a concentração do uso.

A matriz D0–D7 usa a mesma população elegível da taxa. D0 representa a primeira sessão. Em D1 a D7, o numerador é o número de identidades cujo retorno ocorreu até aquele horizonte de 24 horas por dia. Os filtros de modelo, idioma e estado usam os atributos da primeira conversa para retenção e os de cada conversa para volume. O estado é inferido pelo dataset.

## BDR 02 · O que medir na primeira experiência

Usar primeira conversa da primeira sessão como exposição. Modelo é a família registrada. Idioma é a classificação predominante da conversa. Turnos são os registrados na linha. Extensão é a contagem de caracteres da primeira resposta, com corte exploratório em 500. Possível recusa é uma heurística lexical aplicada ao começo dessa resposta. Tema usa palavras-chave no primeiro prompt, com categoria mista para múltiplos ou nenhum sinal. Classificar sem LLM reduz custo e transferência de texto. Temas e recusas são proxies sujeitos a erro. Qualidade percebida exige um sinal do usuário, como avaliação de resolução.

O modelo linear de probabilidade estima diferenças em pontos percentuais com IC 95% HC3, condicionado a mês da coorte e fatores da primeira experiência. O grupo mais frequente é referência, níveis com menos de 30 observações são agrupados e efeitos com base pequena são omitidos. Os ICs são marginais por contraste. Variáveis como turnos e extensão podem mediar o efeito do modelo. Intenção, experiência anterior, motivos de escolha e qualidade percebida podem confundir associações. Para inferir efeito de uma mudança, propor teste aleatório com janela de observação fixa.

Para explicar uma semana, a decomposição simétrica soma variação da composição ponderada pela taxa média e variação das taxas ponderada pelo peso médio. Os perfis combinam GPT-4 e idioma português. A análise requer pelo menos 10 elegíveis por perfil em ambas as semanas e 80% de cobertura em cada uma.

**Privacidade e decisões em aberto.** O painel exibe agregados e o snapshot analítico exclui texto, IP, agente e identificadores. Confirmar com produto a definição de usuário, tamanho mínimo, horizonte e se será possível instrumentar uma conta consentida e feedback. Validar com responsáveis pelos dados as regras de acesso, retenção e transferência antes de operar.

## BDR 03 · Leitura da visão geral

**Contexto.** O público do desafio é de negócio, sem perfil técnico. Uma lista de coeficientes não explica sozinha onde investir.

**Opções.** Destacar automaticamente os três maiores coeficientes ou apresentar três perguntas estáveis de produto com os resultados do recorte selecionado.

**Escolha.** A visão geral começa pelo retorno em cada 100 identidades elegíveis, com contadores e intervalo de confiança. Em seguida, relaciona primeira conversa, tarefas de código e escolha do modelo a decisões de investigação ou experimento. Esses temas correspondem aos três achados documentados; não são anunciados como os três maiores efeitos em todos os filtros. Cada comparação mostra referência, tamanho do grupo e incerteza. Quando o grupo é a referência, está ausente ou não há estimativa válida, a tela informa que a comparação está indisponível. Recomendações são hipóteses para validar, sem promessa de ganho causal. Os demais fatores continuam acessíveis no gráfico e na tela analítica.

### Leitura dos fatores e da mudança semanal

A tela de fatores mostra a referência de cada comparação no gráfico e explica ponto, intervalo de confiança e linha de zero antes das estimativas. A tabela detalhada fica recolhida. Na investigação semanal, pontos e intervalos de Wilson mostram as taxas e sua incerteza; barras separam a contribuição da composição dos perfis e a das taxas dentro deles. A seleção automática da maior variação elegível é explicitamente exploratória. Quando a cobertura dos perfis é parcial, uma terceira barra mostra a diferença entre a variação total e a soma dos componentes comparáveis, sem atribuir causa aos perfis excluídos. Nenhuma decomposição é apresentada como evidência causal.

## Uso de IA

Usei Codex para ler o enunciado, estruturar o código e revisar as definições e a documentação. A validação inclui a execução do pipeline, o teste da janela e as verificações das telas conforme registradas na entrega. O tempo dedicado pelo candidato deve ser registrado pelo próprio candidato antes do envio.
