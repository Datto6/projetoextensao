import os,sys,argparse,time,shutil
from testecurl import pegar_dados,SemEspaco,SemRecursos
from pathlib import Path
from datetime import date,timedelta
from merger import mergerMes
from eda_be_param import EDA_BE
from eda_bui_param import EDA_BU
from eda_gt_param import EDA_GT
from interface_grafica import get_arguments


def main():
    start_time=time.perf_counter()
    args = get_arguments()
    tipos=["BE","BU","GRATUIDADE"]
    input=args.input
    #assume yyyy/mm/dd para as datas
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
    path_input=Path(input)
    downloaded=[]
    hoje=date.today()
    #Rotina de download de arquivos
    for i in tipos:
        comeco_download=time.perf_counter()
        path=path_input/i #input/tipo
        current_date = start_date
        fez_download=False
        while current_date <= end_date and current_date <=hoje:
            ano=current_date.year
            mes=current_date.month
            dia=current_date.day
            padrao=f"TRANSACAO_{i}_PUBLICO_{ano}_{mes:02}_{dia:02}" #padrao pra pegar os dados
            try:
                pegar_dados(padrao,path,i)
                fez_download=True
            except SemRecursos:
                fez_download=False
                break
            except SemEspaco:
                shutil.rmtree(path) #Sem espaço, apagar arquivos do tipo
                print(f"Sem espaço a partir do dia TRANSACAO_{i}_PUBLICO_{ano}_{mes:02}_{dia:02}, apagando diretorio desse tipo ")
                fez_download=False
                break
            except Exception:
                shutil.rmtree(path) #caso de erro, apagar arquivos do tipo
                print(f"Erro de leitura no dia TRANSACAO_{i}_PUBLICO_{ano}_{mes:02}_{dia:02}, apagando diretorio desse tipo ")
                fez_download=False
                break
            current_date += delta
        if fez_download:
            downloaded.append(i) #adiciono esse tipo aos tipos que foram baixados
            fim_download=time.perf_counter()
            download_time = fim_download - comeco_download
            print(f"Tempo de download de {i}: {download_time:.6f} seconds")
            tipo=i
            if i=="GRATUIDADE":
                tipo="GT"
            mergerMes(path,args.output,tipo,args.sep)
    path_saida=Path(args.output)

    #chamadas de funcoes de gerar os graficos
    data_ini=f"{ano_ini}-{mes_ini}-{dia_ini}"
    data_fim=f"{ano_fim}-{mes_fim}-{dia_fim}"
    if "BE" in downloaded:
        EDA_BE(input=path_saida/"BE",output=path_saida/"BE"/"graficos",sep=",",data_ini=data_ini,data_fim=data_fim)
    if "BU" in downloaded:
        EDA_BU(input=path_saida/"BU",output=path_saida/"BU"/"graficos",sep=",",data_ini=data_ini,data_fim=data_fim)
    if "GRATUIDADE" in downloaded:
        EDA_GT(input=path_saida/"GT",output=path_saida/"GT"/"graficos",sep=",",data_ini=data_ini,data_fim=data_fim)
    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"Execution time: {execution_time:.6f} seconds(total do script todo)")

if __name__=="__main__":
    main()