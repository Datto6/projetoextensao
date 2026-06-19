
#!/bin/bash

declare -A headers
count=0

for file in *.csv; do
    [ -f "$file" ] || continue

    header=$(head -n 1 "$file")
    if [[ -z "$header" ]]; then
        mkdir -p empty_files
        mv "$file" empty_files/
        continue
    fi
    if [[ -z "${headers[$header]}" ]]; then
        ((count++))
        dir="tipo_$count"
        headers["$header"]="$dir"
        mkdir -p "$dir"

        echo "Novo cabeçalho encontrado -> $dir"
    fi

    mv "$file" "${headers[$header]}/"
done