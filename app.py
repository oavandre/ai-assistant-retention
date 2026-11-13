from html import escape
from datetime import datetime, timedelta
from hmac import compare_digest
import os
import altair as alt
import pandas as pd
import streamlit as st

from analysis import MIN_N, effects, read, weekly_change, wilson
from etl import DB, ROOT
from etl_job import DAYS, MESSAGES, ZONE, save, settings

PURPLE = "#6b18d4"
st.set_page_config(page_title="Retenção do Assistente de IA", layout="wide")
st.markdown("""<style>
[data-testid="stSidebar"] {background:linear-gradient(160deg,#190e31,#211239); color:#f6eeff}
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p {color:#f2e9ff}
[data-testid="stSidebar"] [data-baseweb="select"] > div {background:#30204d; color:white; border-color:#6e5094}
[data-testid="stSidebar"] [data-baseweb="select"] input {color:white}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
  background:#eee3ff;color:#211239;border-color:#be9de7
}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] p {color:#211239}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {background:#dfc8ff}
[data-testid="stSidebarCollapseButton"] button {
  color:#f6eeff;background:#392554;border:1px solid #8062a5;border-radius:8px
}
[data-testid="stSidebarCollapseButton"] button:hover,
[data-testid="stSidebarCollapseButton"] button:focus-visible {
  color:#fff;background:#513475;border-color:#bd9ee0
}
[data-testid="stSidebarCollapseButton"] button [data-testid="stIconMaterial"] {color:inherit}
.etl-sidebar-load {color:#e2d1f5;font-size:.7rem;line-height:1.35}
[data-testid="stSidebar"] [role="slider"] + div {color:#e5c8ff}
[data-testid="stAppDeployButton"] {display:none}
[data-testid="stMainBlockContainer"] {padding:2rem clamp(1rem,3vw,2rem) 2rem; max-width:1650px}
[data-testid="stMainBlockContainer"] h1 {font-size:clamp(1.9rem,3.1vw,2.4rem);padding-bottom:.1rem}
[data-testid="stMainBlockContainer"] [data-testid="stColumn"] {min-width:0}
[data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] {
  white-space:normal;overflow-wrap:anywhere
}
[data-testid="stMetricValue"] > div {white-space:normal;overflow-wrap:anywhere}
.st-key-trend,.st-key-cohort,.st-key-overview-effects,.st-key-findings,.st-key-recommendations {
  background:#fff;border-radius:15px;box-shadow:0 2px 7px #2112390c
}
.st-key-trend,.st-key-cohort {min-height:350px}
.brand {font-size:1.8rem;font-weight:800;color:#fff;letter-spacing:-.05em;margin:0 0 .75rem}
.brand span {color:#bc82ff;margin-right:.4rem}
.metrics {display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin:8px 0 12px}
.kpi {background:white;border:1px solid #ebe5f3;border-radius:14px;padding:14px 12px;box-shadow:0 2px 6px #2112390d}
.kpi strong {display:block;font-size:clamp(1.35rem,2.1vw,2rem);line-height:1.25;color:#180f2d}
.kpi small {display:block;color:#524660;font-size:.75rem;margin-top:4px}
.kpi:nth-child(3) {background:#f1e4ff}
.kpi:nth-child(3) strong {color:#6714cc}
.kpi i {display:inline-block;color:#6714cc;background:#f3eaff;border-radius:50%;padding:4px 8px;margin-right:5px;font-style:normal}
@media(max-width:1050px){.metrics{grid-template-columns:repeat(auto-fit,minmax(145px,1fr))}}
@media(max-width:740px){
  [data-testid="stMainBlockContainer"] [data-testid="stHorizontalBlock"]{flex-direction:column}
  [data-testid="stMainBlockContainer"] [data-testid="stColumn"]{width:100%!important;flex:auto!important}
}
.heat {width:100%;border-spacing:2px;text-align:center;font-size:.78rem}
.heat-scroll {max-width:100%;overflow-x:auto}
.heat th,.heat td {padding:6px 3px;white-space:nowrap}
.heat th {background:#f3edf9}
.finding {border-left:3px solid #b884f9;padding:0 0 0 .75rem;margin:.7rem 0;font-size:.9rem}
[data-testid="stMainBlockContainer"]:has(.st-key-etl-content) {padding-top:4rem}
.st-key-etl-content [data-testid="stVerticalBlock"] {gap:.65rem}
.etl-status {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%, 150px),1fr));gap:8px}
.etl-status div {padding:8px 10px;background:#fff;border:1px solid #ebe5f3;border-radius:8px;overflow-wrap:anywhere}
.etl-status span,.etl-status strong {display:block;font-size:.8rem;line-height:1.35}
.etl-status span {color:#524660}
</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=3600)
def query(sql, params, version):
    return read(sql, params)


@st.cache_data(ttl=3600)
def estimate(rows):
    return effects(rows)


def percent(value):
    return f"{value:.1%}".replace(".", ",")


def integer(value):
    return f"{int(value):,}".replace(",", ".")


def rate(k, n):
    return percent(k / n) if n >= MIN_N else "Base pequena"


def cards(weekly, volume):
    n, k = int(weekly.elegiveis.sum()), int(weekly.voltaram.sum())
    count = int(volume.conversas.sum())
    low, high = wilson(k, n) if n >= MIN_N else (None, None)
    interval = f"IC 95% {percent(low)} a {percent(high)}" if low is not None else "Mínimo de 30 elegíveis"
    items = [
        ("＋", "Novos usuários", integer(weekly.novos.sum()), "Identidades na primeira sessão"),
        ("↩", "Retornaram em 7 dias", integer(k) if n >= MIN_N else "—", f"{integer(n)} elegíveis"),
        ("◷", "Taxa de retenção (7d)", rate(k, n), interval),
        ("▤", "Conversas", integer(count), "Conversas no recorte"),
        ("▱", "Média de turnos", f"{volume.soma_turnos.sum()/count:.1f}".replace(".", ",") if count else "—",
         "Por conversa no recorte"),
    ]
    html = "".join(f'<div class="kpi"><div><i>{icon}</i><b>{title}</b></div>'
                   f'<strong>{value}</strong><small>{note}</small></div>'
                   for icon, title, value, note in items)
    st.markdown(f'<div class="metrics">{html}</div>', unsafe_allow_html=True)


def trend(weekly):
    frame = weekly.copy()
    frame["taxa"] = frame["taxa"].where(frame["elegiveis"].ge(MIN_N))
    base = alt.Chart(frame).encode(
        x=alt.X("semana:T", scale=alt.Scale(type="utc"),
                axis=alt.Axis(format="%d/%m/%y", title=None, tickCount=8)),
        y=alt.Y("taxa:Q", axis=alt.Axis(format="%", title=None), scale=alt.Scale(zero=True)),
        tooltip=[alt.Tooltip("semana:N", title="Semana"),
                 alt.Tooltip("elegiveis:Q", title="Elegíveis"), alt.Tooltip("voltaram:Q", title="Retornos"),
                 alt.Tooltip("taxa:Q", title="Retenção", format=".1%")],
    )
    chart = base.mark_area(color=PURPLE, opacity=.12) + base.mark_line(
        color=PURPLE, point=alt.OverlayMarkDef(filled=True, color=PURPLE)
    )
    st.altair_chart(chart.properties(height=200), width="stretch")


def cohort_heatmap(rows):
    eligible = rows.loc[rows.elegivel.eq(1)]
    if eligible.empty:
        st.info("Nenhuma coorte elegível neste recorte.")
        return
    groups = list(eligible.groupby("semana", sort=True))
    reliable = [(week, group) for week, group in groups if len(group) >= MIN_N]
    groups = (reliable or groups)[-7:]
    header = "<th>Coorte</th>" + "".join(f"<th>D{day}</th>" for day in range(8))
    body = []
    for week, group in groups:
        values = [1.0] + [group.dia_retorno.le(day).mean() for day in range(1, 8)]
        cells = []
        for day, value in enumerate(values):
            if len(group) < MIN_N:
                cells.append("<td>—</td>")
                continue
            color = f"rgba(107,24,212,{.06 + value * .87:.2f})"
            text = "white" if day == 0 else "#251138"
            cells.append(f'<td style="background:{color};color:{text}">{percent(value)}</td>')
        date = pd.Timestamp(week).strftime("%d/%m")
        body.append(f'<tr><th title="{len(group)} elegíveis">{date}</th>{"".join(cells)}</tr>')
    st.markdown(f'<div class="heat-scroll" tabindex="0" role="region" aria-label="Tabela de coortes">'
                f'<table class="heat"><thead><tr>{header}</tr></thead>'
                f'<tbody>{"".join(body)}</tbody></table></div>', unsafe_allow_html=True)
    st.caption("D0 é a sessão inicial. D1–D7 mostram o retorno acumulado em até sete coortes recentes com pelo menos 30 elegíveis. — indica base pequena.")


def forest(results, limit=None):
    if results.empty:
        st.info("Base insuficiente ou fatores redundantes para estimar diferenças neste recorte.")
        return
    frame = results.head(limit).copy() if limit else results.copy()
    frame["Comparação"] = frame["Fator"] + " · " + frame["Grupo"] + " vs. " + frame["Referência"]
    order = frame["Comparação"].tolist()
    y = alt.Y("Comparação:N", sort=order, title=None, axis=alt.Axis(labelLimit=220))
    chart = alt.Chart(frame)
    intervals = chart.mark_rule(color=PURPLE).encode(
        y=y, x=alt.X("Limite inferior:Q", title="Diferença ajustada (p.p.)"), x2="Limite superior:Q"
    )
    dots = chart.mark_circle(size=85, opacity=1).encode(
        y=y, x="Efeito (p.p.):Q",
        color=alt.condition(alt.datum["Efeito (p.p.)"] >= 0, alt.value(PURPLE), alt.value("#ba3859")),
        tooltip=["Fator", "Grupo", "Referência", "n",
                 alt.Tooltip("Efeito (p.p.):Q", format=".2f"),
                 alt.Tooltip("Limite inferior:Q", format=".2f"),
                 alt.Tooltip("Limite superior:Q", format=".2f")]
    )
    zero = alt.Chart(frame.iloc[:1]).mark_rule(color="#554665", strokeDash=[4, 3]).encode(x=alt.datum(0))
    st.altair_chart((zero + intervals + dots).properties(height=max(155, 27 * len(frame))), width="stretch")
    st.caption("Diferenças em pontos percentuais com IC 95%, ordenadas pela magnitude. Passe o mouse para ver a comparação completa e o tamanho do grupo.")


def weekly_story(rows):
    st.subheader("O que mudou de uma semana para outra?")
    movement = weekly_change(rows)
    if not movement:
        st.info("Sem duas semanas consecutivas com cobertura suficiente para decompor a variação. Amplie os filtros.")
        return
    previous, current, total, mix, within, coverage = movement
    sample = rows.loc[rows.semana.isin([previous, current])]
    summary = sample.groupby("semana")["voltou"].agg(["size", "sum"]).reset_index()
    summary["Semana"] = pd.to_datetime(summary.semana).dt.strftime("%d/%m/%Y")
    summary["Taxa"] = summary["sum"] / summary["size"]
    intervals = [wilson(k, n) for k, n in zip(summary["sum"], summary["size"])]
    summary["Inferior"], summary["Superior"] = zip(*intervals)
    delta = f"{100 * total:+.1f}".replace(".", ",")
    st.write(f"**Variação de {delta} pontos percentuais** entre as coortes de "
             f"{pd.Timestamp(previous):%d/%m/%Y} e {pd.Timestamp(current):%d/%m/%Y}.")
    st.caption("Par selecionado automaticamente pela maior variação absoluta entre semanas consecutivas que passam nos critérios de cobertura. "
               "É uma investigação exploratória, não uma tendência confirmada.")
    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown("**Quanto o retorno mudou?**")
        chart = alt.Chart(summary)
        x = alt.X("Semana:N", title="Semana da primeira sessão", sort=summary.Semana.tolist(), axis=alt.Axis(labelAngle=0))
        bars = chart.mark_rule(color=PURPLE, strokeWidth=3).encode(
            x=x, y=alt.Y("Inferior:Q", title="Retorno em 7 dias", axis=alt.Axis(format=".0%"), scale=alt.Scale(zero=True)),
            y2="Superior:Q")
        points = chart.mark_circle(color=PURPLE, size=110).encode(x=x, y="Taxa:Q",
            tooltip=["Semana", alt.Tooltip("size:Q", title="Elegíveis"), alt.Tooltip("sum:Q", title="Retornos"),
                     alt.Tooltip("Taxa:Q", format=".1%"), alt.Tooltip("Inferior:Q", format=".1%"),
                     alt.Tooltip("Superior:Q", format=".1%")])
        st.altair_chart((bars + points).properties(height=240), width="stretch")
        for _, item in summary.iterrows():
            st.caption(f"{item.Semana}: {integer(item['sum'])}/{integer(item['size'])} = {percent(item.Taxa)} "
                       f"· IC 95% {percent(item.Inferior)} a {percent(item.Superior)}")
        st.caption("Ponto: taxa observada. Barra: intervalo de confiança de 95%. Amostras pequenas geram mais incerteza.")
    with right.container(border=True):
        st.markdown("**Mudou quem chegou ou o retorno de cada perfil?**")
        parts = [("Perfil de quem chegou", mix * 100), ("Retorno dentro dos perfis", within * 100)]
        if coverage < 1 - 1e-9:
            parts.append(("Diferença de cobertura", (total - mix - within) * 100))
        contributions = pd.DataFrame(parts, columns=["Componente", "Pontos percentuais"])
        chart = alt.Chart(contributions)
        bars = chart.mark_bar().encode(
            y=alt.Y("Componente:N", title=None, sort=None, axis=alt.Axis(labelLimit=180)),
            x=alt.X("Pontos percentuais:Q", title="Contribuição para a variação (p.p.)"),
            color=alt.condition(alt.datum["Pontos percentuais"] >= 0, alt.value(PURPLE), alt.value("#ba3859")),
            tooltip=["Componente", alt.Tooltip("Pontos percentuais:Q", format="+.2f")])
        zero = chart.mark_rule(color="#554665").encode(x=alt.datum(0))
        st.altair_chart((bars + zero).properties(height=240), width="stretch")
        st.caption(f"Perfis: modelo (GPT-4 ou demais) e idioma (português ou demais). "
                   f"Cobertura mínima nas duas semanas: {percent(coverage)}.")
        if coverage < 1 - 1e-9:
            st.caption("A diferença de cobertura reconcilia a variação total com os perfis comparáveis; não identifica a causa nos perfis excluídos.")
        st.write("**Perfil de quem chegou:** mudança na proporção de cada perfil. "
                 "**Dentro dos perfis:** mudança na taxa de retorno de grupos comparáveis.")
    dominant = "mudança do perfil de quem chegou" if abs(mix) > abs(within) else "variação do retorno dentro dos perfis"
    st.info(f"Nos perfis comparáveis, o componente de maior magnitude foi a {dominant}. "
            "Isso orienta onde investigar; não prova que uma alteração no assistente causou o movimento.")
    st.caption("Próxima decisão: conferir mudanças de produto e cobertura da coleta nessas semanas, "
               "acompanhar outras coortes e medir resolução da tarefa antes de agir sobre essa oscilação. "
               "Fonte: WildChat-1M · Brasil · recorte e regra de identidade selecionados. "
               "Critérios: 30 elegíveis por semana, 10 por perfil em cada semana e cobertura mínima de 80%.")


def findings(results):
    topics = [
        ("Primeira conversa", "Turnos", "4+",
         "Testar uma sugestão opcional de continuidade e medir também a resolução da tarefa.",
         "Mais turnos podem refletir interesse ou dificuldade. Não é uma meta de prolongar conversas."),
        ("Tarefas de código", "Tema", "Código",
         "Revisar a classificação dos temas e medir se as tarefas de código foram resolvidas antes de priorizar mudanças.",
         "O tema vem de palavras-chave. Compare também as regras de sessão em Usuários e coortes."),
        ("Escolha do modelo", "Modelo", "GPT-4",
         "Comparar modelos em um experimento com distribuição aleatória, acompanhando retenção, qualidade e custo.",
         "Quem escolhe cada modelo pode ter objetivos e experiência diferentes."),
    ]
    for column, (title, factor, group, decision, limitation) in zip(st.columns(3), topics):
        with column.container(border=True):
            st.markdown(f"**{title}**")
            match = results.loc[results.Fator.eq(factor) & results.Grupo.eq(group)] if not results.empty else results
            if match.empty:
                st.write("Comparação indisponível neste recorte.")
                st.caption("O grupo pode ser a referência, estar ausente ou não ter observações suficientes. Amplie os filtros para comparar.")
                continue
            row = match.iloc[0]
            effect, low, high = (row[name] for name in ["Efeito (p.p.)", "Limite inferior", "Limite superior"])
            number = lambda value: f"{value:+.1f}".replace(".", ",")
            st.markdown(f"**{number(effect)} pontos percentuais**")
            st.caption(f"{group} versus {row['Referência']} · {integer(row['n'])} identidades no grupo")
            st.write(f"Intervalo de confiança de 95%: **{number(low)} a {number(high)} p.p.**")
            if low <= 0 <= high:
                st.write("Não há direção clara: o intervalo admite aumento e redução do retorno.")
            else:
                direction = "maior" if effect > 0 else "menor"
                st.write(f"Neste recorte, o grupo apresentou {direction} retorno após o ajuste pelas características observadas.")
            st.markdown(f"**Próxima decisão:** {decision}")
            st.caption(limitation)
    st.caption("Fonte: WildChat-1M · Brasil · primeira conversa das identidades elegíveis no recorte selecionado. "
               "Estimativas ajustadas por mês e características observadas; associações, não efeitos causais. "
               "Um ponto percentual equivale a uma diferença de um retorno a cada 100 identidades.")


def overview_story(weekly):
    n, k = int(weekly.elegiveis.sum()), int(weekly.voltaram.sum())
    if n < MIN_N:
        st.info("Há menos de 30 identidades com sete dias completos neste recorte. Amplie os filtros para interpretar a retenção.")
        return
    low, high = wilson(k, n)
    st.subheader(f"Cerca de {round(100 * k / n)} em cada 100 identidades voltaram em até sete dias")
    st.write(f"**{integer(k)} retornos entre {integer(n)} identidades acompanhadas por sete dias completos.** "
             f"Retenção de {percent(k / n)}, com intervalo de confiança de 95% de {percent(low)} a {percent(high)}.")
    st.caption("Retorno significa iniciar outra sessão em até 168 horas da primeira. "
               "Identidade é uma aproximação por IP ou IP e navegador, conforme o filtro; não uma contagem exata de pessoas. "
               "O intervalo resume incerteza estatística, mas não elimina erros de identidade ou lacunas da coleta.")


def job_time(value):
    if not value:
        return "Ainda não executou"
    return datetime.fromisoformat(value).astimezone(ZONE).strftime("%d/%m/%Y às %H:%M")


def etl_page(job, loaded_at):
    heartbeat = job["heartbeat"]
    online = heartbeat and datetime.now(ZONE) - datetime.fromisoformat(heartbeat) < timedelta(minutes=3)
    status = [
        ("Agendamento", "Ativo" if job["enabled"] else "Desativado"),
        ("Agendador", "Online" if online else "Sem sinal recente"),
        ("Última carga", job_time(loaded_at)),
    ]
    if job["started"]:
        status.append(("Último início", job_time(job["started"])))
        status.append(("Resultado", MESSAGES.get(job["status"], "Sem execução")))
    if job["finished"]:
        status.append(("Último término", job_time(job["finished"])))
    cells = "".join(f"<div><span>{label}</span><strong>{escape(value)}</strong></div>"
                    for label, value in status)
    st.markdown(f'<div class="etl-status">{cells}</div>', unsafe_allow_html=True)
    allowed = os.environ.get("ETL_LOCAL_ADMIN") == "1"
    if password := os.environ.get("ETL_ADMIN_PASSWORD"):
        supplied = st.text_input("Senha de administração", type="password")
        allowed = compare_digest(password.encode(), supplied.encode())
    if not allowed:
        st.caption("Somente consulta")
    st.markdown("**Configuração**")
    enabled = st.toggle("Ativar agendamento", value=bool(job["enabled"]), disabled=not allowed)
    frequencies = {"Diário": "daily", "Semanal": "weekly"}
    frequency_col, hour_col, day_col = st.columns(3)
    label = frequency_col.selectbox("Frequência", list(frequencies),
                                    index=int(job["frequency"] == "weekly"), disabled=not allowed)
    hour = hour_col.time_input("Horário de Brasília", value=datetime.strptime(job["hour"], "%H:%M").time(),
                               step=60, disabled=not allowed)
    day = DAYS[job["weekday"]]
    if label == "Semanal":
        day = day_col.selectbox("Dia da semana", DAYS, index=job["weekday"], disabled=not allowed)
    if allowed and st.button("Salvar agendamento", type="primary"):
        save(enabled, frequencies[label], hour.strftime("%H:%M"), DAYS.index(day))
        st.session_state["etl_saved"] = True
        st.rerun()
    if st.session_state.pop("etl_saved", False):
        st.success("Agendamento salvo.")


def etl_sidebar(job, loaded_at):
    st.sidebar.divider()
    st.sidebar.button(
        "⚙ Configurar ETL", type="primary", width="stretch",
        on_click=lambda: st.session_state.update(navigation=None),
    )
    st.sidebar.markdown(
        f'<div class="etl-sidebar-load">Última carga da base · {escape(job_time(loaded_at))}</div>',
        unsafe_allow_html=True,
    )
    if job["started"]:
        st.sidebar.caption(f"Última execução agendada · {job_time(job['started'])}")


st.sidebar.markdown('<div class="brand"><span>◈</span>Painel</div>', unsafe_allow_html=True)
pages = ["Visão geral", "Fatores de retenção", "Exploração de dados", "Usuários e coortes",
         "Qualidade e incidentes", "Documentação"]
page = st.sidebar.radio("Navegação", pages, label_visibility="collapsed", key="navigation")
job = settings()
loaded_at = None
if DB.exists():
    version = DB.stat().st_mtime_ns
    loaded = query("SELECT valor FROM auditoria WHERE item = ?", ("carga concluída UTC",), version)
    if not loaded.empty:
        loaded_at = loaded.iat[0, 0]
if page is None:
    etl_sidebar(job, loaded_at)
    with st.container(key="etl-content"):
        etl_page(job, loaded_at)
        st.markdown("**Auditoria da carga**")
        if DB.exists():
            st.dataframe(query("SELECT item, valor FROM auditoria", (), version), hide_index=True, height=260)
        else:
            st.caption("Disponível após a primeira carga.")
    st.stop()

if not DB.exists():
    etl_sidebar(job, loaded_at)
    st.error("Execute python run.py para preparar a base analítica.")
    st.stop()

schema = query("PRAGMA table_info(coortes)", (), version)
if "dia_retorno" not in schema["name"].tolist():
    st.info("A base anterior precisa ser atualizada para calcular a matriz de coortes. Execute python run.py --rebuild.")
    st.stop()

st.sidebar.divider()
st.sidebar.markdown("**Filtros globais**")
rules = {"IP com hash": "ip", "IP + navegador": "ip_ua", "IP · intervalo de 60 min": "ip_60"}
options = query("SELECT DISTINCT semana FROM coortes ORDER BY 1", (), version)["semana"].tolist()

if st.sidebar.button("Limpar filtros", key="reset"):
    for key in ("period", "model", "language", "state", "identity"):
        st.session_state.pop(key, None)
    st.session_state.pop("filters", None)

with st.sidebar.form("global_filters"):
    if len(options) > 1:
        period = st.select_slider("Período · semana inicial", options=options,
                                  value=(options[0], options[-1]), key="period")
    else:
        period = (options[0], options[0])
    dimensions = {}
    for col, label, key in [("modelo", "Modelo", "model"), ("idioma", "Idioma", "language"),
                            ("estado", "Estado (BR)", "state")]:
        values = query(f"SELECT DISTINCT {col} FROM volume_semanal ORDER BY 1", (), version)[col].tolist()
        dimensions[col] = st.selectbox(label, ["Todos", *values], key=key)
    identity = st.selectbox("Identidade e sessão", list(rules), key="identity")
    if st.form_submit_button("Aplicar filtros", type="primary", width="stretch"):
        st.session_state["filters"] = (period, dimensions, identity)

etl_sidebar(job, loaded_at)
(start, end), selected, identity = st.session_state.get(
    "filters", ((options[0], options[-1]), {}, next(iter(rules)))
)
where = "semana BETWEEN ? AND ?"
params = [start, end]
for col, value in selected.items():
    if value != "Todos":
        where += f" AND {col} = ?"
        params.append(value)

rows = query(f"SELECT * FROM coortes WHERE regra = ? AND {where}",
             (rules[identity], *params), version)
volume = query(f"SELECT * FROM volume_semanal WHERE {where}", tuple(params), version)
weekly = rows.groupby("semana", as_index=False).agg(
    novos=("elegivel", "size"), elegiveis=("elegivel", "sum"), voltaram=("voltou", "sum")
)
weekly["taxa"] = weekly["voltaram"].div(weekly["elegiveis"].where(weekly["elegiveis"].gt(0)))
eligible = rows.loc[rows.elegivel.eq(1)].drop(columns=["dia_retorno", "estado", "regra", "elegivel"])

main, source = st.columns([3, 1], vertical_alignment="center")
with main:
    st.title("Retenção do Assistente de IA")
    st.markdown("O que está associado a voltar ao assistente em até 7 dias?")
with source:
    st.markdown("**WildChat-1M · Brasil**")
    observed = query("SELECT valor FROM auditoria WHERE item = ?", ("fim observado UTC",), version)
    if not observed.empty:
        st.caption(f"Dados observados até {pd.Timestamp(observed.iat[0, 0]):%d/%m/%Y}")
st.caption(f"Coortes de {pd.Timestamp(start):%d/%m/%Y} a {pd.Timestamp(end):%d/%m/%Y} · {identity}")

if page == "Visão geral":
    overview_story(weekly)
    cards(weekly, volume)
    results = estimate(eligible)
    st.subheader("Três perguntas para orientar o próximo investimento")
    findings(results)
    left, right = st.columns([1.15, 1])
    with left.container(border=True, key="trend"):
        st.subheader("Evolução da retenção (7 dias)")
        trend(weekly)
    with right.container(border=True, key="cohort"):
        st.subheader("Retenção por coorte")
        cohort_heatmap(rows)
    with st.expander("Compare os demais fatores associados ao retorno"):
        forest(results, limit=6)
        st.caption("Na página Fatores de retenção, consulte todas as comparações e a investigação da mudança semanal. "
                   "As barras mostram a incerteza: quando cruzam zero, a direção da associação não é clara.")
elif page == "Fatores de retenção":
    results = estimate(eligible)
    st.subheader("Quais experiências estão associadas a voltar?")
    st.write("Compare a diferença de retorno entre cada grupo e sua referência, após o ajuste pelas características observadas.")
    st.caption("Fonte: WildChat-1M · Brasil · primeira conversa das identidades com sete dias completos no recorte selecionado.")
    with st.container(border=True):
        st.markdown("**Como ler o gráfico**")
        st.write("O ponto mostra a diferença estimada; a barra mostra o intervalo de confiança de 95%. "
                 "À direita de zero: maior retorno. À esquerda: menor retorno. "
                 "Se a barra cruza zero, não há uma direção clara para a associação.")
        st.caption("Exemplo de leitura: +5 pontos percentuais significa uma diferença estimada de 5 retornos a cada 100 identidades, não um ganho garantido.")
    with st.container(border=True):
        st.subheader("Comparações ajustadas · retorno em 7 dias")
        forest(results)
        st.caption("O ajuste considera mês, modelo, idioma, tema, horário, turnos, extensão e possível recusa da resposta, quando há variação suficiente. "
                   "Intenção e qualidade percebida não são medidas. As associações não demonstram causalidade; explorar muitos fatores aumenta a chance de destaques ao acaso.")
        if not results.empty:
            with st.expander("Detalhes das estimativas e tamanho dos grupos"):
                st.dataframe(results.round(2), hide_index=True)
    weekly_story(eligible)
elif page == "Exploração de dados":
    st.subheader("Distribuição de conversas")
    dims = {"Semana": "semana", "Modelo": "modelo", "Idioma": "idioma", "Estado": "estado",
            "Tema · histórico completo": "tema", "Turnos · histórico completo": "tamanho"}
    dim = dims[st.selectbox("Dimensão", list(dims))]
    if dim in volume:
        distribution = volume.groupby(dim, as_index=False)["conversas"].sum().rename(columns={dim: "grupo"})
    else:
        distribution = query("SELECT grupo, conversas FROM uso WHERE dim = ?", (dim,), version)
        st.caption("Esta distribuição abrange todo o histórico do Brasil.")
    distribution = distribution.query("conversas >= 30").sort_values("conversas", ascending=False)
    if dim == "semana":
        st.line_chart(distribution.sort_values("grupo"), x="grupo", y="conversas", color=PURPLE)
    else:
        st.altair_chart(alt.Chart(distribution.head(15)).mark_bar(color=PURPLE).encode(
            x=alt.X("conversas:Q", title="Conversas"), y=alt.Y("grupo:N", sort="-x", title=None),
            tooltip=["grupo", "conversas"]
        ), width="stretch")
elif page == "Usuários e coortes":
    with st.container(border=True):
        st.subheader("Retorno acumulado por coorte")
        cohort_heatmap(rows)
    st.dataframe(weekly.assign(taxa=weekly.apply(lambda item: rate(item.voltaram, item.elegiveis), axis=1))
                 if not weekly.empty else weekly, hide_index=True)
    st.subheader("Sensibilidade à definição de usuário e sessão")
    sensitivity = query(f"""SELECT regra, count(*) AS elegiveis, sum(voltou) AS voltaram
                             FROM coortes WHERE elegivel = 1 AND {where} GROUP BY regra""",
                        tuple(params), version)
    if not sensitivity.empty:
        sensitivity["taxa"] = sensitivity.apply(lambda item: rate(item.voltaram, item.elegiveis), axis=1)
        sensitivity["regra"] = sensitivity["regra"].map({v: k for k, v in rules.items()})
    st.dataframe(sensitivity, hide_index=True)
elif page == "Qualidade e incidentes":
    st.subheader("A retenção caiu ou mudou a forma de contar?")
    st.caption("Caso do desafio · novembro de 2023 · Fonte: endpoint e relatório fornecidos no PDF, páginas 5 e 6. "
               "Os valores abaixo são do caso de investigação, não da base pública carregada. Os filtros globais não se aplicam a este caso.")
    st.info("O painel marcou uma queda, mas o relatório não. Há uma divergência na definição de usuário; "
            "o impacto exato precisa ser reconciliado antes de atribuir a queda ao produto.")

    incident = pd.DataFrame([
        ("06/11", "Painel", 1210, 375), ("13/11", "Painel", 1188, 368),
        ("20/11", "Painel", 2034, 366), ("06/11", "Relatório", 1150, 345),
        ("13/11", "Relatório", 1131, 351), ("20/11", "Relatório", 1172, 352),
    ], columns=["Semana", "Fonte", "Novos usuários", "Retornos em 7 dias"])
    incident["Taxa"] = incident["Retornos em 7 dias"] / incident["Novos usuários"]
    left, middle, right = st.columns(3)
    left.metric("Painel · 20/11", "18,0%", help="366 retornos ÷ 2.034 novos usuários, pela regra do painel legado.")
    middle.metric("Relatório · 20/11", "30,0%", help="352 retornos ÷ 1.172 novos usuários, pela regra do relatório.")
    right.metric("Diferença entre fontes", "12,0 p.p.", help="Relatório menos painel; não representa um efeito causal.")
    colors = alt.Scale(domain=["Painel", "Relatório"], range=[PURPLE, "#168477"])
    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown("**1. Apenas o painel registra a queda**")
        st.altair_chart(alt.Chart(incident).mark_line(point=True).encode(
            x=alt.X("Semana:O", title="Semana de chegada · 2023", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Taxa:Q", title="Retorno em até 7 dias", axis=alt.Axis(format=".0%"),
                    scale=alt.Scale(domain=[0, .4])),
            color=alt.Color("Fonte:N", scale=colors, title=None),
            tooltip=["Semana", "Fonte", "Novos usuários", "Retornos em 7 dias",
                     alt.Tooltip("Taxa:Q", format=".1%")],
        ).properties(height=240), width="stretch")
        st.caption("Taxa = retornos em até 7 dias ÷ novos usuários de cada fonte. "
                   "A comparação expõe regras diferentes de contagem, não estima o efeito de uma mudança no produto.")
    with right.container(border=True):
        st.markdown("**2. O aumento está na contagem de novos usuários**")
        counts = incident.loc[incident.Fonte.eq("Painel")].melt(
            id_vars=["Semana"], value_vars=["Novos usuários", "Retornos em 7 dias"],
            var_name="Indicador", value_name="Quantidade")
        st.altair_chart(alt.Chart(counts).mark_bar().encode(
            x=alt.X("Semana:O", title="Semana de chegada · 2023", axis=alt.Axis(labelAngle=0)),
            xOffset="Indicador:N", y=alt.Y("Quantidade:Q", title="Contagem no painel"),
            color=alt.Color("Indicador:N", scale=alt.Scale(
                domain=["Novos usuários", "Retornos em 7 dias"], range=[PURPLE, "#168477"]), title=None),
            tooltip=["Semana", "Indicador", "Quantidade"],
        ).properties(height=240), width="stretch")
        st.caption("De 13/11 para 20/11: +846 novos usuários contados e −2 retornos. "
                   "O aumento do denominador explica a queda aritmética; sua origem ainda requer reconciliação.")

    st.markdown("**3. Por que as duas fontes podem discordar?**")
    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown("**Painel: IP + navegador**")
        st.write("Uma troca de navegador pode criar uma segunda identidade: o retorno passa a ser contado como uma nova pessoa.")
    with right.container(border=True):
        st.markdown("**Relatório: somente IP**")
        st.write("A troca de navegador preserva a identidade. Ainda assim, IP é uma aproximação: pessoas podem compartilhar uma rede ou mudar de IP.")

    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown("**O que sabemos**")
        st.markdown("- O código da carga usa uma identidade diferente da usada no relatório.\n"
                    "- Um teste automatizado com dados sintéticos reproduz a perda de retorno após a troca de navegador.\n"
                    "- O endpoint respondeu com sucesso; isso não garante que a métrica esteja correta.")
    with right.container(border=True):
        st.markdown("**O que falta confirmar**")
        st.markdown("- Medir as duas regras sobre o mesmo snapshot original.\n"
                    "- Conciliar país, sessões, duplicatas e janela de observação.\n"
                    "- Reprocessar e validar o histórico antes de publicar uma taxa corrigida.")
    st.warning("Decisão para o cliente: não mudar a estratégia do produto com base nesta queda isolada. "
               "Primeiro, alinhar a definição de usuário e reconciliar as contagens.")
    st.caption("Prevenção proposta: contrato único da métrica, testes de regressão e comparação periódica "
               "entre o bruto e o painel. O teste existe no projeto; a reconciliação operacional do caso depende do snapshot original.")
    with st.expander("Detalhes técnicos · diagnóstico, SQL, correção e teste", expanded=False):
        st.markdown((ROOT / "INCIDENTE.md").read_text(encoding="utf-8"))
else:
    for name, filename in [("Resultados", "RESULTADOS.md"), ("Decisões", "DECISOES.md")]:
        with st.expander(name, expanded=name == "Resultados"):
            st.markdown((ROOT / filename).read_text(encoding="utf-8"))
