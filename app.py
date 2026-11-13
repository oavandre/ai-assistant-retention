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
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {background:#30204d;border-color:#6e5094}
[data-testid="stSidebar"] [role="slider"] + div {color:#e5c8ff}
[data-testid="stAppDeployButton"] {display:none}
[data-testid="stMainBlockContainer"] {padding:2rem clamp(1rem,3vw,2rem) 2rem; max-width:1650px}
[data-testid="stMainBlockContainer"] h1 {font-size:clamp(1.9rem,3.1vw,2.4rem);padding-bottom:.1rem}
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
.heat th,.heat td {padding:6px 3px;white-space:nowrap}
.heat th {background:#f3edf9}
.finding {border-left:3px solid #b884f9;padding:0 0 0 .75rem;margin:.7rem 0;font-size:.9rem}
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
    st.markdown(f'<table class="heat"><thead><tr>{header}</tr></thead>'
                f'<tbody>{"".join(body)}</tbody></table>', unsafe_allow_html=True)
    st.caption("D0 é a sessão inicial. D1–D7 mostram o retorno acumulado em até sete coortes recentes com pelo menos 30 elegíveis. — indica base pequena.")


def forest(results, limit=None):
    if results.empty:
        st.info("Base insuficiente ou fatores redundantes para estimar diferenças neste recorte.")
        return
    frame = results.head(limit).copy() if limit else results.copy()
    frame["Comparação"] = frame["Fator"] + " · " + frame["Grupo"]
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
    st.caption("Diferenças em pontos percentuais com IC 95%. A referência de cada comparação aparece ao passar o mouse.")


def findings(results):
    if results.empty:
        st.caption("Amplie o recorte para estimar associações.")
        return
    for _, row in results.head(3).iterrows():
        effect = f"{row['Efeito (p.p.)']:+.1f}".replace(".", ",")
        st.markdown(f'<div class="finding"><b>{escape(row["Grupo"])}</b> vs. '
                    f'{escape(row["Referência"])} · <b>{effect} p.p.</b></div>', unsafe_allow_html=True)
    st.caption("Associações ajustadas para o recorte selecionado.")


def job_time(value):
    if not value:
        return "Ainda não executou"
    return datetime.fromisoformat(value).astimezone(ZONE).strftime("%d/%m/%Y às %H:%M")


def etl_page(job):
    st.title("Agendamento do ETL")
    st.write("O job verifica o WildChat-1M no horário escolhido. Uma nova revisão dispara a carga do recorte brasileiro.")
    heartbeat = job["heartbeat"]
    online = heartbeat and datetime.now(ZONE) - datetime.fromisoformat(heartbeat) < timedelta(minutes=3)
    a, b, c = st.columns(3)
    a.metric("Agendamento", "Ativo" if job["enabled"] else "Desativado")
    b.metric("Último início", job_time(job["started"]))
    c.metric("Resultado", MESSAGES.get(job["status"], "Sem execução"))
    st.caption(f"Agendador: {'respondendo' if online else 'sem sinal recente'} · Horário de Brasília")
    if job["finished"]:
        st.caption(f"Último término: {job_time(job['finished'])}")
    st.button("Atualizar status")
    allowed = os.environ.get("ETL_LOCAL_ADMIN") == "1"
    if password := os.environ.get("ETL_ADMIN_PASSWORD"):
        supplied = st.text_input("Senha de administração", type="password")
        allowed = compare_digest(password.encode(), supplied.encode())
    if not allowed:
        st.info("A configuração do agendamento está disponível para o administrador.")
    enabled = st.toggle("Ativar agendamento", value=bool(job["enabled"]), disabled=not allowed)
    frequencies = {"Diário": "daily", "Semanal": "weekly"}
    label = st.radio("Frequência", list(frequencies), index=int(job["frequency"] == "weekly"),
                     horizontal=True, disabled=not allowed)
    hour = st.time_input("Horário", value=datetime.strptime(job["hour"], "%H:%M").time(),
                         step=60, disabled=not allowed)
    day = DAYS[job["weekday"]]
    if label == "Semanal":
        day = st.selectbox("Dia da semana", DAYS, index=job["weekday"], disabled=not allowed)
    if st.button("Salvar agendamento", type="primary", disabled=not allowed) and allowed:
        save(enabled, frequencies[label], hour.strftime("%H:%M"), DAYS.index(day))
        st.session_state["etl_saved"] = True
        st.rerun()
    if st.session_state.pop("etl_saved", False):
        st.success("Agendamento salvo.")


st.sidebar.markdown('<div class="brand"><span>◈</span>Painel</div>', unsafe_allow_html=True)
pages = ["Visão geral", "Fatores de retenção", "Exploração de dados", "Usuários e coortes",
         "Qualidade e incidentes", "Agendamento do ETL", "Documentação"]
page = st.sidebar.radio("Navegação", pages, label_visibility="collapsed")
job = settings()
if page == "Agendamento do ETL":
    etl_page(job)
    st.stop()

if not DB.exists():
    st.error("Execute python run.py para preparar a base analítica.")
    st.stop()

version = DB.stat().st_mtime_ns
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
    st.caption(f"Job ETL · {'Ativo' if job['enabled'] else 'Desativado'}")
    st.caption(f"Última execução · {job_time(job['started'])}")
st.caption(f"Coortes de {pd.Timestamp(start):%d/%m/%Y} a {pd.Timestamp(end):%d/%m/%Y} · {identity}")

if page == "Visão geral":
    cards(weekly, volume)
    left, right = st.columns([1.15, 1])
    with left.container(border=True, key="trend"):
        st.subheader("Evolução da retenção (7 dias)")
        trend(weekly)
    with right.container(border=True, key="cohort"):
        st.subheader("Retenção por coorte")
        cohort_heatmap(rows)
    results = estimate(eligible)
    left, right = st.columns([1.7, 1])
    with left.container(border=True, key="overview-effects"):
        st.subheader("Fatores associados ao retorno")
        forest(results, limit=6)
    with right:
        with st.container(border=True, key="findings"):
            st.subheader("Principais achados")
            findings(results)
        with st.container(border=True, key="recommendations"):
            st.subheader("Recomendações")
            st.markdown("- Testar uma sugestão de continuidade na primeira conversa.\n"
                        "- Medir resolução da tarefa e retenção no mesmo experimento.")
elif page == "Fatores de retenção":
    results = estimate(eligible)
    with st.container(border=True):
        st.subheader("Efeitos ajustados no retorno em 7 dias")
        forest(results)
        st.caption("O modelo ajusta por características observadas da primeira conversa e mês. Intenção e qualidade percebida podem confundir a associação.")
        if not results.empty:
            st.dataframe(results.round(2), hide_index=True)
    st.subheader("O que mudou de uma semana para outra?")
    if movement := weekly_change(eligible):
        previous, current, total, mix, within, coverage = movement
        st.write(f"De {previous} a {current}, a taxa variou **{total*100:+.2f} p.p.**")
        st.write(f"Nos perfis comparáveis (cobertura mínima de {coverage:.0%}), "
                 f"**{mix*100:+.2f} p.p.** vieram da composição e **{within*100:+.2f} p.p.** "
                 "da variação dentro dos perfis.")
    else:
        st.info("Sem duas semanas consecutivas com cobertura suficiente para decompor a variação.")
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
    st.subheader("Auditoria da carga")
    st.dataframe(query("SELECT item, valor FROM auditoria", (), version), hide_index=True)
    with st.expander("Investigação da semana de 20/11/2023", expanded=True):
        st.markdown((ROOT / "INCIDENTE.md").read_text(encoding="utf-8"))
else:
    for name, filename in [("Resultados", "RESULTADOS.md"), ("Decisões", "DECISOES.md")]:
        with st.expander(name, expanded=name == "Resultados"):
            st.markdown((ROOT / filename).read_text(encoding="utf-8"))
