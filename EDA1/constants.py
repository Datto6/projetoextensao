def pega_dict(tipo: str) -> dict:
    #funcao de pegar dicionario de colunas brutas de cada tipo
    if tipo=="BE": return COLUNAS_BE
    if tipo=="BU": return COLUNAS_BU
    if tipo=="GT": return COLUNAS_GT
def pega_dict_processado(tipo: str) -> dict:
    #funcao de pegar dicionario de colunas no csv ja processado
    if tipo=="BE": return DTYPES_BE
    if tipo=="BU": return DTYPES_BU
    if tipo=="GT": return DTYPES_GT
COLUNAS_BE={
    "Nº Cartão":               "num_cartao",
    "Descrição da Aplicação":  "descricao_aplicacao",
    "Sindicato":               "sindicato",
    "Operadora":               "operadora",
    "Linha":                   "linha",
    "Nº Carro":                "num_carro",
    "Sentido":                 "sentido", #OBS, vazio em BE 
    #"Nº Validador":            "num_validador",  tava dando erro na leitura disso, apenas tirei pois nao usamos
    "Data da Transação":       "data_transacao",
    "Data do Processamento":   "data_processamento",
    "Vl Linha":                "vl_linha",
    "Vl Trans":                "vl_trans",
    "Vl Subsídio":             "vl_subsidio", #OBS, vazio em BE
    "Cartão Hash":              "cartao_hash"
}

COLUNAS_BU = {
    "Nº Cartão":               "num_cartao",
    "Descrição da Aplicação":  "descricao_aplicacao",
    "Sindicato":               "sindicato",
    "Operadora":               "operadora",
    "Linha":                   "linha",
    "Nº Carro":                "num_carro",
    "Sentido":                 "sentido",
    # "Nº Validador":            "num_validador", #tava dando erro na leitura disso, apenas tirei pois nao usamos
    "Data da Transação":       "data_transacao", #dayfirst=True
    "Data do Processamento":   "data_processamento", #dayfirst=true
    "Vl Linha":                "vl_linha",
    "Vl Trans":                "vl_trans",
    "Vl Subsídio":             "vl_subsidio",
    "Qtde Integrações":        "qtde_integracoes",
    "Data da Ordem":           "data_ordem", #dayfirst=False
    "Nº Ordem":                "num_ordem",
    "Cartão Hash":              "cartao_hash"
}
COLUNAS_GT={
    "Nº Cartão":               "num_cartao",
    "Descrição da Aplicação":  "descricao_aplicacao",
    "Sindicato":               "sindicato",
    "Operadora":               "operadora",
    "Linha":                   "linha",
    "Nº Carro":                "num_carro",
    "Nº Validador":            "num_validador",
    "Data da Transação":       "data_transacao",
    "Data do Processamento":   "data_processamento",
    "Transações":               "transacoes", 
    "Escola":                  "escola",
    "Nº Censo Escola":          "num_escola",
    "Cartão Hash":              "cartao_hash",
}
SENTIDO_MAP = {0: "Não informado", 1: "Ida", 2: "Volta"}

DTYPES_BE={
    'data_processamento':'str',# 'datetime64[us]',
    'data_transacao': 'str',   #datetime64[us]',
    'num_cartao': 'str', 
    'descricao_aplicacao': 'str',
    'sindicato': 'str',
    'operadora': 'str',
    'linha': 'str',
    'num_carro': 'int64',
    'sentido': 'float64',
    'vl_linha': 'float64',
    'vl_trans': 'float64',
    'vl_subsidio': 'float64',
    'hora': 'int32',
    'dia_semana': 'str',
    'data_dia': 'object',
    'pct_subsidio': 'float64',
    'sentido_label': 'str',
    'tipo_aplicacao': 'str',
    'cartao_hash':'str'
}

DTYPES_GT={
    'data_processamento':'str',# 'datetime64[us]',
    'data_transacao': 'str',   #datetime64[us]',
    'descricao_aplicacao': 'str',
    'escola': 'str',
    'linha': 'str',
    'num_carro': 'int64',
    'num_cartao': 'str',
    'num_escola': 'str',
    'num_validador': 'int64',
    'operadora': 'str',
    'sindicato': 'str',
    'transacoes': 'str',
    'hora': 'int32',
    'dia_semana': 'str',
    'data_dia': 'object',
    'tipo_aplicacao': 'str',
    'cartao_hash':'str',
}

DTYPES_BU={
    'num_cartao': 'str',
    'descricao_aplicacao': 'str',
    'sindicato': 'str',
    'operadora': 'str',
    'linha': 'str',
    'num_carro': 'int64',
    'sentido': 'int64',
    'data_processamento':'str', # 'datetime64[us]',
    'data_transacao': 'str',   # 'datetime64[us]',
    'vl_linha': 'float64',
    'vl_trans': 'float64',
    'vl_subsidio': 'float64',
    'qtde_integracoes': 'int64',
    'data_ordem': 'str', #'datetime64[us]',
    'num_ordem': 'int64',
    'hora': 'int32',
    'dia_semana': 'str',
    'data_dia': 'object',
    'pct_subsidio': 'float64',
    'sentido_label': 'str',
    'tipo_aplicacao': 'str',
    'cartao_hash':'str'
}