from flask import Flask, jsonify, render_template, request, url_for
from celery import Celery
import time
import os
import uuid

app = Flask(__name__)

# Configuração de conexão com o Redis
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'

# Inicializando o Celery atrelado ao Flask
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# A anotação @celery.task avisa que ela vai rodar em segundo plano
@celery.task(bind=True)
def processamento_externo(self, data_inicial, data_final, local_entrada, pasta_saida):
    print(f"Iniciando processamento em background... (Destino: {pasta_saida})")

    # só chamar a função de processamento aqui dentro
    
    time.sleep(2)
    
    return {'status': 'Concluído'}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/processar', methods=['POST'])
def processar():
    dados = request.get_json()
    
    # Gera ID e cria pasta
    exec_id = str(uuid.uuid4())
    pasta_saida = os.path.join(app.static_folder, 'exports', exec_id)
    os.makedirs(pasta_saida, exist_ok=True)

    # ENVIA PARA O CELERY USANDO .delay()
    # Isso NÃO trava o código. Ele despacha e passa para a linha de baixo imediatamente.
    task = processamento_externo.delay(
        dados.get('data_inicial'),
        dados.get('data_final'),
        dados.get('local_entrada'),
        pasta_saida
    )

    # Retorna o ID da tarefa (o "ticket") para o JavaScript
    return jsonify({
        'task_id': task.id, 
        'exec_id': exec_id
    }), 202


@app.route('/status/<task_id>/<exec_id>')
def task_status(task_id, exec_id):
    # Consulta o status da tarefa no Redis
    task = processamento_externo.AsyncResult(task_id)
    
    if task.state == 'PENDING' or task.state == 'PROGRESS':
        return jsonify({'state': task.state})
        
    elif task.state == 'SUCCESS':
        caminho = url_for('static', filename=f'exports/{exec_id}/')
        return jsonify({
            'state': task.state,
            'caminho': caminho # Altere aqui para "static/teste" para teste
        })
        
    else:
        return jsonify({'state': 'FAILURE', 'erro': str(task.info)})


if __name__ == '__main__':
    app.run(debug=True)