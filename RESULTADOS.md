# Retenção em sete dias · Brasil

Foram processados os 14 arquivos da revisão `7d6490e462285cf85d91eabea0f9a954fbddcd1f` do WildChat-1M. O recorte contém 11.621 conversas brasileiras observadas de abril de 2023 a abril de 2024. Pela regra principal, houve 2.385 primeiras sessões e 2.337 identidades com sete dias completos de acompanhamento. **564 voltaram (24,1%; IC 95% 22,4% a 25,9%).** A identidade é aproximada por IP com hash.

## Três achados e decisões

| Achado | Decisão |
|---|---|
| A primeira conversa com quatro turnos ou mais esteve associada a **+12,3 p.p.** de retorno frente a um turno (IC 95% +6,9 a +17,7). A direção persistiu sob as duas regras alternativas. | Testar uma pergunta de acompanhamento opcional ao fim da primeira resposta e medir retenção junto com resolução da tarefa. Intenção e dificuldade podem explicar a associação. |
| Conversas classificadas como código tiveram **−9,5 p.p.** frente a “Outros / misto” (IC 95% −17,6 a −1,5; n=87). Com a regra de 60 minutos, o intervalo inclui zero. | Validar manualmente a classificação e instrumentar resolução de tarefas de código antes de priorizar mudanças amplas. |
| GPT-4 teve diferença ajustada de **−1,1 p.p.** frente a GPT-3.5 (IC 95% −6,2 a +4,0). O intervalo admite benefício ou prejuízo. | Para uma decisão de troca de modelo, comparar qualidade e custo em experimento com alocação aleatória. |

A regressão ajusta por mês e características observadas da primeira conversa. Turnos e extensão da resposta podem refletir a dificuldade da tarefa e também mediar associações com o modelo. Os intervalos são por contraste e a exploração de vários fatores aumenta a chance de um destaque ao acaso. A tela **Fatores associados** mostra as demais estimativas.

## Distribuição e qualidade

- GPT-3.5 concentrou 7.721 conversas (66,4%). Português representou 8.797 (75,7%). Houve 6.534 conversas de um turno (56,2%).
- A semana de 15/05/2023 teve o maior volume, 616 conversas. O histórico tem semanas com volumes bem diferentes. Mostrar denominadores e o tamanho da coorte junto à taxa evita interpretar uma semana pequena como tendência.
- A classificação lexical deixou 9.930 conversas (85,5%) em “Outros / misto”. Escrita foi a maior categoria identificada (816). O gráfico de tema serve para triagem. Medir cobertura e precisão com uma amostra rotulada ajudaria a decidir se vale detalhar essa dimensão no painel.
- Os 11.621 registros usaram o primeiro horário disponível como proxy para o início porque faltava o horário da primeira mensagem do usuário. Houve 141 primeiros prompts vazios, mantidos porque ainda há uma conversa observada. Nenhuma duplicata foi removida pela chave composta usada na carga.

| Regra | Elegíveis | Retornos | Taxa |
|---|---:|---:|---:|
| IP, intervalo de 30 min | 2.337 | 564 | 24,1% |
| IP + navegador, intervalo de 30 min | 2.832 | 740 | 26,1% |
| IP, intervalo de 60 min | 2.337 | 513 | 22,0% |

## O que mudou entre 26/06 e 03/07/2023

O retorno subiu de **14,6% (6/41)** para **35,0% (14/40)**. Na decomposição por modelo e idioma, com cobertura integral nessas semanas, **+0,3 p.p.** vieram da composição e **+20,1 p.p.** das taxas dentro dos perfis. No perfil em português, a taxa passou de 4/27 para 11/28. Os ICs semanais são amplos (6,9% a 28,4% e 22,1% a 50,5%). A comparação foi selecionada após olhar as semanas e vale como ponto de investigação de produto e coleta.

## Relação com o incidente do enunciado

No snapshot público e com a métrica deste projeto, a semana de 20/11 teve 11 retornos em 64 elegíveis (17,2%) pela regra de IP, e 14 em 72 (19,4%) com IP + navegador. São números de uma coorte e um contrato diferentes dos exemplos operacionais fornecidos. Para medir a causa da divergência original, é preciso o mesmo snapshot e a definição efetivamente usada pelo relatório. A [investigação](INCIDENTE.md) inclui a consulta de reconciliação e a correção proposta.

Fonte [WildChat-1M, Allen Institute for AI](https://huggingface.co/datasets/allenai/WildChat-1M).
