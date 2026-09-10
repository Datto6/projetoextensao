import os
import re
import zipfile
import requests


PADRAO = os.sys.argv[1]
DESTINO = os.sys.argv[2]

# Get package information
url = "https://dadosabertos.rj.gov.br/api/3/action/package_show?id=setram_sbe"

response = requests.get(url)
response.raise_for_status()

data = response.json()

# Download matching resources
for resource in data["result"]["resources"]:
    nome = resource["name"] #nome de um recurso individual dentro dos recursos achados no request
    download_url = resource["url"] #URL de um recurso individual

    if re.search(PADRAO, nome):  #re é um módulo de expressões regulares
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

# Extract ZIPs and remove them
for filename in os.listdir(DESTINO):
    if filename.endswith(".zip"):
        filepath = os.path.join(DESTINO, filename)

        print(f"Extraindo: {filename}")

        with zipfile.ZipFile(filepath, "r") as zip_ref:
            zip_ref.extractall(DESTINO)

        os.remove(filepath)