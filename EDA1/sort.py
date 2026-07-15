import duckdb
con = duckdb.connect()

months = [
    ("2026-01-01", "2026-02-01"),
    ("2026-02-01", "2026-03-01"),
    ("2026-03-01", "2026-04-01"),
    ("2026-04-01", "2026-05-01"),
    ("2026-05-01", "2026-06-01"),
    ("2026-06-01", "2026-07-01"),
    ("2026-07-01", "2026-08-01")
]

#seleciona tudo e trata tudo como string. ORDER BY funciona na data porque a data ta no formato ISO
con.execute("""
COPY (
    SELECT *
    FROM read_csv(
    'BU_separated_2026/*.csv',
    all_varchar = true,
    delim = ',',
    header = true
    )
    ORDER BY "cartao_hash", "data_transacao"
)
TO 'sorted.csv'
(FORMAT CSV, HEADER, DELIMITER ',');
""")

for start, end in months:
    outfile = f"sorted\\ORDENADO_mes_{start[5:7:1]}_BU_.csv"

    con.execute(f"""
    COPY (
        SELECT *
        FROM read_csv('sorted.csv',all_varchar = true,delim = ',',header = true)
        WHERE "data_transacao" >= '{start}'
          AND "data_transacao" < '{end}'
    )
    TO '{outfile}'
    (FORMAT CSV, HEADER);
    """)