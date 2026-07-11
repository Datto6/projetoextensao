

import pandas as pd
import plotly.graph_objects as go
import os
from constants import *
import time
import argparse
from pathlib import Path
# ==========================================
# 1. Configuração dos Sindicatos (De-Para)
# ==========================================
SINDICATOS_ONIBUS = ['RIO ÔNIBUS', 'TRANSONIBUS', 'SETRANSDUC', 'SETRERJ']
TIPO="BU"
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
                df[col] = pd.to_datetime(df[col], dayfirst=False, errors="coerce")
            if "data_ordem" in df.columns:
                df["data_ordem"]=pd.to_datetime(df["data_ordem"], dayfirst=False, errors="coerce")
    return df

# ==========================================
# 2. Processamento e Lógica de Múltiplos Estágios
# ==========================================

def processar_sankey_por_colunas(caminho_arquivo:Path):
    # [ATUALIZADO] Utilizando o array exato de colunas solicitado
    cols_in_use=[
        "hora",
        "data_dia",
        "data_transacao",
        "sindicato",
        "cartao_hash",
        "qtde_integracoes",
    ]#colunas p ler
    agregados = []
    with os.scandir(input) as files:
        for file in files:

            for dia in load_data_spec(file.path,cols_in_use,TIPO,",",chunksize=100_000):
                dia=date_formatter(dia,TIPO)
                dia=dia[dia["data_transacao"].between('2026-01-01','2026-08-08')] #filtra so na janela de 2026
                if dia.empty:
                    continue
                if "sindicato" in dia.columns:
                    dia.rename(columns={"sindicato":"modal"},inplace=True)
                    dia["modal"]=dia["modal"].map(MAP_MODAL)
                dia = dia.sort_values(by=["cartao_hash", "data_transacao"])
                
                # Criar colunas de histórico deslocadas (Shift) para analisar a transição na mesma linha
                g = dia.groupby("cartao_hash")

                dia["prev_time"] = g["data_transacao"].shift()
                dia["modal_Ant"] = g["modal"].shift()
                dia["integ_Ant"] = g["qtde_integracoes"].shift()

                mask = (
                    dia["prev_time"].notna()
                    & ((dia["data_transacao"] - dia["prev_time"])
                        <= pd.Timedelta(hours=3))
                )

                df_int = dia.loc[mask]
                agregado=df_int.groupby(['modal_Ant', 'integ_Ant','qtde_integracoes','modal']).size().reset_index(name='Qtd')
                #agrega os grupos iguais do dia
                agregados.append(agregado)

                # if len(agregados) >= 50:
                #     temp = pd.concat(agregados)

                #     temp = (
                #         temp.groupby(
                #             ['modal_Ant','integ_Ant','qtde_integracoes','modal'],
                #             as_index=False
                #         )["Qtd"]
                #         .sum()
                #     )
                #     agregados = [temp]


    dias_agg = pd.concat(agregados, ignore_index=True)

    dias_agg = (dias_agg.groupby(['modal_Ant','integ_Ant','qtde_integracoes','modal'],
        as_index=False)
        ["Qtd"].sum()
        )#reduz grupos duplicados para reduzir uso de memoria

        
    print("3/4. Executando agrupamento de performance para Big Data...")
    # Agrupa milhões de registros em combinações únicas antes de rodar a lógica estrutural
    
    lista_transicoes_finais = []
    
    print("4/4. Reconstruindo cadeias sequenciais e tratando saltos...")
    for _, row in dias_agg.iterrows():
        qtd = row['Qtd']
        int_ant = int(row['integ_Ant'])
        int_atual = int(row['qtde_integracoes'])
        
        cat_ant = row['modal_Ant']
        cat_atual = row['modal']
        
        # CASO A: Fluxo perfeito por colunas consecutivas (Ex: 0 -> 1, ou 1 -> 2)
        if int_atual == int_ant + 1:
            lista_transicoes_finais.append({
                'Origem': f"{cat_ant} ({int_ant})",
                'Destino': f"{cat_atual} ({int_atual})",
                'Quantidade': qtd
            })
            
        # CASO B: Cenário de saltos na integração (Ex: passou de 0 direto para 2)
        elif int_atual > int_ant + 1:
            # Primeira perna: Da origem conhecida para o primeiro "Não Identificado"
            lista_transicoes_finais.append({
                'Origem': f"{cat_ant} ({int_ant})",
                'Destino': f"Não Identificado ({int_ant + 1})",
                'Quantidade': qtd
            })
            
            # Pernas intermediárias caso haja saltos múltiplos (Ex: pulou de 0 para 3)
            for etapa_vazia in range(int_ant + 1, int_atual - 1):
                lista_transicoes_finais.append({
                    'Origem': f"Não Identificado ({etapa_vazia})",
                    'Destino': f"Não Identificado ({etapa_vazia + 1})",
                    'Quantidade': qtd
                })
                
            # Última perna: Do "Não Identificado" anterior para o destino final conhecido
            lista_transicoes_finais.append({
                'Origem': f"Não Identificado ({int_atual - 1})",
                'Destino': f"{cat_atual} ({int_atual})",
                'Quantidade': qtd
            })

    # Consolidação do dataframe final de fluxos
    df_final = pd.DataFrame(lista_transicoes_finais)
    df_final = df_final.groupby(['Origem', 'Destino'])['Quantidade'].sum().reset_index()
    
    # Criar a coluna estruturada com "->" requisitada para o CSV
    df_final['Fluxo'] = df_final['Origem'] + ' -> ' + df_final['Destino']
    
    return df_final[['Fluxo', 'Origem', 'Destino', 'Quantidade']]

import re

# ==========================================
# 3. Geração do Gráfico e Exportação (Atualizado com X/Y Fixos)
# ==========================================
def plotar_sankey_estruturado(df_final:pd.DataFrame, caminho_saida_csv:Path,sep:str=","):
    # Salvar em CSV estruturado por ponto e vírgula
    df_final.to_csv(caminho_saida_csv, index=False, sep=',')
    print(f"\n[SUCESSO] Base de fluxo exportada para: {caminho_saida_csv}")
    
    # Mapeamento numérico de nós exigido pelo Plotly
    todos_os_nos = list(pd.unique(df_final[['Origem', 'Destino']].values.ravel('K')))
    mapa_nos = {nome: i for i, nome in enumerate(todos_os_nos)}
    
    origens_idx = df_final['Origem'].map(mapa_nos)
    destinos_idx = df_final['Destino'].map(mapa_nos)
    valores = df_final['Quantidade']
    
    # ---------------------------------------------------------
    # NOVA LÓGICA: Posicionamento Manual (Eixos X e Y)
    # ---------------------------------------------------------
    
    # 1. Calcular volume global por categoria para ordenar (Maior volume no topo)
    volume_categoria = {}
    for _, row in df_final.iterrows():
        # Extrai o nome da categoria ignorando o número, ex: "Ônibus (0)" -> "Ônibus"
        cat_orig = row['Origem'].rsplit(' (', 1)[0]
        cat_dest = row['Destino'].rsplit(' (', 1)[0]
        
        volume_categoria[cat_orig] = volume_categoria.get(cat_orig, 0) + row['Quantidade']
        volume_categoria[cat_dest] = volume_categoria.get(cat_dest, 0) + row['Quantidade']
        
    # Ordenar categorias (maior para o menor)
    categorias_ordenadas = sorted(volume_categoria.keys(), key=lambda k: volume_categoria[k], reverse=True)
    
    # 2. Atribuir uma posição Y fixa para cada categoria (de 0.01 a 0.99)
    num_cats = len(categorias_ordenadas)
    # Proteção de divisão por zero caso haja apenas 1 modal
    divisor_y = max(1, num_cats - 1) 
    mapa_y = {cat: 0.01 + (0.98 * i / divisor_y) for i, cat in enumerate(categorias_ordenadas)}
    
    # 3. Descobrir a integração máxima para espaçar as colunas X
    max_step = 0
    for no in todos_os_nos:
        match = re.search(r'\((\d+)\)', no)
        if match:
            max_step = max(max_step, int(match.group(1)))
            
    # 4. Construir as coordenadas X e Y na ordem exata de 'todos_os_nos'
    x_coords = []
    y_coords = []
    
    for no in todos_os_nos:
        cat = no.rsplit(' (', 1)[0]
        match = re.search(r'\((\d+)\)', no)
        step = int(match.group(1)) if match else 0
        
        # X: O estágio 0 fica à esquerda (0.01), o último estágio fica à direita (0.99)
        x_val = 0.01 + (0.98 * step / max(1, max_step))
        
        # Y: Busca a altura fixa mapeada para este modal específico
        y_val = mapa_y[cat]
        
        x_coords.append(x_val)
        y_coords.append(y_val)
        
    # ---------------------------------------------------------
    
    # Plotagem com as posições travadas
    fig = go.Figure(data=[go.Sankey(
        arrangement = "snap", # Diz ao Plotly para respeitar as coordenadas o máximo possível
        node = dict(
          pad = 18,
          thickness = 25,
          line = dict(color = "black", width = 0.5),
          label = todos_os_nos,
          x = x_coords,  # Injetando as colunas
          y = y_coords   # Injetando o alinhamento horizontal
        ),
        link = dict(
          source = origens_idx,
          target = destinos_idx,
          value = valores,
          color = "rgba(180, 180, 180, 0.4)" # Linhas cinzas semitransparentes dão destaque aos nós
        )
    )])

    fig.update_layout(
        title_text="Fluxo de Integração (Ordenado por Volume de Modal)",
        font_size=12,
        height=800 # Aumentar a altura ajuda a afastar os nós se o volume de transações for maciço
    )
    fig.show()

# ==========================================
# Execução Principal
# ==========================================
if __name__ == "__main__":
    start_time = time.perf_counter()
    parser = argparse.ArgumentParser(
        description="EDA — Bilhete Único Intermunicipal (BUI)"
    )
    parser.add_argument("--input",  required=True, help="Caminho do diretorio de arquivos separados por mes e ja processados")
    parser.add_argument("--sep",    default=",",   help="Delimitador (padrão: ',')")
    parser.add_argument("--tipo", default=TIPO, help="Tipo do arquivo(GT,BU OU BE)")
    parser.add_argument("--output", required=True, help="Nome do arquivo de saida")
    args = parser.parse_args()

    out = Path(args.output)
    input=Path(args.input)
    cols_use=pega_dict(args.tipo)

    df_resultado = processar_sankey_por_colunas(input)
    plotar_sankey_estruturado(df_resultado, out)

    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"Execution time: {execution_time:.6f} seconds")
    print(f"\n{'═'*60}")
    print(f"  EDA concluída. Outputs salvos em: {out.resolve()}")
    print(f"{'═'*60}\n")
