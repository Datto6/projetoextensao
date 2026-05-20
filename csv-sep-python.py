import os 
from pathlib import Path
import pandas as pd
from collections import defaultdict

pathBE = Path("org-BE")
pathBE.mkdir(exist_ok=True)

pathGT = Path("org-GT")
pathGT.mkdir(exist_ok=True)

pathBU = Path("org-BU")
pathBU.mkdir(exist_ok=True) #cria diretorios

paths=[pathBE,pathGT,pathBU]
def separate(files, type,indexes):
    grouped = {}

    for file in files:
        if type=='GT':
            df = pd.read_csv(file.path, sep=';',dtype={"Escola": str, "Nº Censo Escola": str}) #tipagem esquisita no GT
        else:
            df = pd.read_csv(file.path, sep=';')

        date_col=df.columns[indexes[0]] #transformando data de processamento

        df["Hora Transação"]=pd.to_datetime(df[date_col],dayfirst=True).dt.hour #salvando hora da transacao
        df[date_col] = pd.to_datetime(df[date_col],dayfirst=True).dt.date #salvando dia de transacao

        outra_col=df.columns[indexes[1]] #transformando data de transacao
        df[outra_col] = pd.to_datetime(df[outra_col],dayfirst=True).dt.date

        if type=='BU':
            outra_col = "Data da Ordem" #desgraca de mudanca de padrao do BU

            converted = pd.to_datetime(df[outra_col],dayfirst=False,errors='coerce')

            # bad_values = df.loc[converted.isna(), date_col].unique() tava dando erro porque dayfirst era falso
            # print(bad_values)

        for date, group in df.groupby(date_col): #agrupa pela coluna de transacao
            key = f"{date}_{type}"
            if key in grouped: #checa se ta no agrupado, se ja ta, appenda
                grouped[key].append(group)
            else:
                grouped[key] = [group]

    return {
        k: pd.concat(v, ignore_index=True) #v eh uma lista de dataframes, ent ele concatena tudo
        for k, v in grouped.items()
    }
items=['BE','GT','BU'] 
for i in range(len(items)): #apenas para nao repetir o mesmo codigo 3 vezes, comecando a partir do 1 pq ja tinha testado
    with os.scandir(items[i]) as files:
        columns=input(f"De a primeira linha do arquivo de {items[i]}").split(";") #split ; pq ta assim no arquivo
        date_indexes=[-1]
        for j in range(len(columns)):
            if columns[j].startswith("Data"):
                if columns[j].endswith("Transação"): #loop para achar coluna de transacao e data de processamento
                    date_indexes[0]=j
                else:
                    date_indexes.append(j)

        dataframes_i = separate(files, items[i],date_indexes)

    for date, dataframe in dataframes_i.items():
        output_file = paths[i] / f"{date}.csv" #apenas mostrando quais arquivos feitos
        print(output_file)

        dataframe.to_csv(output_file, index=False) #escreve arquivo
