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

import argparse
import os
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")

# ── Estilo global ────────────────────────────────────────────────────────────
sns.set_theme(style="whitegrid", palette="muted", font_scale=1.05)
FIGSIZE_WIDE = (14, 5)
FIGSIZE_SQ   = (10, 7)
FIGSIZE_TALL = (12, 8)

COLUNAS_PT = {
    "Nº Cartão":               "num_cartao",
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
    "Nº Ordem":                "num_ordem", #campos particulares de BE e GT a partir dessa linha, nao da erro ao usar para BUI ou outros
    "Transações":               "transacoes", 
    "Escola":                  "escola",
    "Nº Censo Escola":          "num_escola",
}
DIAS_ANALISE=[list(range(1,32))] #lista de dias do mes de agosto 
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


def load_data(path: str, sep: str = ";") -> pd.DataFrame:
    print(f"\n{'─'*60}")
    print(f"  Carregando: {path}")
    print(f"{'─'*60}")

    df = pd.read_csv(path, sep=sep, encoding="utf-8-sig", dtype=str)

    # Normalizar nomes de colunas (strip de espaços)
    df.columns = df.columns.str.strip()
    df.rename(columns=COLUNAS_PT, inplace=True)

    # Datas
    for col in ["data_transacao", "data_processamento", "data_ordem"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")

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

def secao_valores(df: pd.DataFrame, out: Path):
    print("[2/7] Distribuições de Valores")

    fig, axes = plt.subplots(1, 3, figsize=FIGSIZE_WIDE)
    cols_val = [("vl_linha", "Vl Linha (R$)"),
                ("vl_trans", "Vl Trans (R$)"),
                ("vl_subsidio", "Vl Subsídio (R$)")]
    
    valores = { #quero so olhar essas colunas, so que considerando todos os arquivos do mes
    "vl_linha": [],
    "vl_trans": [],
    "vl_subsidio": []
    }
    for pasta in TIPOS:
        with os.scandir(pasta) as files:
            for file in files:
                dia = load_data(file.path, ";")
                for col in valores:
                    if col in dia.columns:
                        valores[col].append(dia[col].dropna()) #itera sobre todos os arquivos de agosto, adiciona apenas essas colunas

    for ax, (col, label) in zip(axes, cols_val):
        serie = pd.concat(valores[col], ignore_index=True) #junta todas as series achadas dessa coluna em uma linha para gerar histograma da coluna tal
        sns.histplot(serie, kde=False, ax=ax, color="steelblue", bins=30)
        ax.set_title(label)
        ax.set_xlabel("R$")
        ax.set_ylabel("Frequência")
        ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))

    plt.suptitle("Distribuição dos Valores Monetários", fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(out / "02_distribuicao_valores.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Boxplots por tipo de aplicação
    if "tipo_aplicacao" in df.columns and "vl_subsidio" in df.columns:
        fig, ax = plt.subplots(figsize=FIGSIZE_WIDE)
        ordem = df.groupby("tipo_aplicacao")["vl_subsidio"].median().sort_values(ascending=False).index
        sns.boxplot(data=df, x="tipo_aplicacao", y="vl_subsidio", order=ordem, ax=ax, palette="pastel")
        ax.set_title("Distribuição do Subsídio por Tipo de Aplicação")
        ax.set_xlabel("Tipo de Aplicação")
        ax.set_ylabel("Vl Subsídio (R$)")
        plt.tight_layout()
        plt.savefig(out / "02b_subsidio_por_aplicacao_boxplot.png", dpi=150, bbox_inches="tight")
        plt.close()

    # Percentual de subsídio
    if "pct_subsidio" in df.columns:
        fig, ax = plt.subplots(figsize=(8, 4))
        sns.histplot(df["pct_subsidio"].dropna().clip(0, 100), bins=40, kde=False, ax=ax, color="coral")
        ax.set_title("Distribuição do Percentual de Subsídio (% do Vl Linha)")
        ax.set_xlabel("% Subsídio")
        ax.set_ylabel("Frequência")
        plt.tight_layout()
        plt.savefig(out / "02c_pct_subsidio.png", dpi=150, bbox_inches="tight")
        plt.close()


# ════════════════════════════════════════════════════════════════════════════
# 4. ANÁLISE TEMPORAL
# ════════════════════════════════════════════════════════════════════════════

def secao_temporal(df: pd.DataFrame, out: Path):
    print("[3/7] Análise Temporal")

    diarios = []
    horas = []
    dias_semana = []
    diarios = []
    latencias = []
    
    for pasta in TIPOS: #extrai apenas essas colunas de cada arquivo do mes, a ser usado pela analise temporal
        with os.scandir(pasta) as files:
            for file in files:
                dia = load_data(file.path, ";")
                if "hora" in dia:
                    horas.append(dia["hora"].dropna())

                if "dia_semana" in dia:
                    dias_semana.append(dia["dia_semana"].dropna())

                if all(c in dia.columns for c in ["data_dia", "num_cartao", "vl_subsidio"]): #so entra se dia tem todas essas colunas
                    diarios.append(dia[["data_dia", "num_cartao", "vl_subsidio"]])

                if all(c in dia.columns for c in ["data_transacao", "data_processamento"]): #idem
                    latencias.append(dia[["data_transacao", "data_processamento"]])

    # Transações por hora do dia
    if "hora" in df.columns:
        fig, axes = plt.subplots(1, 2, figsize=FIGSIZE_WIDE)

        hora = pd.concat(horas, ignore_index=True) #uma unica coluna com todas as horas do mes
        hora_cnt = hora.value_counts().sort_index()
        axes[0].bar(hora_cnt.index, hora_cnt.values, color="steelblue", alpha=0.8)
        axes[0].set_title("Transações por Hora do Dia")
        axes[0].set_xlabel("Hora")
        axes[0].set_ylabel("Nº de Transações")
        axes[0].set_xticks(range(0, 24))

        # Subsídio médio por hora
        if "vl_subsidio" in df.columns:
            hora_sub = df.groupby("hora")["vl_subsidio"].mean()
            axes[1].plot(hora_sub.index, hora_sub.values, marker="o", color="coral")
            axes[1].set_title("Subsídio Médio por Hora do Dia")
            axes[1].set_xlabel("Hora")
            axes[1].set_ylabel("Subsídio Médio (R$)")
            axes[1].set_xticks(range(0, 24))

        plt.suptitle("Padrão Temporal das Transações", fontweight="bold")
        plt.tight_layout()
        plt.savefig(out / "03_analise_temporal_hora.png", dpi=150, bbox_inches="tight")
        plt.close()

    # Transações por dia da semana
    if "dia_semana" in df.columns:
        ordem_dias = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        nomes_pt   = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]
        map_dias   = dict(zip(ordem_dias, nomes_pt)) #apenas p abreviar dias de semana

        dia_semana = pd.concat(dias_semana, ignore_index=True) #junta a coluna dia_semana do mes todo
        dia_cnt = dia_semana.map(map_dias).value_counts().reindex(nomes_pt) 

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(dia_cnt.index, dia_cnt.values, color="mediumseagreen", alpha=0.85)
        ax.set_title("Transações por Dia da Semana")
        ax.set_xlabel("Dia")
        ax.set_ylabel("Nº de Transações")
        plt.tight_layout()
        plt.savefig(out / "03b_transacoes_dia_semana.png", dpi=150, bbox_inches="tight")
        plt.close()

    # Série diária (se houver mais de 1 dia)
    if "data_dia" in df.columns and df["data_dia"].nunique() > 1:
        df_diario=pd.concat(diarios,ignore_index=True)

        diario = df_diario.groupby("data_dia").agg(
            transacoes=("num_cartao","count"),
            subsidio_total=("vl_subsidio","sum")
        ).reset_index()

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
    if "data_transacao" in df.columns and "data_processamento" in df.columns:
        lat_df = pd.concat(latencias, ignore_index=True)
        lat_df["latencia_h"] = (lat_df["data_processamento"] - lat_df["data_transacao"]).dt.total_seconds() / 3600
        lat = lat_df["latencia_h"].dropna()
        lat_pos = lat[lat >= 0]

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


def secao_entidades(df: pd.DataFrame, out: Path):
    print("[4/7] Análise por Entidade")

    fig, axes = plt.subplots(1, 3, figsize=(18, 7))

    for ax, (col, label, cor) in zip(axes, [
        ("operadora", "Operadora", "steelblue"),
        ("linha",     "Linha",     "mediumseagreen"),
        ("sindicato", "Sindicato", "coral"),
    ]):
        if col in df.columns:
            top_bar(df[col].value_counts(), f"Top 15 — {label} (nº transações)",
                    "Nº Transações", ax, color=cor)

    plt.suptitle("Ranking por Entidade", fontweight="bold")
    plt.tight_layout()
    plt.savefig(out / "04_ranking_entidades.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Subsídio total por operadora
    if "operadora" in df.columns and "vl_subsidio" in df.columns:
        sub_op = df.groupby("operadora")["vl_subsidio"].sum().nlargest(15)
        fig, ax = plt.subplots(figsize=(10, 6))
        top_bar(sub_op, "Top 15 Operadoras — Subsídio Total (R$)", "R$", ax, color="darkorange")
        plt.tight_layout()
        plt.savefig(out / "04b_subsidio_por_operadora.png", dpi=150, bbox_inches="tight")
        plt.close()

    # Exportar tabela resumo por linha
    if "linha" in df.columns:
        resumo_linha = df.groupby("linha").agg(
            transacoes=("num_cartao","count"),
            cartoes_unicos=("num_cartao","nunique"),
            vl_linha_medio=("vl_linha","mean"),
            vl_trans_medio=("vl_trans","mean"),
            vl_subsidio_total=("vl_subsidio","sum"),
            pct_subsidio_medio=("pct_subsidio","mean"),
        ).round(2).sort_values("transacoes", ascending=False)
        resumo_linha.to_csv(out / "04c_resumo_por_linha.csv")
        print(f"  Resumo por linha exportado ({len(resumo_linha)} linhas).")


# ════════════════════════════════════════════════════════════════════════════
# 6. ANÁLISE DE SENTIDO E INTEGRAÇÕES
# ════════════════════════════════════════════════════════════════════════════

def secao_sentido_integracoes(df: pd.DataFrame, out: Path):
    print("[5/7] Sentido e Integrações")

    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE_WIDE)

    if "sentido_label" in df.columns:
        cnt = df["sentido_label"].value_counts()
        axes[0].pie(cnt.values, labels=cnt.index, autopct="%1.1f%%",
                    startangle=90, colors=sns.color_palette("pastel"))
        axes[0].set_title("Distribuição por Sentido")

    if "qtde_integracoes" in df.columns:
        cnt_int = df["qtde_integracoes"].value_counts().sort_index()
        axes[1].bar(cnt_int.index.astype(str), cnt_int.values, color="mediumpurple", alpha=0.85)
        axes[1].set_title("Quantidade de Integrações")
        axes[1].set_xlabel("Nº de Integrações")
        axes[1].set_ylabel("Frequência")

    plt.tight_layout()
    plt.savefig(out / "05_sentido_integracoes.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Subsídio médio com e sem integração
    if "qtde_integracoes" in df.columns and "vl_subsidio" in df.columns:
        df["tem_integracao"] = (df["qtde_integracoes"] > 0).map({True:"Com integração", False:"Sem integração"})
        fig, ax = plt.subplots(figsize=(7, 4))
        sns.barplot(data=df, x="tem_integracao", y="vl_subsidio", estimator=np.mean,
                    ci=95, palette="Set2", ax=ax)
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

    # Scatter anomalias em vl_linha vs vl_subsidio
    if "vl_linha" in df.columns and "vl_subsidio" in df.columns:
        fig, ax = plt.subplots(figsize=FIGSIZE_SQ)
        normal = df[df["anomalia"] == 0]
        anoms  = df[df["anomalia"] == 1]
        ax.scatter(normal["vl_linha"], normal["vl_subsidio"],
                   alpha=0.4, s=20, color="steelblue", label="Normal")
        ax.scatter(anoms["vl_linha"],  anoms["vl_subsidio"],
                   alpha=0.9, s=60, color="red", marker="X", label=f"Anômalo (n={n_anom})")
        ax.set_xlabel("Vl Linha (R$)")
        ax.set_ylabel("Vl Subsídio (R$)")
        ax.set_title("Detecção de Anomalias — Isolation Forest")
        ax.legend()
        plt.tight_layout()
        plt.savefig(out / "07_anomalias_isolation_forest.png", dpi=150, bbox_inches="tight")
        plt.close()

    # Exportar anomalias para revisão
    anom_df = df[df["anomalia"] == 1].copy()
    anom_df.to_csv(out / "07_transacoes_anomalas.csv", index=False)
    print(f"  Transações anômalas exportadas em: 07_transacoes_anomalas.csv")


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="EDA — Bilhete Único Intermunicipal (BUI)"
    )
    parser.add_argument("--input",  required=True, help="Caminho do arquivo de dados (.txt/.csv)")
    parser.add_argument("--sep",    default=";",   help="Delimitador (padrão: ';')")
    parser.add_argument("--output", default="relatorio_eda", help="Pasta de saída")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    df = load_data(args.input, sep=args.sep)

    secao_visao_geral(df, out)
    secao_valores(df, out)
    secao_temporal(df, out)
    secao_entidades(df, out)
    secao_sentido_integracoes(df, out)
    secao_correlacoes(df, out)
    secao_anomalias(df, out)

    print(f"\n{'═'*60}")
    print(f"  EDA concluída. Outputs salvos em: {out.resolve()}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
