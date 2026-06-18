#!/bin/bash

# Processa todos os arquivos com data (compatível com versão anterior)
#./merge_any_files.sh /path/to/dir

# Processa apenas arquivos de maio de 2025
#./merge_any_files.sh /path/to/dir "2025_05_*"

# Processa arquivos que começam com "TRANSACAO_"
#./merge_any_files.sh /path/to/dir "TRANSACAO_*"

# Processa apenas arquivos CSV
#./merge_any_files.sh /path/to/dir "*.csv"



DIR="$1"
PATTERN="$2"

if [ -z "$DIR" ]; then
    echo "Uso: $0 <diretorio> [padrao_arquivo]"
    echo "Exemplo: $0 /path/to/dir '2025_05_*'"
    echo "Se nenhum padrão for fornecido, processa todos os arquivos com data"
    exit 1
fi

cd "$DIR" || exit 1

# Se não especificado padrão, usa o padrão de data padrão
if [ -z "$PATTERN" ]; then
    PATTERN="*_[0-9][0-9][0-9][0-9]_[0-9][0-9]_[0-9][0-9].{csv,txt}"
fi

# Lista arquivos que correspondem ao padrão
FILES=$(ls $PATTERN 2>/dev/null)

if [ -z "$FILES" ]; then
    echo "Nenhum arquivo encontrado no formato esperado."
    exit 1
fi

# Extrai datas e encontra a menor (primeiro arquivo do mês)
FIRST_FILE=$(for f in $FILES; do
    datepart=$(echo "$f" | grep -o "[0-9]\{4\}_[0-9]\{2\}_[0-9]\{2\}")
    echo "$datepart $f"
done | sort | head -n 1 | awk '{print $2}')

echo "Primeiro arquivo do mês: $FIRST_FILE"

# Extrai AAAA_MM para nome do arquivo final
MONTH=$(echo "$FIRST_FILE" | grep -o "[0-9]\{4\}_[0-9]\{2\}")

OUTPUT="merged_${MONTH}.txt"
> "$OUTPUT"

# Primeiro arquivo entra inteiro
cat "$FIRST_FILE" >> "$OUTPUT"

# Processa os demais
for f in $FILES; do
    if [ "$f" != "$FIRST_FILE" ]; then
        # Remove a primeira linha e salva no próprio arquivo
        tail -n +2 "$f" > "${f}.tmp" && mv "${f}.tmp" "$f"

        # Adiciona ao merge
        cat "$f" >> "$OUTPUT"
    fi
done

echo "Arquivo final gerado: $OUTPUT"

