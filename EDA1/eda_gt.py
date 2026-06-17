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

warnings.filterwarnings("ignore")

# ── Estilo global ────────────────────────────────────────────────────────────
sns.set_theme(style="whitegrid", palette="muted", font_scale=1.05)
FIGSIZE_WIDE = (14, 5)
FIGSIZE_SQ   = (10, 7)
FIGSIZE_TALL = (12, 8)

COLUNAS_GT={
    "Nº Cartão":               "num_cartao",
    "Descrição da Aplicação":  "descricao_aplicacao",
    "Sindicato":               "sindicato",
    "Operadora":               "operadora",
    "Linha":                   "linha",
    "Nº Carro":                "num_carro",
    "Nº Validador":            "num_validador",
    "Data da Transação":       "data_transacao",
    "Data do Processamento":   "data_processamento",
    "Transações":               "transacoes", 
    "Escola":                  "escola",
    "Nº Censo Escola":          "num_escola",
}
PASTA="agosto\\GT"
TIPO="GT"
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
    if tipo=="GT": return COLUNAS_GT

def load_data(path: str, cols_use:dict,tipo:str, sep: str = ";",) -> pd.DataFrame:
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
        return load_data(path, available_cols,tipo, sep,) #passar elas pro load_data

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

# ════════════════════════════════════════════════════════════════════════════
# 3. ANÁLISE TEMPORAL
# ════════════════════════════════════════════════════════════════════════════

def secao_temporal(out: Path):
    print("[3/7] Análise Temporal")
    hora_cnt = pd.Series(dtype=np.int64)
    diario_trans = {}
    diario_subs = {}
    all_latencies = []
    dia_semana_cnt = pd.Series(dtype=np.int64)
    cols_in_use={
        "Data da Transação":       "data_transacao",
        "Data do Processamento":   "data_processamento",
        "Nº Cartão": "num_cartao",
    }
    with os.scandir(PASTA) as files:
        for file in files:
            dia = load_data_spec(file.path,cols_in_use,TIPO,";") #PASTA [-2:] indica do tipo da entrada,definida no diretorio
            if "hora" in dia.columns:
                cnt = dia["hora"].value_counts()
                hora_cnt = hora_cnt.add(cnt, fill_value=0)

            if "dia_semana" in dia.columns:
                ordem_dias = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                nomes_pt   = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]
                map_dias   = dict(zip(ordem_dias, nomes_pt)) #apenas p abreviar dias de semana
                cnt=dia["dia_semana"].map(map_dias).value_counts().reindex(nomes_pt)
                dia_semana_cnt=dia_semana_cnt.add(cnt,fill_value=0)
            if "data_dia" in dia.columns: #so entra se dia tem todas essas colunas
                grp = dia.groupby("data_dia").agg(transacoes=("data_dia", "size"),)
                for data, row in grp.iterrows():
                    diario_trans[data] = (diario_trans.get(data, 0)+ row["transacoes"])

            if all(c in dia.columns for c in ["data_transacao", "data_processamento"]): #idem
                lat = (dia["data_processamento"]- dia["data_transacao"]).dt.total_seconds() / 3600
                lat = lat[lat >= 0]
                all_latencies.append(lat)
    hora_cnt = hora_cnt.sort_index()

    # Transações por hora do dia
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE_WIDE)
    axes[0].bar(hora_cnt.index, hora_cnt.values, color="steelblue", alpha=0.8)
    axes[0].set_title("Transações por Hora do Dia")
    axes[0].set_xlabel("Hora")
    axes[0].set_ylabel("Nº de Transações")
    axes[0].set_xticks(range(0, 24))


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

    diario = diario.sort_values("data_dia")

    fig, ax1 = plt.subplots(figsize=FIGSIZE_WIDE)
    ax1.bar(diario["data_dia"].astype(str), diario["transacoes"], alpha=0.6, label="Transações")
    ax1.set_xlabel("Data")
    ax1.set_ylabel("Nº Transações")
    ax1.tick_params(axis="x", rotation=45)
    plt.title("Série Diária — Transações")
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
# 4. ANÁLISE POR ENTIDADE (Operadora, Linha, Sindicato, Aplicacao)
# ════════════════════════════════════════════════════════════════════════════

def top_bar(series: pd.Series, title: str, xlabel: str, ax, n=15, color="steelblue"):
    top = series.nlargest(n)
    top.plot.barh(ax=ax, color=color, alpha=0.85)
    ax.invert_yaxis()
    ax.set_title(title)
    ax.set_xlabel(xlabel)


def secao_entidades(out: Path):
    print("[4/7] Análise por Entidade")

    fig, axes = plt.subplots(1, 3, figsize=(18, 7))
    cols_in_use={
        "Operadora":               "operadora",
        "Linha":                   "linha",
        "Sindicato":               "sindicato",
        "Nº Cartão": "num_cartao",
        "Descrição da Aplicação":  "descricao_aplicacao",
        "Data da Transação":       "data_transacao",
    }
    operadora_cnt = pd.Series(dtype=np.int64) #transacoes por operadora
    linha_cnt = pd.Series(dtype=np.int64) #idem
    sindicato_cnt = pd.Series(dtype=np.int64) 
    aplicacao_cnt=pd.Series(dtype=np.int64) 
    dia_semana_cnt=pd.Series(dtype=np.int64) 
    dia_semana_por_linha = defaultdict(lambda: defaultdict(int)) #dicionario com dicionario dentro

    transacoes = defaultdict(int)
    cartoes_unicos = defaultdict(set)# dois atributos para fazer resumo de linha

    with os.scandir(PASTA) as files:
        for file in files:
            dia = load_data_spec(file.path,cols_in_use,TIPO, ";") #pegar tipo de arquivo como ultimos 2 chars da PASTA(PASTA ta agosto/BU agosto/BE etc)
            if "operadora" in dia.columns: #transacoes por operadora 
                cnt = dia["operadora"].value_counts()
                operadora_cnt = operadora_cnt.add(cnt, fill_value=0)
            if all(c in dia.columns for c in ["linha","num_cartao","dia_semana"]): #se dia tem todas essas colunas
                cnt = dia["linha"].value_counts()
                linha_cnt = linha_cnt.add(cnt, fill_value=0) #contando transacoes por linha 
                for linha, grp in dia.groupby("linha"): #construcao de resumo por linha
                    transacoes[linha] += len(grp)
                    cartoes_unicos[linha].update(grp["num_cartao"].dropna())

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
            if "tipo_aplicacao" in dia.columns:
                cnt=dia["tipo_aplicacao"].value_counts()
                aplicacao_cnt=aplicacao_cnt.add(cnt,fill_value=0)

    valores = { #manter num dict p economizar ficar mais legivel
    "operadora": operadora_cnt,
    "linha": linha_cnt,
    "sindicato": sindicato_cnt,
    "aplicacao":aplicacao_cnt
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
    
    
    # Transacoes top 15 aplicacoes
    fig, ax = plt.subplots(figsize=(10, 6))
    top_bar(valores["aplicacao"],f"Top 15 — aplicacao (nº transações)","Nº Transações",ax)
    plt.tight_layout()
    plt.savefig(out / "04b_transacoes_por_aplicacao.png", dpi=150, bbox_inches="tight")
    plt.close()
    # Exportar tabela resumo por linha, so que so GT
    linhas = transacoes.keys()

    resumo_linha = pd.DataFrame({
        "transacoes": [transacoes[l] for l in linhas],
        "linha": list(linhas),
        "cartoes_unicos": [len(cartoes_unicos[l]) for l in linhas],
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
# 7. CORRELAÇÕES E MAPA DE CALOR
# ════════════════════════════════════════════════════════════════════════════

def secao_correlacoes(df: pd.DataFrame, out: Path):
    print("[6/7] Correlações")

    cols_in_use={
        "Sindicato":               "sindicato",
        "hora":                     "hora",
        "Sentido":                 "sentido",
        "Descrição da Aplicação":  "descricao_aplicacao",
        "tipo_aplicacao": "tipo_aplicacao"
    }
    partes_corr=[]
    with os.scandir(PASTA) as files:
        for file in files:
            dia = load_data_spec(file.path,cols_in_use,TIPO,";")
            partes_corr.append(dia)

    corr_df = pd.concat(partes_corr,ignore_index=True)
    corr = corr_df.corr(numeric_only=True)
    fig, ax = plt.subplots(figsize=FIGSIZE_SQ)
    mask = np.triu(np.ones_like(corr, dtype=bool))
    sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="coolwarm",
                center=0, linewidths=0.5, ax=ax)
    ax.set_title("Mapa de Correlações — Variáveis Numéricas", fontweight="bold")
    plt.tight_layout()
    plt.savefig(out / "06_mapa_correlacoes.png", dpi=150, bbox_inches="tight")
    plt.close()



# ════════════════════════════════════════════════════════════════════════════
# 8. DETECÇÃO DE ANOMALIAS (Isolation Forest) --> nao da p GT, sem numericos
# ════════════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    start_time = time.perf_counter()
    parser = argparse.ArgumentParser(
        description="EDA — Bilhete Único Intermunicipal (BUI)"
    )
    parser.add_argument("--input", default="TRANSACAO_BE_PUBLICO_2025_08_17.csv",help="Caminho do arquivo de dados (.txt/.csv)")
    parser.add_argument("--tipo",default="GT", help="Tipo do arquivo(GT,BU OU BE)")
    parser.add_argument("--sep",    default=";",   help="Delimitador (padrão: ';')")
    parser.add_argument("--output", default="relatorio_eda_gt3", help="PASTA de saída")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    cols_use=pega_dict(args.tipo)
    # df = load_data_spec(args.input, cols_use=cols_use,tipo=args.tipo,sep=args.sep)

    # secao_visao_geral(df, out)
    secao_temporal(out)
    secao_entidades(out)
    # secao_correlacoes(df, out)

    print(f"\n{'═'*60}")
    print(f"  EDA concluída. Outputs salvos em: {out.resolve()}")
    print(f"{'═'*60}\n")

    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"Execution time: {execution_time:.6f} seconds")


if __name__ == "__main__":
    main()
