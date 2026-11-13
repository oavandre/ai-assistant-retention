# Investigação da semana de 20/11/2023

O endpoint entregou 366 / 2.034 = 18,0%. O bruto entregou 352 / 1.172 = 30,0%. Em relação à semana anterior do próprio painel, foram **+846 novos e −2 retornos**. O denominador explica a maior parte do salto observado. O status 200 confirma que a rota respondeu.

Começaria reproduzindo a requisição req_4c19a2, guardando o snapshot de carga e conferindo os numeradores/denominadores entre o JSON e o gráfico. Compararia contagens por etapa e em seguida executaria as duas regras de identidade sobre o mesmo snapshot bruto, com recorte Brasil, mesma definição de sessão e janela completa.

A divergência de contrato é visível na **carga**. O trecho `chave = f"{c['hashed_ip']}|{c['header']['user-agent']}"` fragmenta um IP em várias identidades conforme o navegador muda. O relatório usa só IP. Isso é uma hipótese forte para o crescimento do denominador. Os logs fornecidos não permitem confirmar quanto da diferença veio dessa regra ou por que se concentrou naquela semana.

## Reconciliação

SQL de diagnóstico em PostgreSQL, assumindo uma tabela de staging `raw.conversas` com as colunas do enunciado. A consulta mantém os últimos turnos e a janela de uma hora da rota legada para isolar a identidade. O parâmetro `:fim_observado` é a cobertura do snapshot validado.

```sql
WITH eventos AS (
  SELECT hashed_ip, coalesce(header->>'user-agent', '') AS ua, "timestamp" AS ts
  FROM raw.conversas
  WHERE country = 'Brazil' AND nullif(trim(hashed_ip), '') IS NOT NULL
), identidades AS (
  SELECT regra, chave, ts
  FROM eventos
  CROSS JOIN LATERAL (VALUES
    ('ip', jsonb_build_array(hashed_ip)),
    ('ip_ua', jsonb_build_array(hashed_ip, ua))
  ) AS i(regra, chave)
), primeira AS (
  SELECT regra, chave, min(ts) AS inicio
  FROM identidades GROUP BY regra, chave
)
SELECT date_trunc('week', p.inicio AT TIME ZONE 'America/Sao_Paulo')::date AS semana,
       regra, count(*) AS novos,
       count(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM identidades c
         WHERE c.regra = p.regra AND c.chave = p.chave
           AND c.ts > p.inicio + interval '1 hour'
           AND c.ts <= p.inicio + interval '168 hours'
       )) AS voltaram
FROM primeira p
WHERE p.inicio >= timestamptz '2023-11-06 00:00:00-03'
  AND p.inicio < timestamptz '2023-11-27 00:00:00-03'
  AND p.inicio + interval '168 hours' <= :fim_observado
GROUP BY 1, 2 ORDER BY 1, 2;
```

Contaria também IPs com mais de um agente por semana, agentes ausentes, datas cobertas, atraso por partição e conflitos no primeiro `turn_identifier`. Repetiria a conciliação com e sem deduplicação e com os mesmos filtros de país no retorno. A rota antiga permite retornar por outro país e usa o último turno como início. São diferenças que precisam de medições próprias.

## Correção e publicação

O teste de regressão em `test_incidente.py` reproduz a fragmentação com quatro conversas sintéticas e executa a consulta semanal do projeto. Rode `python -m unittest -v test_incidente` na raiz do repositório.

| Regra de identidade | Novos elegíveis | Retornos em 7 dias | Taxa |
|---|---:|---:|---:|
| IP + navegador | 3 | 0 | 0% |
| IP | 2 | 1 | 50% |

No exemplo, o mesmo IP inicia uma sessão no Brasil e volta dois dias depois com outro navegador. Com a regra antiga de identidade, a segunda sessão cria uma nova identidade. A quarta conversa é de outro país e fica fora do recorte, de modo que o segundo IP brasileiro continua sem retorno. Todos os usuários têm a janela completa. Os resultados demonstram o mecanismo com a métrica do projeto. A reprodução dos valores do incidente depende do snapshot operacional original.

Na carga legada, validaria a presença de IP e substituiria a chave pela identidade compartilhada com o relatório.

```python
ip = (c.get("hashed_ip") or "").strip()
if not ip:
    registrar_descarte("ip_ausente")
    continue
usuario_id = sha256(ip.encode("utf-8")).hexdigest()
```

No SQL legado, incluiria `AND c.pais = $3` no retorno e aplicaria a janela completa usando a data de cobertura da partição. Para a métrica proposta, a implementação executável está em `etl.cohort` e `analysis.WEEKLY_SQL`. Ela usa início de sessão e sete dias de observação.

Reprocessaria todo o histórico em uma tabela paralela, pois identidades já fragmentadas não se recompõem com uma mudança na carga diária. Validaria unicidade, volumes e os dois contadores em paralelo com o relatório. Publicaria carga e painel com a mesma versão do contrato, invalidaria cache e comunicaria a revisão das semanas já divulgadas. Preservaria o snapshot anterior para reverter a publicação.

**Durante.** “O painel mostra 18%, mas a contagem de novos usuários subiu sem uma queda correspondente nos retornos. Estamos conciliando a definição usada pelo painel e pelo relatório. Segure decisões sobre a queda até reconciliarmos os números.”

**Conclusão com a evidência disponível.** “Confirmamos que o painel e o relatório agrupavam usuários de formas diferentes. O teste mostrou que uma troca de navegador pode contar uma pessoa duas vezes e perder seu retorno. Para quantificar o impacto naquela semana e publicar uma taxa corrigida, precisamos reprocessar o snapshot original e conferir os dois contadores.”
