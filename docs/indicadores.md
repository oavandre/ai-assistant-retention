# Contrato dos indicadores

Fonte: `allenai/WildChat-1M`, revisão fixada em `etl.REVISION`, país Brazil. O horário da carga não é a cobertura das conversas. A cobertura efetiva fica na auditoria; as coortes usam America/Sao_Paulo e retorno em até 168 horas. Sem filtro, o painel usa todo o histórico disponível.

## Telas e perguntas

| Tela | Pergunta | Escolha visual |
|---|---|---|
| Visão geral | Quanto se retorna e onde investigar? | Indicadores, três achados com decisões, linha temporal e matriz de coortes |
| Fatores de retenção | Quais experiências estão associadas ao retorno? | Pontos e intervalos para comparar magnitude e incerteza; barras para decompor mudança semanal |
| Exploração de dados | Onde o uso se concentra? | Linha por semana e barras para categorias; tema e tamanho abrangem todo o histórico |
| Usuários e coortes | Quando ocorre o retorno e quanto depende da definição? | Matriz acumulada D0–D7 e tabela de sensibilidade |
| Qualidade e incidentes | A queda é de uso ou de mensuração? | Comparação das duas fontes do enunciado e dos contadores; filtros da base pública não se aplicam |
| Configurar ETL | Qual a cobertura, a última carga e o estado do job? | Estado e auditoria operacional; consulta na demonstração pública |

## Base analítica

| Tabela | Granularidade | Uso |
|---|---|---|
| `coortes` | Uma primeira sessão por identidade aproximada e regra | Elegibilidade, retorno, dia de retorno e atributos da primeira conversa; sem identificador persistido |
| `volume_semanal` | Semana × modelo × idioma × estado | Quantidade de conversas e soma de turnos |
| `uso` | Dimensão × categoria, histórico completo | Distribuições pré-calculadas de semana, modelo, idioma, tema e tamanho |
| `auditoria` | Item × valor, carga atual | Origem, cobertura, contagens e horário de publicação |

`ip`, `ip_ua` e `ip_60` são análises alternativas da mesma população, não grupos disjuntos. Nunca somar as três regras. O dashboard não lê Parquet, texto de conversa, IP ou navegador. O arquivo analítico contém atributos por identidade aproximada; não é destinado a download público.

## Consultas equivalentes às métricas da interface

Os parâmetros `:inicio` e `:fim` são semanas iniciais inclusivas, não datas arbitrárias. `:regra` seleciona uma única regra. Os exemplos usam o filtro de modelo opcional (`NULL` = Todos); idioma e estado seguem a mesma igualdade parametrizada. Em retenção, o filtro usa a primeira conversa; em volume, usa cada conversa. O código da interface aplica esses filtros antes de agregar.

### Novos, elegíveis, retornos e taxa

Novos inclui as identidades sem acompanhamento completo. O denominador da taxa é apenas elegíveis, nunca o total de novos. Abaixo de 30 elegíveis, a interface oculta taxa e contagem de retornos do cartão; a linha semanal e a matriz também suprimem taxas pequenas.

```sql
SELECT count(*) AS novos,
       sum(elegivel) AS elegiveis,
       coalesce(sum(voltou), 0) AS retornos,
       CASE WHEN sum(elegivel) >= 30
            THEN 1.0 * sum(voltou) / sum(elegivel) END AS taxa
FROM coortes
WHERE regra = :regra AND semana BETWEEN :inicio AND :fim
  AND (:modelo IS NULL OR modelo = :modelo);
```

Para a série semanal, acrescentar `semana` ao SELECT e `GROUP BY semana ORDER BY semana`. A consulta operacional equivalente está em `analysis.WEEKLY_SQL`. O intervalo de 95% da taxa é Wilson, calculado por `analysis.wilson(retornos, elegiveis)` em Python; não mede viés da coleta ou erro de identidade.

### Conversas e média de turnos

```sql
SELECT coalesce(sum(conversas), 0) AS conversas,
       1.0 * sum(soma_turnos) / nullif(sum(conversas), 0) AS media_turnos
FROM volume_semanal
WHERE semana BETWEEN :inicio AND :fim
  AND (:modelo IS NULL OR modelo = :modelo);
```

O denominador da média é conversas, não usuários. Sem conversas, a interface mostra um traço.

### Matriz acumulada

```sql
WITH dias(dia) AS (VALUES (0),(1),(2),(3),(4),(5),(6),(7))
SELECT semana, dia, count(*) AS elegiveis,
       CASE WHEN count(*) >= 30 THEN
         avg(CASE WHEN dia = 0 OR dia_retorno <= dia THEN 1.0 ELSE 0.0 END)
       END AS retorno_acumulado
FROM coortes CROSS JOIN dias
WHERE regra = :regra AND elegivel = 1
  AND semana BETWEEN :inicio AND :fim
  AND (:modelo IS NULL OR modelo = :modelo)
GROUP BY semana, dia ORDER BY semana, dia;
```

D0 é a sessão inicial, por definição 100%; D1–D7 são o retorno acumulado até 24h, 48h, ..., 168h. Não são a retenção em cada dia isolado. A tela seleciona até sete coortes recentes com base suficiente.

### Distribuições

```sql
SELECT modelo AS grupo, sum(conversas) AS conversas
FROM volume_semanal
WHERE semana BETWEEN :inicio AND :fim
  AND (:modelo IS NULL OR modelo = :modelo)
GROUP BY modelo;

-- Tema e tamanho: histórico completo, sem os filtros globais.
SELECT grupo, conversas FROM uso WHERE dim = :dim;
```

A interface exibe grupos com pelo menos 30 conversas e até 15 categorias; por isso, barras visíveis podem não somar o total. O denominador de uma participação deve incluir todos os grupos, inclusive os ocultos.

### Fatores e mudança semanal

```sql
SELECT * FROM coortes
WHERE regra = :regra AND elegivel = 1
  AND semana BETWEEN :inicio AND :fim
  AND (:modelo IS NULL OR modelo = :modelo);
```

Essas linhas alimentam `analysis.effects`: regressão linear de probabilidade, diferenças em pontos percentuais e IC 95% HC3. Não há SQL que produza sozinho o ajuste estatístico. Exige 100 observações e ao menos 20 retornos e 20 não retornos; níveis com menos de 30 são agrupados. Falta de variação ou matriz sem posto completo impede a estimativa. Referência é o nível mais frequente de cada fator no recorte.

`analysis.weekly_change` usa a mesma população elegível e separa composição e taxas nos perfis modelo × idioma. Exige 30 identidades em cada semana, 10 por perfil em ambas e cobertura mínima de 80%. A seleção do maior movimento é exploratória. Cobertura parcial é mostrada separadamente da decomposição.

## Serviço, desempenho e limites

O frontend Streamlit chama funções Python no servidor; não existe API REST pública com rotas próprias. Nome, entrada e saída dessas operações estão em `DECISOES.md`. A rota Next.js do incidente pertence ao enunciado, não à implementação entregue.

Sessões, elegibilidade e distribuições são pré-calculadas. Consultas e ajustes usam cache de uma hora; a versão do arquivo invalida a consulta e os dados retornados alimentam a chave do ajuste. O índice de coortes começa por regra e semana. Para homologação, medir SQL, ajuste e renderização separadamente, com cache frio/quente, repetindo recortes fixos para reportar p50/p95. Não há benchmark de produção nem alertas automáticos implantados nesta demonstração.
