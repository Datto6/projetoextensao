import os
import re
import zipfile
import requests
import shutil
class SemRecursos(Exception):
    pass
class SemEspaco(Exception):
    pass

def pegar_dados(PADRAO,DESTINO,TIPO):
    # Get package information
    termino=""
    if TIPO=="BE":
        termino="be"
    if TIPO=="BU":
        termino="bu"
    if TIPO=="GRATUIDADE":
        termino="gr"
    url = f"https://dadosabertos.rj.gov.br/api/3/action/package_show?id=setram_s{termino}"
    response = requests.get(url)
    response.raise_for_status()

    data = response.json()

    # Descobrir quais arquivos serão baixados
    recursos = []

    for resource in data["result"]["resources"]:
        nome = resource["name"]
        download_url = resource["url"]

        if re.search(PADRAO, nome):
            recursos.append((nome, download_url))
        
    if len(recursos)==0: #Checa se achei algum arquivo
        raise SemRecursos("Não foi achado nenhum arquivo")
    
    # Calcular o tamanho total
    tamanho_total = 0

    for nome, download_url in recursos:
        resposta = requests.head(download_url, allow_redirects=True)
        resposta.raise_for_status()

        tamanho = int(resposta.headers.get("Content-Length", 0))
        tamanho_total += tamanho

        print(f"{nome}: {tamanho / (1024**3):.2f} GB")


    # Verificar espaço disponível
    os.makedirs(DESTINO, exist_ok=True)

    _, _, espaco_livre = shutil.disk_usage(DESTINO)

    print(f"\nTamanho total: {tamanho_total / (1024**3):.2f} GB")
    print(f"Espaço livre:  {espaco_livre / (1024**3):.2f} GB")

    if tamanho_total > espaco_livre:
        raise SemEspaco("ERRO: não há espaço suficiente para baixar os arquivos.")

    print(f"Espaço suficiente. Iniciando download dos arquivos de {TIPO}...\n")
    # Download matching resources

    for nome,download_url in recursos:
    #nome= nome de um recurso individual dentro dos recursos achados no request
    #download_url=URL de um recurso individual
        filename = download_url.split("/")[-1] #pegar último item, separado por "/"
        filepath = os.path.join(DESTINO, filename)
        os.makedirs(DESTINO,exist_ok=True)
        print(f"Baixando: {filename}")

        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()

            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
    # Calcular tamanho descompactado de todos os ZIPs
    tamanho_extraido = 0

    for filename in os.listdir(DESTINO):
        if filename.endswith(".zip"):
            filepath = os.path.join(DESTINO, filename)
            with zipfile.ZipFile(filepath, "r") as zip_ref:
                tamanho_extraido += sum(info.file_size for info in zip_ref.infolist())

    # Verificar espaço disponível
    _, _, espaco_livre = shutil.disk_usage(DESTINO)
    tamanho_necessario = tamanho_total + tamanho_extraido
    print(f"Tamanho dos ZIPs: "+f"{tamanho_total / (1024**3):.2f} GB")
    print(f"Tamanho descompactado: " + f"{tamanho_extraido / (1024**3):.2f} GB")

    print(f"Tamanho necessário para extração: "+f"{tamanho_necessario / (1024**3):.2f} GB")

    print(f"Espaço livre: "f"{espaco_livre / (1024**3):.2f} GB")

    if tamanho_extraido > espaco_livre:
        raise SemEspaco("ERRO: não há espaço suficiente para baixar os arquivos.")
    
    # Extract ZIPs and remove them
    for filename in os.listdir(DESTINO):
        if filename.endswith(".zip"):
            filepath = os.path.join(DESTINO, filename)

            print(f"Extraindo: {filename}")

            with zipfile.ZipFile(filepath, "r") as zip_ref:
                zip_ref.extractall(DESTINO)

            os.remove(filepath)