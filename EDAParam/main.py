import os,sys,argparse,time
from testecurl import pegar_dados
from pathlib import Path
import re
from datetime import date,timedelta
def is_syntax_valid(filepath: str) -> bool:
    try:
        # resolve() will trigger an OSError if the path syntax contains illegal characters
        Path(filepath).resolve(strict=False)
        return True
    except (OSError, ValueError):
        return False

def tratar(argumentos, arg_esp):
    valor_considerado=getattr(argumentos,arg_esp)
    mapa_correto={
        "data_inicio":"\\d{4}/\\d{2}/\\d{2}",  #formato yyyy/mm/dd
        "data_fim":"\\d{4}/\\d{2}/\\d{2}",
        "sep":";|,", #ou , ou ;
    }
    for key, value in mapa_correto.items():
        if key==arg_esp:
            if re.fullmatch(value,valor_considerado): #Checa se tá no formato certinho,com regex
                return True
            return False
    #Se chegou aqui, o atributo considerado é um path
    #Vamos apenas testar o sintasse, o acesso  e outras coisas vai ser visto depois
    return is_syntax_valid(valor_considerado)

def main():
    start_time=time.perf_counter()
    parser = argparse.ArgumentParser(
        description="Entrada para EDA sobre dados"
    )
    parser.add_argument("--data_inicio",  required=True, help="Data de início(ambas as datas em formato yyyy/mm/dd)")
    parser.add_argument("--data_fim", required=True, help="Data de fim do período considerado")
    parser.add_argument("--sep",    required=True,   help="Delimitador (padrão: ';')")
    parser.add_argument("--output", required=True, help="Pasta de saída do EDA")
    parser.add_argument("--input", required=True, help="Pasta de entrada de dados a serem analisados")
    args = parser.parse_args()

    nomes_args=["data_inicio","data_fim","sep","output","input"]
    for arg in nomes_args:
        if not tratar(args,arg):
            print(f"Argumento {arg} em formato errado, rodar de novo")
            sys.exit()
    tipos=["BE","BU","GRATUIDADE"]
    input=args.input
    ano_ini=int(args.data_inicio[:4])
    ano_fim=int(args.data_fim[:4])

    mes_ini=int(args.data_inicio[5:7])
    mes_fim=int(args.data_fim[5:7])

    dia_ini=int(args.data_inicio[8:])
    dia_fim=int(args.data_fim[8:])
    try:
        start_date = date(ano_ini, mes_ini, dia_ini)
        end_date = date(ano_fim, mes_fim, dia_fim)
    except ValueError:
        print("Data inválida. Checar meses, anos ou dias invalidos, e rodar de novo. ")
        sys.exit()
    delta = timedelta(days=1)
    for i in tipos:
        current_date = start_date
        while current_date <= end_date:
            ano=current_date.year
            mes=current_date.month
            dia=current_date.day
            padrao=f"TRANSACAO_{i}_PUBLICO_{ano}_{mes:02}_{dia:02}" #padrao pra pegar os dados
            pegar_dados(padrao,input,i)
            current_date += delta
    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"Execution time: {execution_time:.6f} seconds")