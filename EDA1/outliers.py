import duckdb

import pandas as pd
import os
from constants import *
import time
import argparse
from pathlib import Path

def filtrar(diretorios):
    for dir in diretorios:
        duckdb.sql(f"""
        COPY (
            SELECT *
            FROM read_csv(
                '{dir}/*.csv',
                all_varchar = true,
                header = true
            )
            WHERE data_transacao < '2026-01-01'
            OR data_transacao >= '2026-08-01'
        )
        TO 'outside_window_{dir[:2]}.csv'
        (FORMAT CSV, HEADER,DELIMITER ',');
        """)

if __name__=="__main__":
    diretorios=["BE_separated_2026","BU_separated_2026","GT_separated_2026"]
    filtrar(diretorios)
