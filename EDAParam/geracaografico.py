import os,sys,argparse,time,shutil
from testecurl import pegar_dados
from pathlib import Path
import re
from datetime import date,timedelta
from merger import mergerMes
from eda_be_param import EDA_BE
from eda_bui_param import EDA_BU
from eda_gt_param import EDA_GT
path_input=Path("vamola")
path_saida=Path("resultado")
data_ini="2026-03-16"
data_fim="2026-03-24"
# EDA_BE(input=path_saida/"BE",output=path_saida/"BE"/"graficos",sep=",",data_ini=data_ini,data_fim=data_fim)
EDA_BU(input=path_saida/"BU",output=path_saida/"BU"/"graficos",sep=",",data_ini=data_ini,data_fim=data_fim)
EDA_GT(input=path_saida/"GT",output=path_saida/"GT"/"graficos",sep=",",data_ini=data_ini,data_fim=data_fim)