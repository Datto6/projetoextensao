"""
Análise Exploratória de Dados — Bilhete Único Intermunicipal (BUI)
SETRAM / LIA² / UERJ

Campos:
    Nº Cartão            — Número do cartão com dígitos mascarados (não é identificador único)
    Cartão Hash          — Hash único do cartão; identifica o usuário de forma LGPD-compliant.
                           Presente em alguns arquivos; quando ausente, Nº Cartão é usado como
                           fallback com aviso explícito.
    Descrição da Aplicação — Tipo de benefício/aplicação (100, 115, 400, 450, 820…)
    Sindicato            — Sindicato ao qual a operadora é filiada
    Operadora            — Empresa de transporte (anonimizada para Vans)
    Linha                — Número e nome da linha
    Nº Carro             — Estação ou veículo onde ocorreu a transação
    Sentido              — 0=não informado, 1=ida, 2=volta
    Nº Validador         — Dispositivo de validação
    Data da Transação    — Data/hora da transação no validador
    Data do Processamento— Data/hora do processamento
    Vl Linha             — Tarifa cheia da linha
    Vl Trans             — Valor cobrado no cartão do usuário
    Vl Subsídio          — Valor subsidiado pelo estado
    Qtde Integrações     — Número de integrações na viagem
    Data da Ordem        — Data da ordem de subsídio
    Nº Ordem             — Sequencial da ordem de subsídio por modal

Arquitetura de leitura em chunks
─────────────────────────────────
O arquivo é lido em blocos de CHUNK_SIZE linhas. Cada chunk é transformado
(parse de datas, valores monetários, campos derivados) e então suas
contribuições são ACUMULADAS em estruturas de agregação leves:

    • Contadores e somas escalares  → acumulados diretamente
    • Distribuições (histogramas)   → numpy arrays de bins fixos, somados por chunk
    • Séries temporais (diário)     → dict {data: (count, soma)} acumulado
    • Top-N (operadora, linha…)     → Counter acumulado, top-N extraído no final
    • Anomalias (Isolation Forest)  → amostra aleatória estratificada de até
                                       SAMPLE_ANOMALIA linhas coletada durante
                                       a leitura; modelo treinado no final

O DataFrame completo NUNCA é materializado em memória.

Uso:
    python eda_bui.py --input arquivo.txt [--sep ";"] [--output relatorio/]
                      [--chunk 200000] [--sample-anomalia 500000]
"""

import argparse
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import IsolationForest

warnings.filterwarnings("ignore")

# ── Estilo global ─────────────────────────────────────────────────────────────
sns.set_theme(style="whitegrid", palette="muted", font_scale=1.05)
FIGSIZE_WIDE = (14, 5)
FIGSIZE_SQ   = (10, 7)

COLUNAS_PT = {
    "Nº Cartão":               "num_cartao",
    "Cartão Hash":             "cartao_hash",
    "Descrição da Aplicação":  "descricao_aplicacao",
    "Sindicato":               "sindicato",
    "Operadora":               "operadora",
    "Linha":                   "linha",
    "Nº Carro":                "num_carro",
    "Sentido":                 "sentido",
    "Nº Validador":            "num_validador",
    "Data da Transação":       "data_transacao",
    "Data do Processamento":   "data_processamento",
    "Vl Linha":                "vl_linha",
    "Vl Trans":                "vl_trans",
    "Vl Subsídio":             "vl_subsidio",
    "Qtde Integrações":        "qtde_integracoes",
    "Data da Ordem":           "data_ordem",
    "Nº Ordem":                "num_ordem",
}

SENTIDO_MAP  = {0: "Não informado", 1: "Ida", 2: "Volta"}
DIAS_MAP     = {"Monday":"Seg","Tuesday":"Ter","Wednesday":"Qua",
                "Thursday":"Qui","Friday":"Sex","Saturday":"Sáb","Sunday":"Dom"}
DIAS_ORDEM   = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]


# ════════════════════════════════════════════════════════════════════════════
# TRANSFORMAÇÃO DE UM CHUNK
# ════════════════════════════════════════════════════════════════════════════

def parse_brl(series: pd.Series) -> pd.Series:
    """Converte 'R$ 1.234,56' → 1234.56 (float)."""
    return (
        series.astype(str)
        .str.replace(r"R\$\s*", "", regex=True)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.strip()
        .replace("", np.nan)
        .astype(float)
    )


def transform_chunk(chunk: pd.DataFrame, usando_hash: bool) -> pd.DataFrame:
    """Aplica todas as transformações a um chunk bruto."""
    chunk = chunk.copy()
    chunk.columns = chunk.columns.str.strip()
    chunk.rename(columns=COLUNAS_PT, inplace=True)

    # Identificador de usuário
    if usando_hash and "cartao_hash" in chunk.columns:
        chunk["id_usuario"] = chunk["cartao_hash"]
    else:
        chunk["id_usuario"] = chunk.get("num_cartao", pd.Series(dtype=str))

    # Datas
    for col in ["data_transacao", "data_processamento", "data_ordem"]:
        if col in chunk.columns:
            chunk[col] = pd.to_datetime(chunk[col], dayfirst=True, errors="coerce")

    # Monetários
    for col in ["vl_linha", "vl_trans", "vl_subsidio"]:
        if col in chunk.columns:
            chunk[col] = parse_brl(chunk[col])

    # Numéricos
    for col in ["sentido", "qtde_integracoes", "num_carro", "num_validador", "num_ordem"]:
        if col in chunk.columns:
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce")

    # Campos derivados
    if "data_transacao" in chunk.columns:
        chunk["hora"]       = chunk["data_transacao"].dt.hour
        chunk["dia_semana"] = chunk["data_transacao"].dt.day_name().map(DIAS_MAP)
        chunk["data_dia"]   = chunk["data_transacao"].dt.date

    if "vl_linha" in chunk.columns and "vl_subsidio" in chunk.columns:
        chunk["pct_subsidio"] = (chunk["vl_subsidio"] / chunk["vl_linha"] * 100).round(2)

    if "sentido" in chunk.columns:
        chunk["sentido_label"] = chunk["sentido"].map(SENTIDO_MAP)

    if "descricao_aplicacao" in chunk.columns:
        chunk["tipo_aplicacao"] = chunk["descricao_aplicacao"].str.extract(r"^(\d+)")

    if "data_transacao" in chunk.columns and "data_processamento" in chunk.columns:
        chunk["latencia_h"] = (
            (chunk["data_processamento"] - chunk["data_transacao"])
            .dt.total_seconds() / 3600
        )

    if "qtde_integracoes" in chunk.columns:
        chunk["tem_integracao"] = (chunk["qtde_integracoes"] > 0).map(
            {True: "Com integração", False: "Sem integração"}
        )

    return chunk


# ════════════════════════════════════════════════════════════════════════════
# DETECÇÃO DE METADADOS (1ª passagem ultra-leve: só cabeçalho + 1 chunk)
# ════════════════════════════════════════════════════════════════════════════

def detectar_metadados(path: str, sep: str) -> dict:
    """Lê apenas o primeiro chunk para descobrir se Cartão Hash existe."""
    reader = pd.read_csv(path, sep=sep, encoding="utf-8-sig", dtype=str,
                         chunksize=1000)
    first  = next(reader)
    first.columns = first.columns.str.strip()
    first.rename(columns=COLUNAS_PT, inplace=True)

    usando_hash = (
        "cartao_hash" in first.columns
        and first["cartao_hash"].notna().any()
        and (first["cartao_hash"].str.strip() != "").any()
    )
    return {"usando_hash": usando_hash, "colunas": list(first.columns)}


# ════════════════════════════════════════════════════════════════════════════
# LEITURA EM CHUNKS + ACUMULAÇÃO DE AGREGADOS
# ════════════════════════════════════════════════════════════════════════════

# Bins para histogramas (definidos na 1ª passagem pelo primeiro chunk)
N_BINS = 50

def _make_acc() -> dict:
    """Cria o dicionário acumulador zerado."""
    return {
        # Escalares
        "n_linhas":          0,
        "usuarios":          set(),       # HyperLogLog seria melhor para bilhões; set é OK até ~50M
        "linhas_unicas":     set(),
        "operadoras":        set(),
        "sindicatos":        set(),
        "vl_linha_sum":      0.0,
        "vl_trans_sum":      0.0,
        "vl_subsidio_sum":   0.0,
        "pct_subsidio_sum":  0.0,
        "pct_subsidio_n":    0,
        "com_integracao":    0,
        "nulos":             Counter(),
        # Para describe() — Welford online variance
        "wf":                {},           # {col: {"n","mean","M2"}}
        # Distribuições (histogramas acumulados)
        "hist_bins":         {},           # {col: edges}
        "hist_counts":       {},           # {col: counts array}
        # Séries temporais
        "hora_cnt":          Counter(),
        "hora_sub_sum":      defaultdict(float),
        "hora_sub_n":        Counter(),
        "dia_semana_cnt":    Counter(),
        "diario":            defaultdict(lambda: {"cnt": 0, "sub": 0.0}),
        "latencia_vals":     [],           # amostra de até 100k para histograma
        # Top-N categorias
        "operadora_cnt":     Counter(),
        "linha_cnt":         Counter(),
        "sindicato_cnt":     Counter(),
        "operadora_sub":     defaultdict(float),
        "linha_agg":         defaultdict(lambda: {"cnt":0,"uid":set(),"vl":[],"vt":[],"vs":[],"ps":[]}),
        # Sentido / Integrações
        "sentido_cnt":       Counter(),
        "integracao_cnt":    Counter(),
        "integ_sub_sum":     defaultdict(float),
        "integ_sub_n":       Counter(),
        # Correlações (somas para correlação de Pearson online)
        "corr_n":            0,
        "corr_sum":          {},           # {col: sum}
        "corr_sum2":         {},           # {col: sum of squares}
        "corr_cross":        {},           # {(c1,c2): sum of products}
        # Scatter vl_linha vs vl_trans (amostra)
        "scatter_sample":    [],
        # Anomalias (reservoir sample)
        "anom_sample":       [],
        "anom_sample_seen":  0,
        # Datas extremas
        "dt_min":            None,
        "dt_max":            None,
    }


def _welford_update(wf: dict, col: str, values: pd.Series):
    """Atualiza variância incremental de Welford para compute de describe()."""
    vals = values.dropna().values
    if col not in wf:
        wf[col] = {"n": 0, "mean": 0.0, "M2": 0.0,
                   "min": np.inf, "max": -np.inf, "vals_sample": []}
    s = wf[col]
    for x in vals:
        s["n"]   += 1
        delta     = x - s["mean"]
        s["mean"] += delta / s["n"]
        s["M2"]  += delta * (x - s["mean"])
        if x < s["min"]: s["min"] = x
        if x > s["max"]: s["max"] = x
    # Guarda amostra aleatória pequena para percentis (máx 10k por col)
    if len(s["vals_sample"]) < 10_000:
        s["vals_sample"].extend(vals[:max(0, 10_000 - len(s["vals_sample"]))].tolist())


def _hist_update(acc: dict, col: str, values: pd.Series, n_bins: int = N_BINS):
    """Acumula histograma incremental de bins fixos."""
    vals = values.dropna().values
    if len(vals) == 0:
        return
    if col not in acc["hist_bins"]:
        # Define edges no primeiro chunk com algum dado
        vmin, vmax = np.nanmin(vals), np.nanmax(vals)
        if vmin == vmax:
            vmax = vmin + 1
        acc["hist_bins"][col]   = np.linspace(vmin, vmax, n_bins + 1)
        acc["hist_counts"][col] = np.zeros(n_bins, dtype=np.int64)
    counts, _ = np.histogram(vals, bins=acc["hist_bins"][col])
    acc["hist_counts"][col] += counts


def _reservoir_sample(reservoir: list, seen: int, new_rows: pd.DataFrame,
                      max_size: int) -> tuple[list, int]:
    """Reservoir sampling (Vitter's Algorithm R) para amostra de tamanho fixo."""
    for _, row in new_rows.iterrows():
        seen += 1
        if len(reservoir) < max_size:
            reservoir.append(row)
        else:
            j = np.random.randint(0, seen)
            if j < max_size:
                reservoir[j] = row
    return reservoir, seen


CORR_COLS = ["vl_linha", "vl_trans", "vl_subsidio", "pct_subsidio",
             "qtde_integracoes", "hora", "sentido"]


def _corr_update(acc: dict, chunk: pd.DataFrame):
    """Acumula somas para correlação de Pearson online."""
    cols = [c for c in CORR_COLS if c in chunk.columns]
    sub  = chunk[cols].dropna()
    if sub.empty:
        return
    n = len(sub)
    acc["corr_n"] += n
    for c in cols:
        acc["corr_sum"][c]  = acc["corr_sum"].get(c,  0.0) + sub[c].sum()
        acc["corr_sum2"][c] = acc["corr_sum2"].get(c, 0.0) + (sub[c]**2).sum()
    for i, c1 in enumerate(cols):
        for c2 in cols[i+1:]:
            key = (c1, c2)
            acc["corr_cross"][key] = acc["corr_cross"].get(key, 0.0) + (sub[c1]*sub[c2]).sum()


def _corr_finalize(acc: dict) -> pd.DataFrame:
    """Calcula matriz de correlação a partir das somas acumuladas."""
    n    = acc["corr_n"]
    cols = list(acc["corr_sum"].keys())
    if n == 0 or len(cols) < 2:
        return pd.DataFrame()
    mat  = pd.DataFrame(np.eye(len(cols)), index=cols, columns=cols)
    mean = {c: acc["corr_sum"][c] / n for c in cols}
    std  = {c: np.sqrt(max(acc["corr_sum2"][c]/n - mean[c]**2, 0)) for c in cols}
    for i, c1 in enumerate(cols):
        for c2 in cols[i+1:]:
            key  = (c1, c2)
            cov  = acc["corr_cross"].get(key, 0.0) / n - mean[c1] * mean[c2]
            denom = std[c1] * std[c2]
            r    = cov / denom if denom > 1e-12 else 0.0
            r    = max(-1.0, min(1.0, r))
            mat.loc[c1, c2] = r
            mat.loc[c2, c1] = r
    return mat


def acumular_chunk(acc: dict, chunk: pd.DataFrame, sample_anomalia: int):
    """Acumula agregados de um chunk já transformado."""
    n = len(chunk)
    acc["n_linhas"] += n

    # Identificadores únicos
    if "id_usuario" in chunk.columns:
        acc["usuarios"].update(chunk["id_usuario"].dropna().tolist())
    for col, key in [("linha","linhas_unicas"),("operadora","operadoras"),("sindicato","sindicatos")]:
        if col in chunk.columns:
            acc[key].update(chunk[col].dropna().tolist())

    # Somas monetárias
    for col, key in [("vl_linha","vl_linha_sum"),("vl_trans","vl_trans_sum"),("vl_subsidio","vl_subsidio_sum")]:
        if col in chunk.columns:
            acc[key] += chunk[col].sum(skipna=True)

    if "pct_subsidio" in chunk.columns:
        v = chunk["pct_subsidio"].dropna()
        acc["pct_subsidio_sum"] += v.sum()
        acc["pct_subsidio_n"]   += len(v)

    if "qtde_integracoes" in chunk.columns:
        acc["com_integracao"] += int((chunk["qtde_integracoes"] > 0).sum())

    # Nulos
    acc["nulos"].update(chunk.isnull().sum().to_dict())

    # Welford (describe)
    for col in ["vl_linha","vl_trans","vl_subsidio","pct_subsidio","qtde_integracoes"]:
        if col in chunk.columns:
            _welford_update(acc["wf"], col, chunk[col])

    # Histogramas
    for col in ["vl_linha","vl_trans","vl_subsidio","pct_subsidio","latencia_h"]:
        if col in chunk.columns:
            _hist_update(acc, col, chunk[col])

    # Temporal
    if "hora" in chunk.columns:
        acc["hora_cnt"].update(chunk["hora"].dropna().astype(int).tolist())
        if "vl_subsidio" in chunk.columns:
            grp = chunk.groupby("hora")["vl_subsidio"]
            for h, s in grp.sum().items():
                acc["hora_sub_sum"][int(h)] += s
            for h, c in grp.count().items():
                acc["hora_sub_n"][int(h)]   += c

    if "dia_semana" in chunk.columns:
        acc["dia_semana_cnt"].update(chunk["dia_semana"].dropna().tolist())

    if "data_dia" in chunk.columns and "vl_subsidio" in chunk.columns:
        for (d, sub_sum, cnt) in chunk.groupby("data_dia").apply(
            lambda g: (g.name, g["vl_subsidio"].sum(), len(g))
        ):
            acc["diario"][d]["cnt"] += cnt
            acc["diario"][d]["sub"] += sub_sum

    if "latencia_h" in chunk.columns:
        lat_pos = chunk["latencia_h"].dropna()
        lat_pos = lat_pos[lat_pos >= 0]
        if not lat_pos.empty and len(acc["latencia_vals"]) < 100_000:
            acc["latencia_vals"].extend(lat_pos.values[:max(0, 100_000 - len(acc["latencia_vals"]))].tolist())

    # Datas extremas
    if "data_transacao" in chunk.columns:
        mn = chunk["data_transacao"].min()
        mx = chunk["data_transacao"].max()
        if pd.notna(mn) and (acc["dt_min"] is None or mn < acc["dt_min"]):
            acc["dt_min"] = mn
        if pd.notna(mx) and (acc["dt_max"] is None or mx > acc["dt_max"]):
            acc["dt_max"] = mx

    # Entidades
    if "operadora" in chunk.columns:
        acc["operadora_cnt"].update(chunk["operadora"].dropna().tolist())
        if "vl_subsidio" in chunk.columns:
            for op, val in chunk.groupby("operadora")["vl_subsidio"].sum().items():
                acc["operadora_sub"][op] += val
    if "linha" in chunk.columns:
        acc["linha_cnt"].update(chunk["linha"].dropna().tolist())
    if "sindicato" in chunk.columns:
        acc["sindicato_cnt"].update(chunk["sindicato"].dropna().tolist())

    # Resumo por linha (top 200 linhas mais frequentes acumuladas)
    if "linha" in chunk.columns:
        for linha, grp in chunk.groupby("linha"):
            la = acc["linha_agg"][linha]
            la["cnt"] += len(grp)
            if "id_usuario" in grp.columns:
                la["uid"].update(grp["id_usuario"].dropna().tolist())
            for col, lst in [("vl_linha","vl"),("vl_trans","vt"),
                              ("vl_subsidio","vs"),("pct_subsidio","ps")]:
                if col in grp.columns:
                    la[lst].extend(grp[col].dropna().tolist())

    # Sentido / Integrações
    if "sentido_label" in chunk.columns:
        acc["sentido_cnt"].update(chunk["sentido_label"].dropna().tolist())
    if "tem_integracao" in chunk.columns:
        acc["integracao_cnt"].update(chunk["tem_integracao"].dropna().tolist())
        if "vl_subsidio" in chunk.columns:
            for ti, grp in chunk.groupby("tem_integracao"):
                acc["integ_sub_sum"][ti] += grp["vl_subsidio"].sum()
                acc["integ_sub_n"][ti]   += len(grp)

    # Correlações
    _corr_update(acc, chunk)

    # Scatter sample (amostra de até 5000 pontos)
    if "vl_linha" in chunk.columns and "vl_trans" in chunk.columns and "tipo_aplicacao" in chunk.columns:
        sub = chunk[["vl_linha","vl_trans","tipo_aplicacao"]].dropna()
        if not sub.empty and len(acc["scatter_sample"]) < 5000:
            take = min(len(sub), 5000 - len(acc["scatter_sample"]))
            acc["scatter_sample"].extend(sub.sample(min(take, len(sub))).to_dict("records"))

    # Reservoir sample para anomalias
    feat_cols = ["vl_linha","vl_trans","vl_subsidio","pct_subsidio","qtde_integracoes","hora"]
    avail     = [c for c in feat_cols if c in chunk.columns]
    sub_anom  = chunk[avail].dropna()
    if not sub_anom.empty:
        acc["anom_sample"], acc["anom_sample_seen"] = _reservoir_sample(
            acc["anom_sample"], acc["anom_sample_seen"], sub_anom, sample_anomalia
        )


# ════════════════════════════════════════════════════════════════════════════
# LOOP PRINCIPAL DE LEITURA
# ════════════════════════════════════════════════════════════════════════════

def ler_e_acumular(path: str, sep: str, chunk_size: int,
                   sample_anomalia: int, usando_hash: bool) -> dict:
    print(f"\n{'─'*60}")
    print(f"  Carregando: {path}")
    print(f"  Chunk size: {chunk_size:,} linhas")
    print(f"{'─'*60}")

    if usando_hash:
        print("  Identificador de usuário: cartao_hash ✓")
    else:
        print("  ⚠ AVISO: 'Cartão Hash' ausente neste arquivo.")
        print("    Usando 'Nº Cartão' como fallback — contagens de usuários únicos")
        print("    podem estar SUBESTIMADAS (dígitos mascarados geram colisões).")

    acc    = _make_acc()
    reader = pd.read_csv(path, sep=sep, encoding="utf-8-sig",
                         dtype=str, chunksize=chunk_size)

    for i, raw_chunk in enumerate(reader):
        chunk = transform_chunk(raw_chunk, usando_hash)
        acumular_chunk(acc, chunk, sample_anomalia)
        if (i + 1) % 10 == 0 or i == 0:
            print(f"  ... chunk {i+1:4d} processado  "
                  f"({acc['n_linhas']:>12,} linhas acumuladas)")

    print(f"\n  Total: {acc['n_linhas']:,} linhas")
    print(f"  Período: {acc['dt_min']} → {acc['dt_max']}")
    return acc


# ════════════════════════════════════════════════════════════════════════════
# SEÇÕES DE OUTPUT  (operam sobre `acc`, nunca sobre o df completo)
# ════════════════════════════════════════════════════════════════════════════

def secao_visao_geral(acc: dict, usando_hash: bool, out: Path):
    print("\n[1/7] Visão Geral")

    pct_med = (acc["pct_subsidio_sum"] / acc["pct_subsidio_n"]
               if acc["pct_subsidio_n"] else float("nan"))
    id_label = "Usuários únicos (hash)" if usando_hash else "Usuários únicos (fallback: Nº Cartão ⚠)"

    resumo = {
        "Total de transações":         f"{acc['n_linhas']:,}",
        id_label:                      f"{len(acc['usuarios']):,}",
        "Linhas únicas":               f"{len(acc['linhas_unicas']):,}",
        "Operadoras únicas":           f"{len(acc['operadoras']):,}",
        "Sindicatos únicos":           f"{len(acc['sindicatos']):,}",
        "Total Vl Linha (R$)":         f"{acc['vl_linha_sum']:,.2f}",
        "Total Vl Trans (R$)":         f"{acc['vl_trans_sum']:,.2f}",
        "Total Vl Subsídio (R$)":      f"{acc['vl_subsidio_sum']:,.2f}",
        "Média % Subsídio":            f"{pct_med:.1f}%",
        "Com integrações (>0)":        f"{acc['com_integracao']:,}",
    }

    print("\n  ── Resumo Executivo ──")
    for k, v in resumo.items():
        print(f"  {k:<40} {v}")

    # Nulos acumulados
    nulos = {k: v for k, v in acc["nulos"].items() if v > 0}
    if nulos:
        print("\n  ── Campos com valores ausentes ──")
        for col, n in sorted(nulos.items(), key=lambda x: -x[1]):
            print(f"  {col:<30} {n:>10,} ({n/acc['n_linhas']*100:.1f}%)")

    # Estatísticas descritivas a partir do Welford
    rows = []
    for col, s in acc["wf"].items():
        if s["n"] == 0:
            continue
        var  = s["M2"] / s["n"] if s["n"] > 1 else 0
        vals = sorted(s["vals_sample"])
        p25  = np.percentile(vals, 25) if vals else np.nan
        p50  = np.percentile(vals, 50) if vals else np.nan
        p75  = np.percentile(vals, 75) if vals else np.nan
        rows.append({"campo": col, "count": s["n"], "mean": round(s["mean"], 4),
                     "std": round(np.sqrt(var), 4), "min": round(s["min"], 4),
                     "25%": round(p25, 4), "50%": round(p50, 4),
                     "75%": round(p75, 4), "max": round(s["max"], 4)})
    stats = pd.DataFrame(rows).set_index("campo")
    print(f"\n{stats.to_string()}")
    stats.to_csv(out / "01_estatisticas_descritivas.csv")


def secao_valores(acc: dict, out: Path):
    print("[2/7] Distribuições de Valores")

    fig, axes = plt.subplots(1, 3, figsize=FIGSIZE_WIDE)
    for ax, col, label in zip(axes,
        ["vl_linha",    "vl_trans",    "vl_subsidio"],
        ["Vl Linha (R$)","Vl Trans (R$)","Vl Subsídio (R$)"]
    ):
        if col in acc["hist_bins"]:
            edges  = acc["hist_bins"][col]
            counts = acc["hist_counts"][col]
            widths = np.diff(edges)
            ax.bar(edges[:-1], counts, width=widths, align="edge",
                   color="steelblue", alpha=0.8, edgecolor="none")
            ax.set_title(label); ax.set_xlabel("R$"); ax.set_ylabel("Frequência")
            ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    plt.suptitle("Distribuição dos Valores Monetários", fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(out / "02_distribuicao_valores.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Percentual de subsídio
    if "pct_subsidio" in acc["hist_bins"]:
        fig, ax = plt.subplots(figsize=(8, 4))
        edges  = acc["hist_bins"]["pct_subsidio"]
        counts = acc["hist_counts"]["pct_subsidio"]
        ax.bar(edges[:-1], counts, width=np.diff(edges), align="edge",
               color="coral", alpha=0.8, edgecolor="none")
        ax.set_title("Distribuição do Percentual de Subsídio (% do Vl Linha)")
        ax.set_xlabel("% Subsídio"); ax.set_ylabel("Frequência")
        plt.tight_layout()
        plt.savefig(out / "02c_pct_subsidio.png", dpi=150, bbox_inches="tight")
        plt.close()


def secao_temporal(acc: dict, out: Path):
    print("[3/7] Análise Temporal")

    # Por hora
    if acc["hora_cnt"]:
        horas  = range(0, 24)
        cnts   = [acc["hora_cnt"].get(h, 0) for h in horas]
        sub_md = [acc["hora_sub_sum"].get(h, 0) / acc["hora_sub_n"].get(h, 1)
                  if acc["hora_sub_n"].get(h, 0) > 0 else 0 for h in horas]

        fig, axes = plt.subplots(1, 2, figsize=FIGSIZE_WIDE)
        axes[0].bar(horas, cnts, color="steelblue", alpha=0.8)
        axes[0].set_title("Transações por Hora do Dia")
        axes[0].set_xlabel("Hora"); axes[0].set_ylabel("Nº de Transações")
        axes[0].set_xticks(horas)

        axes[1].plot(horas, sub_md, marker="o", color="coral")
        axes[1].set_title("Subsídio Médio por Hora do Dia")
        axes[1].set_xlabel("Hora"); axes[1].set_ylabel("Subsídio Médio (R$)")
        axes[1].set_xticks(horas)

        plt.suptitle("Padrão Temporal das Transações", fontweight="bold")
        plt.tight_layout()
        plt.savefig(out / "03_analise_temporal_hora.png", dpi=150, bbox_inches="tight")
        plt.close()

    # Por dia da semana
    if acc["dia_semana_cnt"]:
        cnts = [acc["dia_semana_cnt"].get(d, 0) for d in DIAS_ORDEM]
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(DIAS_ORDEM, cnts, color="mediumseagreen", alpha=0.85)
        ax.set_title("Transações por Dia da Semana")
        ax.set_xlabel("Dia"); ax.set_ylabel("Nº de Transações")
        plt.tight_layout()
        plt.savefig(out / "03b_transacoes_dia_semana.png", dpi=150, bbox_inches="tight")
        plt.close()

    # Série diária
    if len(acc["diario"]) > 1:
        datas  = sorted(acc["diario"].keys())
        cnts   = [acc["diario"][d]["cnt"] for d in datas]
        subs   = [acc["diario"][d]["sub"] for d in datas]
        labels = [str(d) for d in datas]

        fig, ax1 = plt.subplots(figsize=FIGSIZE_WIDE)
        ax1.bar(labels, cnts, alpha=0.6, label="Transações", color="steelblue")
        ax2 = ax1.twinx()
        ax2.plot(labels, subs, color="red", marker="o", linewidth=2, label="Subsídio Total")
        ax1.set_xlabel("Data"); ax1.set_ylabel("Nº Transações")
        ax2.set_ylabel("Subsídio Total (R$)")
        ax1.tick_params(axis="x", rotation=45)
        # Reduz labels se período longo
        if len(labels) > 60:
            step = max(1, len(labels) // 30)
            ax1.set_xticks(range(0, len(labels), step))
            ax1.set_xticklabels([labels[i] for i in range(0, len(labels), step)], rotation=45)
        plt.title("Série Diária — Transações e Subsídio")
        fig.legend(loc="upper left", bbox_to_anchor=(0.1, 0.95))
        plt.tight_layout()
        plt.savefig(out / "03c_serie_diaria.png", dpi=150, bbox_inches="tight")
        plt.close()

    # Latência de processamento
    if acc["latencia_vals"]:
        lat = np.array(acc["latencia_vals"])
        lat = lat[lat >= 0]
        if len(lat) > 0:
            fig, ax = plt.subplots(figsize=(8, 4))
            clip = np.percentile(lat, 99)
            sns.histplot(lat[lat <= clip], bins=40, kde=True, ax=ax, color="orchid")
            ax.set_title("Latência de Processamento (horas) — amostra")
            ax.set_xlabel("Horas (transação → processamento)")
            ax.set_ylabel("Frequência")
            plt.tight_layout()
            plt.savefig(out / "03d_latencia_processamento.png", dpi=150, bbox_inches="tight")
            plt.close()
            print(f"  Latência média: {lat.mean():.1f} h | mediana: {np.median(lat):.1f} h")


def secao_entidades(acc: dict, out: Path):
    print("[4/7] Análise por Entidade")

    fig, axes = plt.subplots(1, 3, figsize=(18, 7))
    for ax, (cnt, label, cor) in zip(axes, [
        (acc["operadora_cnt"], "Operadora",  "steelblue"),
        (acc["linha_cnt"],     "Linha",      "mediumseagreen"),
        (acc["sindicato_cnt"], "Sindicato",  "coral"),
    ]):
        if cnt:
            top = pd.Series(dict(cnt.most_common(15)))
            top.sort_values().plot.barh(ax=ax, color=cor, alpha=0.85)
            ax.set_title(f"Top 15 — {label} (nº transações)")
            ax.set_xlabel("Nº Transações")
    plt.suptitle("Ranking por Entidade", fontweight="bold")
    plt.tight_layout()
    plt.savefig(out / "04_ranking_entidades.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Subsídio total por operadora
    if acc["operadora_sub"]:
        sub_op = pd.Series(acc["operadora_sub"]).nlargest(15).sort_values()
        fig, ax = plt.subplots(figsize=(10, 6))
        sub_op.plot.barh(ax=ax, color="darkorange", alpha=0.85)
        ax.set_title("Top 15 Operadoras — Subsídio Total (R$)")
        ax.set_xlabel("R$")
        plt.tight_layout()
        plt.savefig(out / "04b_subsidio_por_operadora.png", dpi=150, bbox_inches="tight")
        plt.close()

    # Resumo por linha
    rows = []
    for linha, la in acc["linha_agg"].items():
        rows.append({
            "linha":               linha,
            "transacoes":          la["cnt"],
            "usuarios_unicos":     len(la["uid"]),
            "vl_linha_medio":      round(np.mean(la["vl"]), 2) if la["vl"] else np.nan,
            "vl_trans_medio":      round(np.mean(la["vt"]), 2) if la["vt"] else np.nan,
            "vl_subsidio_total":   round(sum(la["vs"]), 2)     if la["vs"] else np.nan,
            "pct_subsidio_medio":  round(np.mean(la["ps"]), 2) if la["ps"] else np.nan,
        })
    resumo_linha = (pd.DataFrame(rows)
                    .sort_values("transacoes", ascending=False)
                    .set_index("linha"))
    resumo_linha.to_csv(out / "04c_resumo_por_linha.csv")
    print(f"  Resumo por linha exportado ({len(resumo_linha)} linhas).")


def secao_sentido_integracoes(acc: dict, out: Path):
    print("[5/7] Sentido e Integrações")

    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE_WIDE)

    if acc["sentido_cnt"]:
        labels = list(acc["sentido_cnt"].keys())
        vals   = list(acc["sentido_cnt"].values())
        axes[0].pie(vals, labels=labels, autopct="%1.1f%%",
                    startangle=90, colors=sns.color_palette("pastel"))
        axes[0].set_title("Distribuição por Sentido")

    if acc["integracao_cnt"]:
        labels = list(acc["integracao_cnt"].keys())
        vals   = list(acc["integracao_cnt"].values())
        axes[1].bar(labels, vals, color="mediumpurple", alpha=0.85)
        axes[1].set_title("Quantidade de Integrações")
        axes[1].set_xlabel("Nº de Integrações"); axes[1].set_ylabel("Frequência")

    plt.tight_layout()
    plt.savefig(out / "05_sentido_integracoes.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Subsídio médio com/sem integração
    if acc["integ_sub_sum"]:
        cats  = list(acc["integ_sub_sum"].keys())
        medias = [acc["integ_sub_sum"][c] / acc["integ_sub_n"][c]
                  if acc["integ_sub_n"][c] > 0 else 0 for c in cats]
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(cats, medias, color=sns.color_palette("Set2", len(cats)), alpha=0.85)
        ax.set_title("Subsídio Médio — Com vs Sem Integração")
        ax.set_xlabel(""); ax.set_ylabel("Subsídio Médio (R$)")
        plt.tight_layout()
        plt.savefig(out / "05b_subsidio_integracao.png", dpi=150, bbox_inches="tight")
        plt.close()


def secao_correlacoes(acc: dict, out: Path):
    print("[6/7] Correlações")

    corr = _corr_finalize(acc)
    if corr.empty:
        print("  Dados insuficientes para correlações.")
        return

    fig, ax = plt.subplots(figsize=FIGSIZE_SQ)
    mask = np.triu(np.ones_like(corr, dtype=bool))
    sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="coolwarm",
                center=0, linewidths=0.5, ax=ax)
    ax.set_title("Mapa de Correlações — Variáveis Numéricas", fontweight="bold")
    plt.tight_layout()
    plt.savefig(out / "06_mapa_correlacoes.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Scatter (amostra coletada durante leitura)
    if acc["scatter_sample"]:
        sdf   = pd.DataFrame(acc["scatter_sample"])
        tipos = sdf["tipo_aplicacao"].dropna().unique()
        pal   = sns.color_palette("tab10", len(tipos))
        fig, ax = plt.subplots(figsize=FIGSIZE_SQ)
        for tipo, cor in zip(tipos, pal):
            sub = sdf[sdf["tipo_aplicacao"] == tipo]
            ax.scatter(sub["vl_linha"], sub["vl_trans"],
                       label=f"Aplicação {tipo}", alpha=0.5, s=25, color=cor)
        ax.set_xlabel("Vl Linha (tarifa cheia, R$)")
        ax.set_ylabel("Vl Trans (cobrado no cartão, R$)")
        ax.set_title("Tarifa Cheia vs. Valor Cobrado — amostra")
        ax.legend(fontsize=8)
        plt.tight_layout()
        plt.savefig(out / "06b_scatter_vl_linha_trans.png", dpi=150, bbox_inches="tight")
        plt.close()


def secao_anomalias(acc: dict, out: Path):
    print("[7/7] Detecção de Anomalias (Isolation Forest)")

    sample = acc["anom_sample"]
    if len(sample) < 20:
        print("  Dados insuficientes para detecção de anomalias.")
        return

    df_feat = pd.DataFrame(sample).reset_index(drop=True)
    print(f"  Treinando Isolation Forest em amostra de {len(df_feat):,} transações…")

    iso    = IsolationForest(n_estimators=100, contamination=0.03, random_state=42)
    labels = iso.fit_predict(df_feat)
    scores = iso.decision_function(df_feat)

    df_feat["anomalia"]     = (labels == -1).astype(int)
    df_feat["anomaly_score"] = scores

    n_anom = int(df_feat["anomalia"].sum())
    print(f"  Transações sinalizadas: {n_anom} ({n_anom/len(df_feat)*100:.1f}% da amostra)")
    print(f"  (amostra = {len(df_feat):,} de {acc['n_linhas']:,} total "
          f"= {len(df_feat)/acc['n_linhas']*100:.1f}%)")

    if "vl_linha" in df_feat.columns and "vl_subsidio" in df_feat.columns:
        fig, ax = plt.subplots(figsize=FIGSIZE_SQ)
        normal = df_feat[df_feat["anomalia"] == 0]
        anoms  = df_feat[df_feat["anomalia"] == 1]
        ax.scatter(normal["vl_linha"], normal["vl_subsidio"],
                   alpha=0.3, s=15, color="steelblue", label="Normal")
        ax.scatter(anoms["vl_linha"],  anoms["vl_subsidio"],
                   alpha=0.9, s=50, color="red", marker="X",
                   label=f"Anômalo (n={n_anom})")
        ax.set_xlabel("Vl Linha (R$)"); ax.set_ylabel("Vl Subsídio (R$)")
        ax.set_title("Detecção de Anomalias — Isolation Forest (amostra)")
        ax.legend()
        plt.tight_layout()
        plt.savefig(out / "07_anomalias_isolation_forest.png", dpi=150, bbox_inches="tight")
        plt.close()

    df_feat[df_feat["anomalia"] == 1].to_csv(out / "07_transacoes_anomalas.csv", index=False)
    print("  Transações anômalas exportadas em: 07_transacoes_anomalas.csv")


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="EDA — Bilhete Único Intermunicipal (BUI)"
    )
    parser.add_argument("--input",           required=True,
                        help="Caminho do arquivo de dados (.txt/.csv)")
    parser.add_argument("--sep",             default=";",
                        help="Delimitador (padrão: ';')")
    parser.add_argument("--output",          default="relatorio_eda",
                        help="Pasta de saída")
    parser.add_argument("--chunk",           type=int, default=200_000,
                        help="Linhas por chunk (padrão: 200000)")
    parser.add_argument("--sample-anomalia", type=int, default=500_000,
                        help="Máx. linhas na amostra do Isolation Forest (padrão: 500000)")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    meta        = detectar_metadados(args.input, args.sep)
    usando_hash = meta["usando_hash"]

    acc = ler_e_acumular(
        path            = args.input,
        sep             = args.sep,
        chunk_size      = args.chunk,
        sample_anomalia = args.sample_anomalia,
        usando_hash     = usando_hash,
    )

    secao_visao_geral(acc, usando_hash, out)
    secao_valores(acc, out)
    secao_temporal(acc, out)
    secao_entidades(acc, out)
    secao_sentido_integracoes(acc, out)
    secao_correlacoes(acc, out)
    secao_anomalias(acc, out)

    print(f"\n{'═'*60}")
    print(f"  EDA concluída. Outputs salvos em: {out.resolve()}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
