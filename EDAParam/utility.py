from constants import *
import pandas as pd
def txt_faltantes(out,data_ini,data_fim,diario,minimo):
    day_range = pd.date_range(start=data_ini, end=data_fim, freq="D")

    # Criar txt de dias vazios, faltantes, e com entrada infimas
    dia_faltante=[]
    dia_vazio=[]
    dia_infimo=[]
    for day in day_range:
        # 'day' eh pandas Timestamp object
        valor=diario.get(day,None)
        if valor is None:
            dia_faltante.append(day.strftime("%d/%m/%Y"))
        if valor==0:
            dia_vazio.append(day.strftime("%d/%m/%Y"))
        elif valor is not None and valor<minimo:
            dia_infimo.append(day.strftime("%d/%m/%Y"))
        
    # Criar txt de dias com problemas
    with open(out / "dias_com_problemas.txt", "w", encoding="utf-8") as f:
        f.write("=== Dias sem registros (não encontrados) ===\n")
        if dia_faltante:
            f.write("\n".join(dia_faltante))
        else:
            f.write("Nenhum")
        f.write("\n\n")

        f.write("=== Dias com 0 transações ===\n")
        if dia_vazio:
            f.write("\n".join(dia_vazio))
        else:
            f.write("Nenhum")
        f.write("\n\n")

        f.write("=== Dias com menos de 5000 transações ===\n")
        if dia_infimo:
            f.write("\n".join(dia_infimo))
        else:
            f.write("Nenhum")
        f.write("\n")