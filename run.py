import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from backend.app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('=' * 50)
    print('  RETRO AFILIADOS - Servidor rodando!')
    print('=' * 50)
    print(f'  Acesse: http://localhost:{port}')
    print('  Pressione CTRL+C para parar')
    print('=' * 50)
    app.run(host='0.0.0.0', port=port, debug=True)
