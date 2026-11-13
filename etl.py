import hashlib
import json
import math
import os
import re
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pyarrow.dataset as ds
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DB = DATA / "retencao.sqlite"
REPO = "allenai/WildChat-1M"
REVISION = "7d6490e462285cf85d91eabea0f9a954fbddcd1f"
WINDOW = pd.Timedelta(days=7)
TOPICS = {
    "Código": r"\b(python|javascript|sql|código|programação|code|api)\b",
    "Escrita": r"\b(escrev\w*|redação|reescrev\w*|write|rewrite|email|e-mail|poema)\b",
    "Estudo": r"\b(expliqu\w*|explique|explain|exercício|estudar|resolva|homework)\b",
    "Tradução": r"\b(traduz\w*|traduç\w*|translate|translation)\b",
}
REFUSAL = re.compile(
    r"^(desculp[ae]|sinto muito|não posso|não consigo|i'm sorry|i am sorry|"
    r"i cannot|i can't|as an ai|como (um )?modelo)", re.I
)
FIELDS = ["country", "state", "hashed_ip", "header", "conversation", "timestamp", "model", "language", "turn"]


def digest(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def source_files(audit=None, revision=None):
    local = sorted((DATA / "raw").rglob("*.parquet"))
    if local and revision is None:
        if audit is not None:
            audit["fonte"] = "Parquet local"
        yield from local
        return
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
    )))
    if token := os.getenv("HF_TOKEN"):
        session.headers["Authorization"] = f"Bearer {token}"
    revision = revision or os.getenv("WILDCHAT_REVISION", REVISION)
    base = "https://huggingface.co"
    response = session.get(f"{base}/api/datasets/{REPO}/revision/{revision}", timeout=30)
    response.raise_for_status()
    meta = response.json()
    if audit is not None:
        audit["revisão WildChat-1M"] = meta["sha"]
    paths = sorted(item["rfilename"] for item in meta["siblings"]
                   if item["rfilename"].endswith(".parquet"))
    if not paths:
        raise ValueError("A revisão selecionada não contém Parquet.")
    print(f"WildChat-1M revisão {meta['sha']}", flush=True)
    cache = DATA / "downloads" / meta["sha"]
    cache.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(paths, 1):
        print(f"Parquet {i}/{len(paths)}", flush=True)
        file = cache / Path(name).name
        if not file.exists():
            url = f"{base}/datasets/{REPO}/resolve/{meta['sha']}/{name}"
            with TemporaryDirectory(dir=cache) as temp:
                partial = Path(temp) / "part.parquet"
                for attempt in range(3):
                    try:
                        with session.get(url, stream=True, timeout=(20, 45)) as download:
                            download.raise_for_status()
                            with partial.open("wb") as out:
                                for chunk in download.iter_content(1024 * 1024):
                                    out.write(chunk)
                        os.replace(partial, file)
                        break
                    except requests.exceptions.RequestException:
                        if attempt == 2:
                            raise
                        print(f"Tentando baixar novamente o Parquet {i}", flush=True)
        yield file


def normalize(row, audit):
    audit["linhas Brasil"] += 1
    ip = str(row.get("hashed_ip") or "").strip()
    messages = [m for m in (row["conversation"] or []) if m]
    dated = [t for m in messages if pd.notna(
        t := pd.to_datetime(m.get("timestamp"), utc=True, errors="coerce")
    )]
    users = [m for m in messages if m.get("role") == "user"]
    top = pd.to_datetime(row["timestamp"], utc=True, errors="coerce")
    timestamps = dated + ([top] if pd.notna(top) else [])
    end = max(timestamps, default=pd.NaT)
    if pd.notna(end):
        audit["fim observado UTC"] = max(audit.get("fim observado UTC", end), end)
    if not ip or not users or pd.isna(end):
        audit["linhas descartadas por identidade ou tempo"] += 1
        return None
    first = users[0]
    start = pd.to_datetime(first.get("timestamp"), utc=True, errors="coerce")
    if pd.isna(start):
        audit["início aproximado por primeiro timestamp disponível"] += 1
        start = min(timestamps)
    if pd.notna(top) and top < end:
        audit["timestamp de linha anterior ao último timestamp dos turnos"] += 1
    prompt = str(first.get("content") or "")
    if not prompt.strip():
        audit["primeiro prompt vazio"] += 1
    answer = next((str(m.get("content") or "") for m in messages[messages.index(first) + 1:]
                   if m.get("role") == "assistant"), "")
    matches = [topic for topic, pattern in TOPICS.items() if re.search(pattern, prompt, re.I)]
    topic = matches[0] if len(matches) == 1 else "Outros / misto"
    ua = (row["header"] or {}).get("user-agent") or ""
    if not ua:
        audit["linhas sem user-agent"] += 1
    model = str(row.get("model") or "")
    family = "GPT-3.5" if model.startswith("gpt-3.5") else (
        "GPT-4" if model.startswith("gpt-4") else "Outros"
    )
    # Hash da linha sem depender da unicidade do hash de conteúdo ou de um único turno.
    key = digest(ip, ua, start.isoformat(), end.isoformat(), model,
                 [(m.get("turn_identifier"), m.get("role"), m.get("content")) for m in messages])
    return {
        "chave": key, "ip": digest(ip), "ip_ua": digest(ip, ua),
        "inicio": start, "fim": end, "modelo": family,
        "idioma": row["language"] or "Desconhecido", "tema": topic,
        "estado": row.get("state") or "Desconhecido",
        "turnos": int(row["turn"] or len(users)),
        "resposta_chars": len(answer), "resposta": (
            "Sem resposta observada" if not answer else
            "Possível recusa" if REFUSAL.search(answer.strip()) else "Resposta registrada"
        ),
    }


def cohort(conversations, identity, cutoff, gap_minutes=30):
    ordered = conversations.sort_values([identity, "inicio", "chave"]).copy()
    previous_end = ordered.groupby(identity)["fim"].cummax().groupby(ordered[identity]).shift()
    new_session = previous_end.isna() | (ordered["inicio"] - previous_end > pd.Timedelta(minutes=gap_minutes))
    starts = ordered.loc[new_session].copy()
    starts["proxima"] = starts.groupby(identity)["inicio"].shift(-1)
    first = starts.drop_duplicates(identity).copy()
    local = first["inicio"].dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None)
    first["semana"] = local.dt.to_period("W-SUN").dt.start_time.dt.strftime("%Y-%m-%d")
    first["faixa_hora"] = pd.cut(local.dt.hour, [-1, 5, 11, 17, 23],
                                 labels=["Madrugada", "Manhã", "Tarde", "Noite"]).astype(str)
    first["elegivel"] = (first["inicio"] + WINDOW <= cutoff).astype(int)
    first["voltou"] = (first["proxima"] <= first["inicio"] + WINDOW).astype(int)
    days = (first["proxima"] - first["inicio"]) / pd.Timedelta(days=1)
    first["dia_retorno"] = days.where(days.gt(0) & days.le(7)).apply(
        lambda value: math.ceil(value) if pd.notna(value) else None
    )
    first.loc[first["elegivel"].eq(0), "voltou"] = None
    first.loc[first["elegivel"].eq(0), "dia_retorno"] = None
    if "estado" not in first:
        first["estado"] = "Desconhecido"
    return first[["semana", "faixa_hora", "elegivel", "voltou", "modelo", "idioma",
                  "tema", "turnos", "resposta_chars", "resposta", "estado", "dia_retorno"]]


def build(revision=None):
    DATA.mkdir(exist_ok=True)
    audit = Counter()
    rows = []
    downloaded = []
    for file in source_files(audit, revision):
        audit["arquivos processados"] += 1
        if file.is_relative_to(DATA / "downloads"):
            downloaded.append(file)
        batches = ds.dataset(file, format="parquet").to_batches(
            columns=FIELDS, filter=ds.field("country") == "Brazil", batch_size=512
        )
        for batch in batches:
            for row in batch.to_pylist():
                if item := normalize(row, audit):
                    rows.append(item)
    if not rows:
        raise ValueError(f"Nenhuma conversa brasileira válida encontrada. Auditoria: {dict(audit)}")
    raw = pd.DataFrame(rows)
    conversations = raw.drop_duplicates("chave")
    audit["duplicatas exatas removidas"] = len(raw) - len(conversations)
    audit["conversas válidas"] = len(conversations)
    audit["início observado UTC"] = conversations["inicio"].min()
    cutoff = audit["fim observado UTC"]
    with TemporaryDirectory(dir=DATA) as directory:
        staged = Path(directory) / DB.name
        with closing(sqlite3.connect(staged)) as db, db:
            for label, key, gap in [("ip", "ip", 30), ("ip_ua", "ip_ua", 30), ("ip_60", "ip", 60)]:
                cohort(conversations, key, cutoff, gap).assign(regra=label).to_sql(
                    "coortes", db, if_exists="append", index=False
                )
            db.execute("CREATE INDEX idx_coortes ON coortes(regra, semana, elegivel)")
            pd.DataFrame([(key, str(value)) for key, value in audit.items()],
                         columns=["item", "valor"]).to_sql("auditoria", db, index=False)
            volume = conversations.copy()
            volume["semana"] = (volume["inicio"].dt.tz_convert("America/Sao_Paulo")
                                .dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time
                                .dt.strftime("%Y-%m-%d"))
            volume["tamanho"] = pd.cut(volume["turnos"], [0, 1, 3, 10, float("inf")],
                                       labels=["1", "2–3", "4–10", "11+"], include_lowest=True)
            volume.groupby(["semana", "modelo", "idioma", "estado"], observed=True)["turnos"].agg(
                conversas="size", soma_turnos="sum"
            ).reset_index().to_sql("volume_semanal", db, index=False)
            for dimension in ("semana", "modelo", "idioma", "tema", "tamanho"):
                volume.groupby(dimension, observed=True).size().rename("conversas").reset_index().rename(
                    columns={dimension: "grupo"}
                ).assign(dim=dimension).to_sql("uso", db, if_exists="append", index=False)
        os.replace(staged, DB)
    for file in downloaded:
        try:
            file.unlink(missing_ok=True)
        except OSError:
            print(f"Não foi possível limpar o Parquet temporário {file.name}.", flush=True)
    print(f"Base publicada: {DB}", flush=True)


if __name__ == "__main__":
    build()
