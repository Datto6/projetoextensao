import tkinter as tk
from tkinter import filedialog
from argparse import Namespace
from tkcalendar import DateEntry


def get_arguments():

    result = {}

    def escolher_input():
        path = filedialog.askdirectory()
        if path:
            input_entry.delete(0, tk.END)
            input_entry.insert(0, path)

    def escolher_output():
        path = filedialog.askdirectory()
        if path:
            output_entry.delete(0, tk.END)
            output_entry.insert(0, path)

    def confirmar():
        # DateEntry returns a datetime.date object
        data_inicio = data_inicio_entry.get_date()
        data_fim = data_fim_entry.get_date()

        result["data_inicio"] = data_inicio.strftime("%Y/%m/%d")
        result["data_fim"] = data_fim.strftime("%Y/%m/%d")
        result["sep"] = sep_entry.get()
        result["input"] = input_entry.get()
        result["output"] = output_entry.get()
        janela.destroy()

    janela = tk.Tk()
    janela.title("Entrada para EDA sobre dados")
    janela.geometry("600x300")

    # =========================================================
    # Data inicial
    # =========================================================

    tk.Label(janela,text="Data inicial:").grid(
        row=0,
        column=0,
        padx=10,
        pady=10,
        sticky="w"
    )

    data_inicio_entry = DateEntry(janela,
        width=17,
        date_pattern="dd/mm/yyyy"
    )

    data_inicio_entry.grid(
        row=0,
        column=1,
        padx=10,
        pady=10,
        sticky="w"
    )
    # =========================================================
    # Data final
    # =========================================================

    tk.Label(janela,text="Data final:").grid(
        row=1,
        column=0,
        padx=10,
        pady=10,
        sticky="w"
    )

    data_fim_entry = DateEntry(janela,width=17,
        date_pattern="dd/mm/yyyy"
    )

    data_fim_entry.grid(
        row=1,
        column=1,
        padx=10,
        pady=10,
        sticky="w"
    )

    # =========================================================
    # Separador
    # =========================================================

    tk.Label(
        janela,
        text="Separador:"
    ).grid(
        row=2,
        column=0,
        padx=10,
        pady=10,
        sticky="w"
    )

    sep_entry = tk.Entry(janela)
    sep_entry.insert(0, ";")

    sep_entry.grid(
        row=2,
        column=1,
        padx=10,
        pady=10,
        sticky="w"
    )

    # =========================================================
    # Input
    # =========================================================

    tk.Label(
        janela,
        text="Pasta de entrada:"
    ).grid(
        row=3,
        column=0,
        padx=10,
        pady=10,
        sticky="w"
    )

    input_entry = tk.Entry(
        janela,
        width=40
    )

    input_entry.grid(
        row=3,
        column=1,
        padx=10,
        pady=10
    )

    tk.Button(
        janela,
        text="Procurar",
        command=escolher_input
    ).grid(
        row=3,
        column=2,
        padx=5
    )

    # =========================================================
    # Output
    # =========================================================

    tk.Label(
        janela,
        text="Pasta de saída:"
    ).grid(
        row=4,
        column=0,
        padx=10,
        pady=10,
        sticky="w"
    )

    output_entry = tk.Entry(
        janela,
        width=40
    )

    output_entry.grid(
        row=4,
        column=1,
        padx=10,
        pady=10
    )

    tk.Button(
        janela,
        text="Procurar",
        command=escolher_output
    ).grid(
        row=4,
        column=2,
        padx=5
    )

    # =========================================================
    # Executar
    # =========================================================

    tk.Button(janela,
        text="Executar",
        command=confirmar,
        width=15
    ).grid(
        row=5,
        column=1,
        pady=20
    )
    janela.mainloop()
    return Namespace(**result) #retorna um objeto igual o args parse