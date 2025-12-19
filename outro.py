import pandas as pd

respostas0 = pd.read_csv(
    'C:\\transporte\\karla\\input\\TRANSACAO_BU_PUBLICO_2025_05_28.csv',
    sep=';'
)
respostas1=pd.read_csv(
    'C:\\transporte\\karla\\input\\TRANSACAO_BU_PUBLICO_2025_05_29.csv',
    sep=';'
)
respostas2=pd.read_csv(
    'C:\\transporte\\karla\\input\\TRANSACAO_BU_PUBLICO_2025_05_30.csv',
    sep=';'
)
respostas3=pd.read_csv(
    'C:\\transporte\\karla\\input\\TRANSACAO_BU_PUBLICO_2025_05_31.csv',
    sep=';'
)
respostas=pd.concat([respostas0,respostas1,respostas2,respostas3]) #concatena todos os inputs

respostas['hora'] = pd.to_datetime(
    respostas['Data da Transação'],
    dayfirst=True,
    errors='coerce'
).dt.strftime('%Hh')  #extraindo horario

tabela = respostas.groupby(['Nº Carro', 'hora']).size().unstack(fill_value=0) #agrupando por numero de carro, e hora 
#size retorna o numero de linhas, que no nosso caso eh quantas vezes o carro aparece
#unstack para des-esculhambar o novo dataframe que sai do groupby

horas = [f'{i:02d}h' for i in range(24)]
tabela = tabela.reindex(columns=horas, fill_value=0)

# traz o Nº Carro de volta como coluna visível
tabela = tabela.reset_index()

tabela.to_csv('output.csv', index=False) 