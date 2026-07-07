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
from constants import *

def load_data_spec(path: str, cols_use:list, tipo:str,sep: str=","):
    #auxiliar de load_data que especifica as colunas a serem lidas, e pula a leitura se nao ha nenhuma coluna em comum, usando o dicionario que ja sabemos que existe
    dicionario_tipo=DTYPES_LINHA.keys()

    available_cols = [ #pegar colunas em comum com cols_use e dicionario do tipo
        col for col in cols_use
        if col in dicionario_tipo
    ]
    dtypes={
        k:v for k,v in DTYPES_LINHA.items()
        if k in available_cols
    }
    if available_cols:
            return pd.read_csv(
            path,
            sep=sep,
            usecols=available_cols, #estamos na parte ja processada
            dtype=dtypes,
        )
    return pd.DataFrame() 
cols_use=[
    "transacoes",
    "linha",
    "cartoes_unicos",
    "carros_unicos",
    "vl_linha_medio",
    "vl_trans_medio",
    "vl_subsidio_total",
    "pct_subsidio_medio",
    "Seg",
    "Ter",
    "Qua",
    "Qui",
    "Sex",
    "Sáb",
    "Dom"
]
def compara_string(s1:str,s2:str):
    dif=0
    for i in range(len(s1)):
        if i<len(s2) and s2[i]!=s1[i]:
            dif+=1
        if dif>=4:
            return False
    return True
df=load_data_spec(path="entidade_sentido_chunks\\04c_resumo_por_linha.csv",cols_use=cols_use,tipo="BU",sep=",")
def merge_linhas(df:pd.DataFrame):
    df["estacao"]=(df["linha"].str.split("-", n=1)
                   .str[1] #segunda parte do split do string
                   .str.lower()
                   .str.strip() # sem letras maiusculas
                   .str.replace(" ", "_", regex=False)) # sem espaco
    
    df["linha"]=(df["linha"].str.split("-", n=1)
                .str[0]
                .str.upper()) # sem letras minusculas
    grouped = df.groupby(df["linha"].str.split("-", n=1).str[0])
    # print(df.head())
    for linha, grupo in grouped:
        if len(grupo)!=1:
            estacoes=grupo["estacao"].tolist()
            # print(grupo["estacao"].head())
            for i in range(len(estacoes)):
                j = len(estacoes) - 1
                while j > i:
                    if compara_string(estacoes[i], estacoes[j]):
                        estacoes[j]=estacoes[i] #padroniza, os dois ficam iguais
                    j-=1
            grupo["estacao"]=estacoes
    
    merged_df=df.groupby('estacao').sum().reset_index()
    merged_df.round(2)
    merged_df=(merged_df.sort_values("transacoes", ascending=False).round(2))
    return merged_df    
                            
        

new_df=merge_linhas(df)
new_df.to_csv("resumo_estacoes.csv",index=False)