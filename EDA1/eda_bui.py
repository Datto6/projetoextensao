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

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import LabelEncoder
from constants import *
warnings.filterwarnings("ignore")

# ── Estilo global ────────────────────────────────────────────────────────────
sns.set_theme(style="whitegrid", palette="muted", font_scale=1.05)
FIGSIZE_WIDE = (14, 5)
FIGSIZE_SQ   = (10, 7)
FIGSIZE_TALL = (12, 8)
TIPOS=["agosto\\BE","agosto\\BU","agosto\\GT"]
SENTIDO_MAP = {0: "Não informado", 1: "Ida", 2: "Volta"}

# ════════════════════════════════════════════════════════════════════════════
# 1. CARGA E LIMPEZA
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
def pega_dict(tipo: str) -> dict:
    if tipo=="BE": return COLUNAS_BE
    if tipo=="BU": return COLUNAS_BU
    if tipo=="GT": return COLUNAS_GT

def load_data(path: str, cols_use:dict,tipo:str, sep: str = ";") -> pd.DataFrame:
    print(f"\n{'─'*60}")
    print(f"  Carregando: {path}")
    print(f"{'─'*60}")
    df = pd.read_csv(path, sep=sep, encoding="utf-8-sig", dtype=str,usecols=cols_use.keys())

    # Normalizar nomes de colunas (strip de espaços)
    df.columns = df.columns.str.strip()
    df.rename(columns=cols_use, inplace=True)

    # Datas
    if tipo=="GT":
        for col in ["data_transacao", "data_processamento", "data_ordem"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], dayfirst=False, errors="coerce")
    if tipo=="BE" or tipo=="BU":
        for col in ["data_transacao", "data_processamento"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
        if "data_ordem" in df.columns:
            df["data_ordem"]=pd.to_datetime(df[col], dayfirst=False, errors="coerce")


    # Monetários
    for col in ["vl_linha", "vl_trans", "vl_subsidio"]:
        if col in df.columns:
            df[col] = parse_brl(df[col])

    # Numéricos simples
    for col in ["sentido", "qtde_integracoes", "num_carro", "num_validador", "num_ordem"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Campos derivados
    if "data_transacao" in df.columns:
        df["hora"]       = df["data_transacao"].dt.hour
        df["dia_semana"] = df["data_transacao"].dt.day_name()
        df["data_dia"]   = df["data_transacao"].dt.date

    if "vl_linha" in df.columns and "vl_trans" in df.columns:
        df["pct_subsidio"] = (df["vl_subsidio"] / df["vl_linha"] * 100).round(2)

    if "sentido" in df.columns:
        df["sentido_label"] = df["sentido"].map(SENTIDO_MAP)

    # Prefixo do tipo de benefício (ex: '400' de '400-VALE TRANSPORTE…')
    if "descricao_aplicacao" in df.columns:
        df["tipo_aplicacao"] = df["descricao_aplicacao"].str.extract(r"^(\d+)")

    print(f"  Linhas: {len(df):,}  |  Colunas: {df.shape[1]}")
    print(f"  Período: {df['data_transacao'].min()} → {df['data_transacao'].max()}" if "data_transacao" in df.columns else "")
    return df

def load_data_spec(path: str, cols_use:dict, tipo:str,sep: str=";"):
    #auxiliar de load_data que especifica as colunas a serem lidas, e pula a leitura se nao ha nenhuma coluna em comum, usando o dicionario que ja sabemos que existe
    dicionario_tipo=pega_dict(tipo)

    available_cols = { #pegar colunas em comum com cols_use e dicionario do tipo
        k: v for k, v in cols_use.items()
        if k in dicionario_tipo
    }

    if available_cols:
        return load_data(path, available_cols,tipo, sep) #passar elas pro load_data

    return pd.DataFrame() 
# ════════════════════════════════════════════════════════════════════════════
# 2. VISÃO GERAL
# ════════════════════════════════════════════════════════════════════════════

def secao_visao_geral(df: pd.DataFrame, out: Path):
    print("\n[1/7] Visão Geral")

    resumo = {
        "Total de transações":         len(df),
        "Cartões únicos":              df["num_cartao"].nunique() if "num_cartao" in df else "—",
        "Linhas únicas":               df["linha"].nunique() if "linha" in df else "—",
        "Operadoras únicas":           df["operadora"].nunique() if "operadora" in df else "—",
        "Sindicatos únicos":           df["sindicato"].nunique() if "sindicato" in df else "—",
        "Total Vl Linha (R$)":         f"{df['vl_linha'].sum():,.2f}" if "vl_linha" in df else "—",
        "Total Vl Trans (R$)":         f"{df['vl_trans'].sum():,.2f}" if "vl_trans" in df else "—",
        "Total Vl Subsídio (R$)":      f"{df['vl_subsidio'].sum():,.2f}" if "vl_subsidio" in df else "—",
        "Média % Subsídio":            f"{df['pct_subsidio'].mean():.1f}%" if "pct_subsidio" in df else "—",
        "Com integrações (>0)":        int((df["qtde_integracoes"] > 0).sum()) if "qtde_integracoes" in df else "—",
    }

    print("\n  ── Resumo Executivo ──")
    for k, v in resumo.items():
        print(f"  {k:<35} {v}")

    # Tabela de nulos
    nulos = df.isnull().sum()
    nulos = nulos[nulos > 0]
    if not nulos.empty:
        print("\n  ── Campos com valores ausentes ──")
        for col, n in nulos.items():
            print(f"  {col:<30} {n:>6} ({n/len(df)*100:.1f}%)")

    # Estatísticas descritivas numéricas
    cols=list(set(["vl_linha","vl_trans","vl_subsidio","pct_subsidio","qtde_integracoes"]) & set(df.columns)) #intersecao entre colunas que queremos e coluna na df

    stats = df[cols].describe().round(2)
    print(f"\n{stats.to_string()}")

    stats.to_csv(out / "01_estatisticas_descritivas.csv")


# ════════════════════════════════════════════════════════════════════════════
# 3. DISTRIBUIÇÕES DE VALORES
# ════════════════════════════════════════════════════════════════════════════

def secao_valores(out: Path):
    print("[2/7] Distribuições de Valores")

    fig, axes = plt.subplots(1, 3, figsize=FIGSIZE_WIDE)
    cols_val = [("vl_linha", "Vl Linha (R$)"),
                ("vl_trans", "Vl Trans (R$)"),
                ("vl_subsidio", "Vl Subsídio (R$)")]

    vl_linha_cnt=pd.Series(dtype=np.int64)
    vl_trans_cnt=pd.Series(dtype=np.int64)
    vl_subsidio_cnt=pd.Series(dtype=np.int64)
    pct_subsidio_cnt=pd.Series(dtype=np.int64)

    cols_in_use={
        "Vl Linha":                "vl_linha",
        "Vl Trans":                "vl_trans",
        "Vl Subsídio":             "vl_subsidio",
    } #colunas que vamos ler dos arquivos do mes


    for pasta in TIPOS:
        with os.scandir(pasta) as files:
            for file in files:
                dia = load_data_spec(file.path,cols_in_use,pasta[-2:], ";") #pegar tipo de arquivo como ultimos 2 chars da pasta(pasta ta agosto/BU agosto/BE etc)
                dia=dia[dia["data_transacao"].dt.month == 8]
                if "vl_linha" in dia.columns:
                    cnt = dia["vl_linha"].value_counts() 
                    vl_linha_cnt = vl_linha_cnt.add(cnt, fill_value=0)
                if "vl_trans" in dia.columns:
                    cnt = dia["vl_trans"].value_counts()
                    vl_trans_cnt = vl_trans_cnt.add(cnt, fill_value=0)
                if "vl_subsidio" in dia.columns:
                    cnt = dia["vl_subsidio"].value_counts()
                    vl_subsidio_cnt = vl_subsidio_cnt.add(cnt, fill_value=0)
                if "pct_subsidio" in dia.columns:
                    cnt = dia["pct_subsidio"].dropna().clip(0, 100).value_counts()
                    pct_subsidio_cnt=pct_subsidio_cnt.add(cnt,fill_value=0)
    valores = { #manter num dict p economizar ficar mais legivel
    "vl_linha": vl_linha_cnt,
    "vl_trans": vl_trans_cnt,
    "vl_subsidio": vl_subsidio_cnt
    }
    for ax, (col, label) in zip(axes, cols_val):
        serie = valores[col].sort_index()
        bins = np.arange(0, 30, 0.5)
        # Criar bins p cada valor distinto
        bin_ids = pd.cut(serie.index.astype(float),bins=bins,include_lowest=True)

        # Somar frequencias dentro de cada bin
        hist = serie.groupby(bin_ids).sum()

        # Centros de bin p plotar
        centers = [(interval.left + interval.right)/2 for interval in hist.index]

        ax.bar(centers,hist.values,width=0.5)
        ax.set_title(label)
        ax.set_xlabel("R$")
        ax.set_ylabel("Frequência")
        ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))

    plt.suptitle("Distribuição dos Valores Monetários", fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(out / "02_distribuicao_valores.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Boxplots por tipo de aplicação--> retirei, pois nao fazia muito sentido/ilegivel

    # Percentual de subsídio
    fig, ax = plt.subplots(figsize=(8, 4))
    serie = pct_subsidio_cnt.sort_index()

    bins = np.arange(0, 102.5, 2.5)

    bin_ids = pd.cut(serie.index.astype(float),bins=bins,include_lowest=True) #determina ids de bins
    hist = serie.groupby(bin_ids).sum() #soma as frequencias dentro de cada bin 
    centers = [(interval.left + interval.right) / 2
        for interval in hist.index]

    ax.bar(centers, hist.values, width=2.5)
    ax.set_title("Distribuição do Percentual de Subsídio (% do Vl Linha)")
    ax.set_xlabel("% Subsídio")
    ax.set_ylabel("Frequência")
    plt.tight_layout()
    plt.savefig(out / "02c_pct_subsidio.png", dpi=150, bbox_inches="tight")
    plt.close()


# ════════════════════════════════════════════════════════════════════════════
# 4. ANÁLISE TEMPORAL
# ════════════════════════════════════════════════════════════════════════════

def secao_temporal(out: Path):
    print("[3/7] Análise Temporal")
    hora_cnt = pd.Series(dtype=np.int64)
    hora_sub_sum = pd.Series(dtype=np.float64)
    diario_trans = {}
    diario_subs = {}
    all_latencies = []
    dia_semana_cnt = pd.Series(dtype=np.int64)
    cols_in_use={
        "Data da Transação":       "data_transacao",
        "Data do Processamento":   "data_processamento",
        "Vl Linha":                "vl_linha",
        "Vl Trans":                "vl_trans",
        "Vl Subsídio":             "vl_subsidio",
        "Nº Cartão": "num_cartao",
    }
    for pasta in TIPOS: #extrai apenas essas colunas de cada arquivo do mes, a ser usado pela analise temporal
        with os.scandir(pasta) as files:
            for file in files:
                dia = load_data_spec(file.path,cols_in_use,pasta[-2:],";") #pasta [-2:] indica do tipo da entrada,definida no diretorio
                dia=dia[dia["data_transacao"].dt.month == 8]
                if "hora" in dia.columns: #agregando transacoes por hora 
                    cnt = dia["hora"].value_counts()
                    hora_cnt = hora_cnt.add(cnt, fill_value=0)
                    if "vl_subsidio" in dia.columns: #agregando subsidio por hora
                        sub_sum = dia.groupby("hora")["vl_subsidio"].sum()
                        hora_sub_sum = hora_sub_sum.add(sub_sum, fill_value=0) #cada hora tem sua soma de subsidio aqui
                if "dia_semana" in dia.columns: #agregando transacoes por dia de semana
                    ordem_dias = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                    nomes_pt   = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]
                    map_dias   = dict(zip(ordem_dias, nomes_pt)) #apenas p abreviar dias de semana
                    cnt=dia["dia_semana"].map(map_dias).value_counts().reindex(nomes_pt,fill_value=0)
                    dia_semana_cnt=dia_semana_cnt.add(cnt,fill_value=0)

                if all(c in dia.columns for c in ["data_dia", "num_cartao", "vl_subsidio"]): #so entra se dia tem todas essas colunas
                    grp = dia.groupby("data_dia").agg(
                            transacoes=("num_cartao", "count"),
                            subsidio_total=("vl_subsidio", "sum"))
                    for data, row in grp.iterrows():
                        diario_trans[data] = (diario_trans.get(data, 0)+ row["transacoes"])
                        diario_subs[data] = (diario_subs.get(data, 0.0)+ row["subsidio_total"])

                if all(c in dia.columns for c in ["data_transacao", "data_processamento"]): #idem
                    lat = (dia["data_processamento"]- dia["data_transacao"]).dt.total_seconds() / 3600
                    lat = lat[lat >= 0]
                    all_latencies.append(lat) #agregando latencias 

    hora_cnt = hora_cnt.sort_index()#quantas transacoes por hora

    hora_sub_sum = hora_sub_sum.sort_index()
    hora_sub_media = hora_sub_sum / hora_cnt #calculando medias de subsidio por hora com total agregado 
    # Transações por hora do dia
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE_WIDE)
    axes[0].bar(hora_cnt.index, hora_cnt.values, color="steelblue", alpha=0.8)
    axes[0].set_title("Transações por Hora do Dia")
    axes[0].set_xlabel("Hora")
    axes[0].set_ylabel("Nº de Transações")
    axes[0].set_xticks(range(0, 24))

    # Subsídio médio por hora
    axes[1].plot(hora_sub_media.index, hora_sub_media.values, marker="o", color="coral")
    axes[1].set_title("Subsídio Médio por Hora do Dia")
    axes[1].set_xlabel("Hora")
    axes[1].set_ylabel("Subsídio Médio (R$)")
    axes[1].set_xticks(range(0, 24))

    plt.suptitle("Padrão Temporal das Transações", fontweight="bold")
    plt.tight_layout()
    plt.savefig(out / "03_analise_temporal_hora.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Transações por dia da semana
    nomes_pt   = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]
    dia_cnt = dia_semana_cnt.reindex(nomes_pt, fill_value=0)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(dia_cnt.index, dia_cnt.values, color="mediumseagreen", alpha=0.85)
    ax.set_title("Transações por Dia da Semana")
    ax.set_xlabel("Dia")
    ax.set_ylabel("Nº de Transações")
    plt.tight_layout()
    plt.savefig(out / "03b_transacoes_dia_semana.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Série diária (se houver mais de 1 dia)
    diario = pd.DataFrame({
        "data_dia": list(diario_trans.keys()),
        "transacoes": list(diario_trans.values())
    })

    diario["subsidio_total"] = diario["data_dia"].map(diario_subs)

    diario = diario.sort_values("data_dia")

    fig, ax1 = plt.subplots(figsize=FIGSIZE_WIDE)
    ax1.bar(diario["data_dia"].astype(str), diario["transacoes"], alpha=0.6, label="Transações")
    ax2 = ax1.twinx()
    ax2.plot(diario["data_dia"].astype(str), diario["subsidio_total"], color="red",
                marker="o", linewidth=2, label="Subsídio Total")
    ax1.set_xlabel("Data")
    ax1.set_ylabel("Nº Transações")
    ax2.set_ylabel("Subsídio Total (R$)")
    ax1.tick_params(axis="x", rotation=45)
    plt.title("Série Diária — Transações e Subsídio")
    fig.legend(loc="upper left", bbox_to_anchor=(0.1, 0.95))
    plt.tight_layout()
    plt.savefig(out / "03c_serie_diaria.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Latência de processamento
    lat_pos = pd.concat(all_latencies, ignore_index=True)

    if not lat_pos.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        sns.histplot(lat_pos.clip(upper=lat_pos.quantile(0.99)), bins=40, kde=False, ax=ax, color="orchid")
        ax.set_title("Latência de Processamento (horas)")
        ax.set_xlabel("Horas (transação → processamento)")
        ax.set_ylabel("Frequência")
        plt.tight_layout()
        plt.savefig(out / "03d_latencia_processamento.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Latência média: {lat_pos.mean():.1f} h | mediana: {lat_pos.median():.1f} h")


# ════════════════════════════════════════════════════════════════════════════
# 5. ANÁLISE POR ENTIDADE (Operadora, Linha, Sindicato)
# ════════════════════════════════════════════════════════════════════════════

def top_bar(series: pd.Series, title: str, xlabel: str, ax, n=15, color="steelblue"):
    top = series.nlargest(n)
    top.plot.barh(ax=ax, color=color, alpha=0.85)
    ax.invert_yaxis()
    ax.set_title(title)
    ax.set_xlabel(xlabel)


def secao_entidades( out: Path):
    print("[4/7] Análise por Entidade")

    fig, axes = plt.subplots(1, 3, figsize=(18, 7))
    cols_in_use={
        "Operadora":               "operadora",
        "Vl Linha":                "vl_linha",
        "Vl Trans":                "vl_trans",
        "Vl Subsídio":             "vl_subsidio",
        "Linha":                   "linha",
        "Sindicato":               "sindicato",
        "pct_subsidio":            "pct_subsidio",
        "Nº Cartão": "num_cartao",
        "Nº Carro":                "num_carro",
        "Data da Transação":       "data_transacao",
    }
    operadora_cnt = pd.Series(dtype=np.int64)
    linha_cnt = pd.Series(dtype=np.int64)
    sindicato_cnt = pd.Series(dtype=np.int64)
    subsidio_operadora = pd.Series(dtype=float) #definindo series especificas para usar para o mes todo

    dia_semana_cnt=pd.Series(dtype=np.int64)#atributos para fazer resumo por linha
    dia_semana_por_linha = defaultdict(lambda: defaultdict(int)) #dicionario com dicionario dentro

    transacoes = defaultdict(int)

    vl_linha_sum = defaultdict(float)
    vl_linha_count = defaultdict(int)
    
    vl_trans_sum = defaultdict(float)
    vl_trans_count = defaultdict(int)

    subsidio_total = defaultdict(float)

    pct_sum = defaultdict(float)
    pct_count = defaultdict(int)#sum e count para fazer medias depois

    cartoes_unicos = defaultdict(set)
    carros_unicos=defaultdict(set)
    for pasta in TIPOS:
        with os.scandir(pasta) as files:
            for file in files:
                dia = load_data_spec(file.path,cols_in_use,pasta[-2:], ";") #pegar tipo de arquivo como ultimos 2 chars da pasta(pasta ta agosto/BU agosto/BE etc)
                if "operadora" in dia.columns: #transacoes por operadora 
                    cnt = dia["operadora"].value_counts()
                    operadora_cnt = operadora_cnt.add(cnt, fill_value=0)
                if "vl_subsidio" in dia.columns and "operadora" in dia.columns: #contando subsidio por operadora 
                    sub = dia.groupby("operadora")["vl_subsidio"].sum()
                    subsidio_operadora = subsidio_operadora.add(sub, fill_value=0)
                if all(c in dia.columns for c in ["linha", "vl_linha","vl_trans","pct_subsidio","num_cartao","dia_semana"]): #se dia tem todas essas colunas
                    cnt = dia["linha"].value_counts()
                    linha_cnt = linha_cnt.add(cnt, fill_value=0) #contando transacoes por linha 
                    for linha, grp in dia.groupby("linha"):#construcao de resumo por linha
                        transacoes[linha] += len(grp)

                        vl_linha_sum[linha] += grp["vl_linha"].sum()
                        vl_linha_count[linha] += grp["vl_linha"].notna().sum()

                        vl_trans_sum[linha] += grp["vl_trans"].sum()
                        vl_trans_count[linha] += grp["vl_trans"].notna().sum()

                        subsidio_total[linha] += grp["vl_subsidio"].sum()

                        pct_sum[linha] += grp["pct_subsidio"].sum()
                        pct_count[linha] += grp["pct_subsidio"].notna().sum()

                        cartoes_unicos[linha].update(grp["num_cartao"].dropna()) 
                        carros_unicos[linha].update(grp["num_carro"].dropna()) #mantem unicos porque set descarta duplicados

                        ordem_dias = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                        nomes_pt   = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]
                        map_dias   = dict(zip(ordem_dias, nomes_pt)) #apenas p abreviar dias de semana
                        cnt=grp["dia_semana"].map(map_dias).value_counts().reindex(nomes_pt,fill_value=0) #quantas transacoes por dia de semana
                        dia_semana_cnt=dia_semana_cnt.add(cnt,fill_value=0)
                        for dia_sem, n in cnt.items():
                            dia_semana_por_linha[linha][dia_sem] += n
                if "sindicato" in dia.columns: #transacoes por sindicato
                    cnt = dia["sindicato"].value_counts()
                    sindicato_cnt = sindicato_cnt.add(cnt, fill_value=0)

    valores = { #manter num dict p economizar ficar mais legivel
    "operadora": operadora_cnt,
    "linha": linha_cnt,
    "sindicato": sindicato_cnt,
    "subsidio": subsidio_operadora
    }
    for ax, (col, label, cor) in zip(axes, [
        ("operadora", "Operadora", "steelblue"),
        ("linha",     "Linha",     "mediumseagreen"),
        ("sindicato", "Sindicato", "coral"),
    ]):
        top_bar(valores[col], f"Top 15 — {label} (nº transações)","Nº Transações", ax, color=cor)

    plt.suptitle("Ranking por Entidade", fontweight="bold")
    plt.tight_layout()
    plt.savefig(out / "04_ranking_entidades.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Subsídio total por operadora
    sub_op = valores["subsidio"].nlargest(15)
    fig, ax = plt.subplots(figsize=(10, 6))
    top_bar(sub_op, "Top 15 Operadoras — Subsídio Total (R$)", "R$", ax, color="darkorange")
    plt.tight_layout()
    plt.savefig(out / "04b_subsidio_por_operadora.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Exportar tabela resumo por linha
    linhas = transacoes.keys()

    resumo_linha = pd.DataFrame({
        "transacoes": [transacoes[l] for l in linhas],
        "linha": list(linhas),
        "cartoes_unicos": [len(cartoes_unicos[l]) for l in linhas],
        "carros_unicos":[len(carros_unicos[l])for l in linhas],
        "vl_linha_medio": [
            vl_linha_sum[l] / vl_linha_count[l]
            if vl_linha_count[l] else np.nan
            for l in linhas
        ],
        "vl_trans_medio": [
            vl_trans_sum[l] / vl_trans_count[l]
            if vl_trans_count[l] else np.nan
            for l in linhas
        ],
        "vl_subsidio_total": [
            subsidio_total[l]
            for l in linhas
        ],
        "pct_subsidio_medio": [
            pct_sum[l] / pct_count[l]
            if pct_count[l] else np.nan
            for l in linhas
        ]
    })
    for dia in ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]:
        resumo_linha[dia] = [
            dia_semana_por_linha[l].get(dia, 0)
            for l in linhas
        ] #atualiza transacoes por dia de semana para cada linha
    resumo_linha = (resumo_linha.sort_values("transacoes", ascending=False).round(2))
    print(resumo_linha.columns.tolist())     
    resumo_linha.to_csv(out / "04c_resumo_por_linha.csv",index=False)
    print(f"  Resumo por linha exportado ({len(resumo_linha)} linhas).")



# ════════════════════════════════════════════════════════════════════════════
# 6. ANÁLISE DE SENTIDO E INTEGRAÇÕES
# ════════════════════════════════════════════════════════════════════════════

def secao_sentido_integracoes(out: Path):
    print("[5/7] Sentido e Integrações")

    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE_WIDE)
    cols_in_use={
        "Sentido":                 "sentido",
        "sentido_label":       "sentido_label",
        "Qtde Integrações":   "qtde_integracoes",
        "Vl Linha":                "vl_linha",
        "Vl Subsídio":             "vl_subsidio",
    }
    subsidio_sum = pd.Series(dtype=float)
    subsidio_count = pd.Series(dtype=np.int64)
    sentido_cnt=pd.Series(dtype=np.int64)
    integracoes_cnt=pd.Series(dtype=np.int64)

    for pasta in TIPOS: #extrai apenas essas colunas de cada arquivo do mes, a ser usado pela analise temporal
        with os.scandir(pasta) as files:
            for file in files:
                dia = load_data_spec(file.path,cols_in_use,pasta[-2:],";") #pasta [-2:] indica do tipo da entrada,definida no diretorio
                dia=dia[dia["data_transacao"].dt.month == 8]
                if "sentido_label" in dia.columns:
                    cnt = dia["sentido_label"].value_counts()
                    sentido_cnt = sentido_cnt.add(cnt, fill_value=0)
                if "qtde_integracoes" in dia.columns:
                    cnt=dia["qtde_integracoes"].value_counts().sort_index()
                    integracoes_cnt=integracoes_cnt.add(cnt, fill_value=0)
                if "qtde_integracoes" in dia.columns and "vl_subsidio" in dia.columns: #so entra se dia tem todas essas colunas
                    dia["tem_integracao"] = (dia["qtde_integracoes"] > 0).map({True:"Com integração", False:"Sem integração"})
                    
                    grp_sum = dia.groupby("tem_integracao")["vl_subsidio"].sum()
                    grp_count = dia.groupby("tem_integracao")["vl_subsidio"].count()
                    subsidio_sum = subsidio_sum.add(grp_sum, fill_value=0)
                    subsidio_count = subsidio_count.add(grp_count, fill_value=0)

    subsidio_medio = subsidio_sum / subsidio_count
    print(sentido_cnt)
    print(sentido_cnt.sum())
    axes[0].pie(sentido_cnt.values, labels=sentido_cnt.index, autopct="%1.1f%%",
                startangle=90, colors=sns.color_palette("pastel"))
    axes[0].set_title("Distribuição por Sentido")

    axes[1].bar(integracoes_cnt.index.astype(str), integracoes_cnt.values, color="mediumpurple", alpha=0.85)
    axes[1].set_title("Quantidade de Integrações")
    axes[1].set_xlabel("Nº de Integrações")
    axes[1].set_ylabel("Frequência")

    plt.tight_layout()
    plt.savefig(out / "05_sentido_integracoes.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Subsídio médio com e sem integração
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(
        subsidio_medio.index,
        subsidio_medio.values
    )
    ax.set_title("Subsídio Médio — Com vs Sem Integração")
    ax.set_xlabel("")
    ax.set_ylabel("Subsídio Médio (R$)")
    plt.tight_layout()
    plt.savefig(out / "05b_subsidio_integracao.png", dpi=150, bbox_inches="tight")
    plt.close()


# ════════════════════════════════════════════════════════════════════════════
# 7. CORRELAÇÕES E MAPA DE CALOR
# ════════════════════════════════════════════════════════════════════════════

def secao_correlacoes(df: pd.DataFrame, out: Path):
    print("[6/7] Correlações")

    num_cols = ["vl_linha","vl_trans","vl_subsidio","pct_subsidio","qtde_integracoes","hora","sentido"]
    available = [c for c in num_cols if c in df.columns]
    corr = df[available].corr(numeric_only=True)

    fig, ax = plt.subplots(figsize=FIGSIZE_SQ)
    mask = np.triu(np.ones_like(corr, dtype=bool))
    sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="coolwarm",
                center=0, linewidths=0.5, ax=ax)
    ax.set_title("Mapa de Correlações — Variáveis Numéricas", fontweight="bold")
    plt.tight_layout()
    plt.savefig(out / "06_mapa_correlacoes.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Scatter: vl_linha vs vl_trans colorido por tipo de aplicação
    if "vl_linha" in df.columns and "vl_trans" in df.columns and "tipo_aplicacao" in df.columns:
        fig, ax = plt.subplots(figsize=FIGSIZE_SQ)
        tipos = df["tipo_aplicacao"].dropna().unique()
        palette = sns.color_palette("tab10", len(tipos))
        for tipo, cor in zip(tipos, palette):
            sub = df[df["tipo_aplicacao"] == tipo]
            ax.scatter(sub["vl_linha"], sub["vl_trans"], label=f"Aplicação {tipo}",
                       alpha=0.5, s=25, color=cor)
        ax.set_xlabel("Vl Linha (tarifa cheia, R$)")
        ax.set_ylabel("Vl Trans (cobrado no cartão, R$)")
        ax.set_title("Tarifa Cheia vs. Valor Cobrado por Tipo de Aplicação")
        ax.legend(fontsize=8)
        plt.tight_layout()
        plt.savefig(out / "06b_scatter_vl_linha_trans.png", dpi=150, bbox_inches="tight")
        plt.close()


# ════════════════════════════════════════════════════════════════════════════
# 8. DETECÇÃO DE ANOMALIAS (Isolation Forest)
# ════════════════════════════════════════════════════════════════════════════

def secao_anomalias(df: pd.DataFrame, out: Path):
    print("[7/7] Detecção de Anomalias (Isolation Forest)")

    feature_cols = ["vl_linha","vl_trans","vl_subsidio","pct_subsidio","qtde_integracoes","hora"]
    available = [c for c in feature_cols if c in df.columns]

    df_feat = df[available].dropna()
    if len(df_feat) < 20:
        print("  Dados insuficientes para detecção de anomalias.")
        return

    iso = IsolationForest(n_estimators=100, contamination=0.03, random_state=42)
    labels = iso.fit_predict(df_feat)
    scores = iso.decision_function(df_feat)

    df.loc[df_feat.index, "anomalia"]    = (labels == -1).astype(int)
    df.loc[df_feat.index, "anomaly_score"] = scores

    n_anom = int(df["anomalia"].sum())
    print(f"  Transações sinalizadas como anômalas: {n_anom} ({n_anom/len(df)*100:.1f}%)")

    # Exportar anomalias para revisão
    anom_df = df[df["anomalia"] == 1].copy()
    arquivo=Path(out/"07_transacoes_anomalas.csv")
    if arquivo.is_file():
        anom_df.to_csv(out / "07_transacoes_anomalas.csv",mode="a",header=False, index=False)
    else:
        anom_df.to_csv(out / "07_transacoes_anomalas.csv",mode="a",header=True, index=False)
    print(f"  Transações anômalas exportadas em: 07_transacoes_anomalas.csv")

def anomalias_aux(out:Path):
    #faz anomalias para cada arquivo individualmente, depois exporta pra csv compartilhado
    with os.scandir("agosto\\BU") as files:
        for file in files:
            cols_in_use=pega_dict("BU")
            dia = load_data_spec(file.path,cols_in_use,"BU", ";") 
            secao_anomalias(dia,out)



# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    start_time = time.perf_counter()
    parser = argparse.ArgumentParser(
        description="EDA — Bilhete Único Intermunicipal (BUI)"
    )
    parser.add_argument("--input",  default="TRANSACAO_BE_PUBLICO_2025_08_17.csv", help="Caminho do arquivo de dados (.txt/.csv)")
    parser.add_argument("--tipo", default="BE", help="Tipo do arquivo(GT,BU OU BE)")
    parser.add_argument("--sep",    default=";",   help="Delimitador (padrão: ';')")
    parser.add_argument("--output", default="relatorio_eda_BUI_reuniao7", help="Pasta de saída")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    cols_use=pega_dict(args.tipo)
    df = load_data_spec(args.input, cols_use=cols_use,tipo=args.tipo,sep=args.sep)

    # secao_visao_geral(df, out)
    # secao_valores(out)
    secao_temporal(out)
    # secao_entidades(out)
    # secao_sentido_integracoes(out)
    # secao_correlacoes(df, out)
    # anomalias_aux(out)

    print(f"\n{'═'*60}")
    print(f"  EDA concluída. Outputs salvos em: {out.resolve()}")
    print(f"{'═'*60}\n")

    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"Execution time: {execution_time:.6f} seconds")


if __name__ == "__main__":
    main()
