#!/bin/bash

PADRAO="$1"

curl -s "https://dadosabertos.rj.gov.br/api/3/action/package_show?id=setram_sbu" \
  | jq -r --arg p "$PADRAO" '.result.resources[] | select(.name | test($p)) | .url' \
  | xargs -n 1 wget -c

