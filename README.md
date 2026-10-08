## Como rodar o site:
### Dependências
Esta aplicação utiliza o **Redis** como Message Broker e Result Backend para gerenciar as tarefas assíncronas do Celery.

* **Linux (Ubuntu/Debian):**
```bash
  sudo apt update
  sudo apt install redis-server
  sudo systemctl start redis
```

### Comandos
Em um terminal execute
```bash
celery -A main.celery worker --loglevel=info
```
e em seguida execute em outro terminal
```bash
python3 main.py
```

## Dicas de depuração
- Você pode alterar o caminho retornado pela função para testar a exibição das imagens
