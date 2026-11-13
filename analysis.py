import math
from contextlib import closing
import sqlite3

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from etl import DB

MIN_N = 30
WEEKLY_SQL = """
SELECT semana, count(*) AS novos, sum(elegivel) AS elegiveis,
       coalesce(sum(voltou), 0) AS voltaram,
       1.0 * sum(voltou) / nullif(sum(elegivel), 0) AS taxa
FROM coortes WHERE regra = ? AND semana BETWEEN ? AND ?
GROUP BY semana ORDER BY semana
"""


def read(query, params=()):
    with closing(sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True)) as db:
        return pd.read_sql_query(query, db, params=params)


def wilson(k, n):
    p = k / n
    z = 1.96
    denominator = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denominator
    radius = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator
    return center - radius, center + radius


def effects(rows):
    data = rows.copy()
    if len(data) < 100 or data["voltou"].value_counts().reindex([0, 1], fill_value=0).min() < 20:
        return pd.DataFrame()
    data["mes"] = data["semana"].str[:7]
    data["tamanho"] = pd.cut(data["turnos"], [0, 1, 3, float("inf")],
                            labels=["1", "2–3", "4+"], include_lowest=True).astype(str)
    data["resposta_longa"] = np.where(data["resposta_chars"] >= 500, "500+ caracteres", "<500 caracteres")
    labels = {"modelo": "Modelo", "idioma": "Idioma", "tema": "Tema", "faixa_hora": "Horário",
              "tamanho": "Turnos", "resposta_longa": "Extensão", "resposta": "Resposta",
              "mes": "Mês da coorte"}
    terms = {}
    for col in labels:
        counts = data[col].value_counts()
        data[col] = data[col].where(data[col].isin(counts[counts >= MIN_N].index), "Demais / raros")
        counts = data[col].value_counts()
        if len(counts) > 1:
            terms[col] = counts.index[0]
    if not terms:
        return pd.DataFrame()
    formula = "voltou ~ " + " + ".join(f"C({col}, Treatment({ref!r}))" for col, ref in terms.items())
    fit = smf.ols(formula, data=data).fit(cov_type="HC3")
    if fit.model.rank < len(fit.params) or fit.df_resid < 30:
        return pd.DataFrame()
    intervals = fit.conf_int()
    results = []
    for col, reference in terms.items():
        if col == "mes":
            continue
        for level, n in data[col].value_counts().items():
            if level == reference or n < MIN_N:
                continue
            term = f"C({col}, Treatment({reference!r}))[T.{level}]"
            low, high = intervals.loc[term] * 100
            results.append({"Fator": labels[col], "Grupo": level, "Referência": reference,
                            "n": n, "Efeito (p.p.)": 100 * fit.params[term],
                            "Limite inferior": low, "Limite superior": high})
    return pd.DataFrame(results).sort_values("Efeito (p.p.)", key=abs, ascending=False) if results else pd.DataFrame()


def weekly_change(rows):
    weekly = rows.groupby("semana")["voltou"].agg(["size", "mean"])
    candidates = weekly.assign(
        delta=weekly["mean"].diff(), anterior=weekly["size"].shift(),
        gap=pd.Series(pd.to_datetime(weekly.index), index=weekly.index).diff().dt.days
    ).query("size >= 30 and anterior >= 30 and gap == 7")
    for current in candidates["delta"].abs().sort_values(ascending=False).index:
        previous = (pd.Timestamp(current) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        frame = rows.loc[rows["semana"].isin([previous, current])].copy()
        frame["perfil"] = np.where(frame["modelo"].eq("GPT-4"), "GPT-4", "Demais") + np.where(
            frame["idioma"].eq("Portuguese"), " / português", " / demais idiomas"
        )
        by_profile = frame.groupby(["perfil", "semana"])["voltou"].agg(["size", "mean"]).unstack()
        by_profile = by_profile.loc[by_profile["size"].ge(10).all(axis=1)]
        if by_profile.empty or (by_profile["size"].sum() / frame.groupby("semana").size()).min() < .8:
            continue
        weights = by_profile["size"] / by_profile["size"].sum()
        rates = by_profile["mean"]
        mix = ((weights[current] - weights[previous]) * rates.mean(axis=1)).sum()
        within = ((rates[current] - rates[previous]) * weights.mean(axis=1)).sum()
        covered = (by_profile["size"].sum() / frame.groupby("semana").size()).min()
        return previous, current, candidates.loc[current, "delta"], mix, within, covered
    return None
