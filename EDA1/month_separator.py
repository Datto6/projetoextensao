import os 
from pathlib import Path
import pandas as pd
from collections import defaultdict
import time 
import argparse
import os

import numpy as np
import pandas as pd
from constants import *

SENTIDO_MAP = {0: "Não informado", 1: "Ida", 2: "Volta"}
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

def load_data(path: str, cols_use:dict, tipo:str, sep: str = ";") -> pd.DataFrame:
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
        return load_data(path, available_cols, tipo, sep) #passar elas pro load_data

    return pd.DataFrame()

def separar(input: str, out: str,tipo:str):
    with os.scandir(input) as files:
        for file in files:
            dia = load_data_spec(file.path,COLUNAS_BE,tipo, ";")
            for month, group in dia.groupby(dia["data_transacao"].dt.month): #agrupa pela coluna de transacao
                key = f"mes_{month}_{tipo}.csv"
                arquivo=Path(out / key)
                if arquivo.is_file():
                    group.to_csv(arquivo,mode="a",header=False, index=False) #modo append, sem o header
                else:
                    group.to_csv(arquivo,mode="w",header=True, index=False) #cria novo arquivo do mes
                print(f"Adicionado ao mes {month}")

def main():
    start_time = time.perf_counter()
    parser = argparse.ArgumentParser(
        description="EDA — Bilhete Único Intermunicipal (BUI)"
    )
    parser.add_argument("--input",  default="BE_2026", help="Caminho do diretorio")
    parser.add_argument("--tipo",default="BE", help="Tipo do arquivo(GT,BU OU BE)")
    parser.add_argument("--sep",    default=";",   help="Delimitador (padrão: ';')")
    parser.add_argument("--output", default="meses_BE_2026", help="Pasta de saída")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    separar(input,out,args.tipo)
    print(f"\n{'═'*60}")
    print(f"  EDA concluída. Outputs salvos em: {out.resolve()}")
    print(f"{'═'*60}\n")

    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"Execution time: {execution_time:.6f} seconds")


if __name__ == "__main__":
    main()
