"""
Análise Exploratória de Dados — Bilhete Único Intermunicipal (BUI)
SETRAM / LIA² / UERJ

Campos:
    Nº Cartão            — Identificador anonimizado do usuário (LGPD)
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

Uso:
    python eda_bui.py --input arquivo.txt [--sep ";"] [--output relatorio/]
    
    O arquivo pode ser CSV ou TXT delimitado por ponto-e-vírgula.
    Os valores monetários devem estar no formato brasileiro: R$ 1.234,56
"""
import time 
import argparse
import os
import warnings
from pathlib import Path
from collections import defaultdict
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from constants import *
from utility import txt_faltantes
warnings.filterwarnings("ignore")
import duckdb

# ── Estilo global ────────────────────────────────────────────────────────────
sns.set_theme(style="whitegrid", palette="muted", font_scale=1.05)
FIGSIZE_WIDE = (14, 5)
FIGSIZE_SQ   = (10, 7)
FIGSIZE_TALL = (12, 8)


TIPO="GT"
SENTIDO_MAP = {0: "Não informado", 1: "Ida", 2: "Volta"}
DIAS_EN = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
NOMES_PT = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]
MAP_DIAS = dict(zip(DIAS_EN, NOMES_PT))

LAT_MAX = 240            # horas; valores acima disso caem no último bin
LAT_BINS = np.linspace(0, LAT_MAX, 241)

COLS_IN_USE = [
    "data_transacao", "data_processamento", "num_cartao", "hora", "dia_semana",
    "data_dia", "sindicato", "operadora", "linha", "num_carro", "tipo_aplicacao",
]
def add(acc, new):
    return new if acc is None else acc.add(new, fill_value=0) 
# ════════════════════════════════════════════════════════════════════════════
# 1. CARGA E LIMPEZA
# ════════════════════════════════════════════════════════════════════════════
def load_data_spec(path: str, cols_use:list, tipo:str,sep: str=",",chunksize=None):
    #auxiliar de load_data que especifica as colunas a serem lidas, e pula a leitura se nao ha nenhuma coluna em comum, usando o dicionario que ja sabemos que existe
    dicionario_tipo=pega_dict_processado(tipo)

    available_cols = [ #pegar colunas em comum com cols_use e dicionario do tipo
        col for col in cols_use
        if col in dicionario_tipo
    ]
    dtypes={
        k:v for k,v in DTYPES_GT.items()
        if k in available_cols
    }
    if available_cols:
        print(f"Acessando arquivo {path}")
        return pd.read_csv(
            path,
            sep=sep,
            usecols=available_cols, #estamos na parte ja processada
            dtype=dtypes,
            chunksize=chunksize,
        )
    return pd.DataFrame()

def date_formatter(df:pd.DataFrame,tipo:str):
    if tipo=="GT":
            for col in ["data_transacao", "data_processamento", "data_ordem"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], dayfirst=False, errors="coerce")
    if tipo=="BE" or tipo=="BU":
        for col in ["data_transacao", "data_processamento"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
            if "data_ordem" in df.columns:
                df["data_ordem"]=pd.to_datetime(df["data_ordem"], dayfirst=False, errors="coerce")
    return df
# ════════════════════════════════════════════════════════════════════════════
# 2. VISÃO GERAL
# ════════════════════════════════════════════════════════════════════════════

def secao_visao_geral(input:Path,out: Path,sep:str,data_ini:str,data_fim:str):
    print("\n Visão Geral GT")

    result = duckdb.sql(f"""
    SELECT
        COUNT(*) AS total_transacoes,
        COUNT(DISTINCT cartao_hash) AS hashes_unicos,
        COUNT(DISTINCT linha) AS linhas_unicas,
        COUNT(DISTINCT operadora) AS operadoras_unicas,
        COUNT(DISTINCT sindicato) AS sindicatos_unicos
    FROM read_csv(
        '{input}/*.csv',
        all_varchar=true,
        header=true
    )
    """).fetchone()

    resumo = {
        "Total de transações": result[0],
        "Hashes únicos": result[1],
        "Linhas únicas": result[2],
        "Operadoras únicas": result[3],
        "Sindicatos únicos": result[4],
    }

    # Exportar resumo para TXT
    with open(out / "01_resumo_executivo.txt", "w", encoding="utf-8") as f:
        f.write("RESUMO EXECUTIVO\n")
        f.write("=" * 50 + "\n\n")

        for k, v in resumo.items():
            f.write(f"{k:<35} {v}\n")


# ════════════════════════════════════════════════════════════════════════════
# 3. Varredura de Acumulação
# ════════════════════════════════════════════════════════════════════════════

def varredura_unica(input: Path, out: Path, sep: str, data_ini: str, data_fim: str):
    print("Varredura única GT")

    # --- acumuladores (todos pequenos, exceto cartoes_unicos) ---
    hora_cnt = dia_semana_cnt = modal_cnt = None
    operadora_cnt = linha_cnt = sindicato_cnt = aplicacao_cnt = None
    linha_dia = None                      # DataFrame linha x dia_semana
    lat_modal = None                      # (modal, dia_semana) -> sum, count
    diario_trans = defaultdict(int)
    carros_unicos = defaultdict(set)

    lat_sum = 0.0
    lat_n = 0
    lat_hist = np.zeros(len(LAT_BINS) - 1, dtype=np.int64)

    with os.scandir(input) as files:
        for file in files:
            if not file.is_file():
                continue
            for dia in load_data_spec(file.path, COLS_IN_USE, TIPO, sep, chunksize=100_000):
                dia = date_formatter(dia, TIPO)
                dia = dia[(dia["data_transacao"] >= data_ini) & (dia["data_transacao"] < data_fim) ]
                if dia.empty:
                    continue

                dia_pt = dia["dia_semana"].map(MAP_DIAS)

                # ---------- temporal ----------
                hora_cnt = add(hora_cnt, dia["hora"].value_counts())
                dia_semana_cnt = add(dia_semana_cnt, dia_pt.value_counts())

                for data, n in dia["data_dia"].value_counts().items():
                    diario_trans[data] += n

                modal = dia["sindicato"].map(MAP_MODAL)        # coluna nova, não renomeia
                modal_cnt = add(modal_cnt, modal.value_counts())

                lat = (dia["data_processamento"] - dia["data_transacao"]).dt.total_seconds() / 3600
                ok = lat >= 0
                lat_ok = lat[ok]
                lat_sum += lat_ok.sum()
                lat_n += len(lat_ok)
                lat_hist += np.histogram(lat_ok.clip(upper=LAT_MAX), bins=LAT_BINS)[0]

                g = (pd.DataFrame({"modal": modal[ok], "dia": dia_pt[ok], "lat": lat_ok})
                       .groupby(["modal", "dia"],observed=True)["lat"].agg(["sum", "count"]))
                lat_modal = add(lat_modal, g)

                # ---------- entidades ----------
                operadora_cnt = add(operadora_cnt, dia["operadora"].value_counts())
                sindicato_cnt = add(sindicato_cnt, dia["sindicato"].value_counts())
                aplicacao_cnt = add(aplicacao_cnt, dia["tipo_aplicacao"].value_counts())
                linha_cnt = add(linha_cnt, dia["linha"].value_counts())
                linha_dia = add(linha_dia, pd.crosstab(dia["linha"], dia_pt))
                for linha, s in dia.dropna(subset=["num_carro"]).groupby("linha")["num_carro"].unique():
                    carros_unicos[linha].update(s)

    # ---------- pós-processamento ----------
    hora_cnt = hora_cnt.sort_index()
    dia_cnt = dia_semana_cnt.reindex(NOMES_PT, fill_value=0)

    # latência: média exata, mediana aproximada pelo histograma
    lat_media = lat_sum / lat_n
    cum = np.cumsum(lat_hist)
    lat_mediana = LAT_BINS[np.searchsorted(cum, lat_n / 2)]
    print(f"  Latência média: {lat_media:.1f} h | mediana ≈ {lat_mediana:.1f} h")

    # latência média por modal x dia da semana
    df_sum = lat_modal["sum"].unstack().rename(columns=MAP_DIAS).reindex(columns=NOMES_PT, fill_value=0)
    df_cnt = lat_modal["count"].unstack().rename(columns=MAP_DIAS).reindex(columns=NOMES_PT, fill_value=0)
    df_lat_media = df_sum / df_cnt.replace(0, np.nan)

    # resumo por linha
    linhas = list(linha_cnt.index)
    resumo_linha = pd.DataFrame({
        "linha": linhas,
        "transacoes": linha_cnt.values,
        "carros_unicos": [len(carros_unicos[l]) for l in linhas],
    })
    resumo_linha = resumo_linha.join(linha_dia.reindex(index=linhas, columns=NOMES_PT, fill_value=0).reset_index(drop=True)
    ).sort_values("transacoes", ascending=False).round(2)
    resumo_linha.to_csv(out / "04c_resumo_por_linha.csv", index=False)

    # ---------- gráficos ----------
    fig, ax = plt.subplots(figsize=FIGSIZE_WIDE)
    ax.bar(hora_cnt.index, hora_cnt.values, color="steelblue", alpha=0.8)
    ax.set_title("Transações por Hora do Dia")
    ax.set_xlabel("Hora"); ax.set_ylabel("Nº de Transações")
    ax.set_xticks(range(0, 24))
    plt.tight_layout()
    plt.savefig(out / "03a_transacoes_hora.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Transações por dia da semana
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(dia_cnt.index, dia_cnt.values, color="mediumseagreen", alpha=0.85)
    ax.set_title("Transações por Dia da Semana")
    ax.set_xlabel("Dia"); ax.set_ylabel("Nº de Transações")
    plt.tight_layout()
    plt.savefig(out / "03b_transacoes_dia_semana.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Pie modal
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.pie(modal_cnt.values, labels=modal_cnt.index, autopct="%1.1f%%",
           startangle=90, colors=sns.color_palette("pastel"))
    ax.set_title("Distribuição por Modal")
    plt.tight_layout()
    plt.savefig(out / "04e_pie_modal.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Série diária
    diario = pd.DataFrame({"data_dia": list(diario_trans.keys()),
                           "transacoes": list(diario_trans.values())})
    diario["data_dia"] = pd.to_datetime(diario["data_dia"])
    diario = diario.sort_values("data_dia")
    fig, ax1 = plt.subplots(figsize=FIGSIZE_WIDE)
    ax1.bar(diario["data_dia"], diario["transacoes"], alpha=0.6, label="Transações")
    ax1.set_xlabel("Data (ticks a cada segunda)")
    ax1.set_ylabel("Nº Transações")
    ax1.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax1.tick_params(axis="x", which="major", bottom=True, length=5, width=1,
                    color="black", direction="out", rotation=45)
    ax1.set_title("Série Diária — Transações")
    fig.legend(loc="upper left", bbox_to_anchor=(0.1, 0.95))
    plt.tight_layout()
    plt.savefig(out / "03c_serie_diaria.png", dpi=150, bbox_inches="tight")
    plt.close()
    diario_dict = diario.set_index("data_dia")["transacoes"].to_dict()
    txt_faltantes(out=out, data_ini=data_ini, data_fim=data_fim,
                  diario=diario_dict, minimo=MINIMO_ENTRADAS_GT)

    # Latência média por modal x dia da semana (grid dinâmico)
    n = len(df_lat_media)
    nrows = ceil(n / 2)
    fig, axes = plt.subplots(nrows, 2, figsize=(18, 3.5 * nrows), squeeze=False)
    axes = axes.ravel()
    for ax, (modal, row) in zip(axes, df_lat_media.iterrows()):
        ax.bar(NOMES_PT, row.values, color="mediumseagreen", alpha=0.85)
        ax.set_title(str(modal))
        ax.set_ylabel("Latência Média em Horas")
    for ax in axes[n:]:
        ax.set_visible(False)
    plt.suptitle("Latência Média por Modal", fontweight="bold")
    plt.tight_layout()
    plt.savefig(out / "03f_latencia_media_semana_modal.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Último modal isolado
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(NOMES_PT, df_lat_media.iloc[-1].values, color="mediumseagreen", alpha=0.85)
    ax.set_title(str(df_lat_media.index[-1]))
    ax.set_ylabel("Latência Média em Horas")
    plt.tight_layout()
    plt.savefig(out / "03g_latencia_media_semana_modal.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Histograma de latência (a partir dos bins acumulados)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(LAT_BINS[:-1], lat_hist, width=np.diff(LAT_BINS), align="edge", color="orchid")
    ax.set_title("Latência de Processamento (horas)")
    ax.set_xlabel("Horas (transação → processamento)")
    ax.set_ylabel("Frequência")
    plt.tight_layout()
    plt.savefig(out / "03d_latencia_processamento.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Ranking por entidade
    valores = {"operadora": operadora_cnt, "linha": linha_cnt,
               "sindicato": sindicato_cnt, "aplicacao": aplicacao_cnt}
    fig, axes = plt.subplots(1, 3, figsize=(18, 7))          # <- faltava
    for ax, (col, label, cor) in zip(axes, [
        ("operadora", "Operadora", "steelblue"),
        ("linha",     "Linha",     "mediumseagreen"),
        ("sindicato", "Sindicato", "coral"),
    ]):
        top_bar(valores[col], f"Top 15 — {label} (nº transações)", "Nº Transações", ax, color=cor)
    plt.suptitle("Ranking por Entidade", fontweight="bold")
    plt.tight_layout()
    plt.savefig(out / "04_ranking_entidades.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Top 15 aplicações (barras)
    fig, ax = plt.subplots(figsize=(10, 6))
    top_bar(valores["aplicacao"], "Top 15 — aplicação (nº transações)", "Nº Transações", ax)
    plt.tight_layout()
    plt.savefig(out / "04b_transacoes_por_aplicacao.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Pie aplicações: top 10 + Outros
    ap = valores["aplicacao"].sort_values(ascending=False)
    ap_pie = pd.concat([ap.head(10), pd.Series({"Outros": ap.iloc[10:].sum()})]) if len(ap) > 10 else ap
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.pie(ap_pie.values, labels=ap_pie.index, autopct="%1.1f%%",
           startangle=90, colors=sns.color_palette("pastel"))
    ax.set_title("Distribuição por Aplicação")
    plt.tight_layout()
    plt.savefig(out / "04d_pie_aplicacao.png", dpi=150, bbox_inches="tight")
    plt.close()

    print(f"  Resumo por linha exportado ({len(resumo_linha)} linhas).")
    
def top_bar(series: pd.Series, title: str, xlabel: str, ax, n=15, color="steelblue"):
    top = series.nlargest(n)
    top.plot.barh(ax=ax, color=color, alpha=0.85)
    ax.invert_yaxis()
    ax.set_title(title)
    ax.set_xlabel(xlabel)

#Função que chama tudo
def EDA_GT(input,output,sep,data_ini,data_fim):
    start_time = time.perf_counter()
    out=Path(output)
    out.mkdir(parents=True, exist_ok=True)
    input=Path(input)

    secao_visao_geral(input, out,sep,data_ini,data_fim)
    secao_temporal(input,out,sep,data_ini,data_fim)
    secao_entidades(input,out,sep,data_ini,data_fim)

    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"Execution time: {execution_time:.6f} seconds(EDA de GT)")