#!/bin/bash

PADRAO="$1"
DESTINO="$2"
curl -s "https://dadosabertos.rj.gov.br/api/3/action/package_show?id=setram_sbu" \
  | jq -r --arg p "$PADRAO" '.result.resources[] | select(.name | test($p)) | .url' \
  | xargs -n 1 wget -c -P "$DESTINO" 

for f in "$DESTINO"/*.zip; do 
  unzip "$f" -d "$DESTINO" && rm "$f"; 
done
# -s ->download em modo silencioso \ indica que comando continua, | manda resultado p prox comando
#-r raw output --arg passa p como variavel com valor de PADRAO
#'' ao redor dos comandos pro jq, acessa result->resources->select->.name->testa se PADRAO ta dentro->passa p url se true
#depois faz unzip e remocao de .zip no diretorio escolhido
#usage: ./download_setram.sh padrao_arquivo diretorio_destino