import os
import csv
import sys
from constants import *
def pegar_colunas(TIPO:str, PASTA:str):
    arquivos = [
        f for f in os.listdir(PASTA)
        if f.endswith(".csv")
    ]
    # Read the first line of the first CSV
    primeiro_arquivo = os.path.join(PASTA, arquivos[0])

    with open(primeiro_arquivo, "r", encoding="utf-8") as f:
        primeira_linha = f.readline().strip()

    print("Primeira linha do CSV:")
    print(primeira_linha)

    separador = input("Qual é o separador? ")

    print("Separador escolhido:", separador)
    colunas_comuns = None

    for arquivo in arquivos:
        caminho = os.path.join(PASTA, arquivo)

        with open(caminho, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f,delimiter=separador)
            colunas = set(next(reader))

        if colunas_comuns is None:
            colunas_comuns = colunas
        else:
            colunas_comuns &= colunas

    print("Colunas presentes em todos os arquivos:")
    colunas_map={}
    dict_geral=pega_dict(TIPO)
    colunas_usaveis= {k: dict_geral[k] for k in colunas_comuns if k in dict_geral}
    print(colunas_usaveis)

    return colunas_usaveis
pegar_colunas("BE", "teste/")