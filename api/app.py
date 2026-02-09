from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import base64
import time
import re
from dotenv import load_dotenv

# =============================================================================
# CONFIGURAÇÃO INICIAL
# =============================================================================

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# ✅ CORS COMPLETO PARA DESENVOLVIMENTO
CORS(app, resources={r"/*": {"origins": "*"}})  # Permite TODAS as origens

# =============================================================================
# CONFIGURAÇÕES GHOSTPAY
# =============================================================================

GHOSTPAY_SECRET_KEY = os.getenv('GHOSTPAY_SECRET_KEY')
GHOSTPAY_COMPANY_ID = os.getenv('GHOSTPAY_COMPANY_ID')

if not GHOSTPAY_SECRET_KEY:
    print("=" * 60)
    print("⚠️  AVISO: GHOSTPAY_SECRET_KEY não configurada")
    print("Configure no painel do Render.com")
    print("=" * 60)

GHOSTPAY_URL = "https://api.ghostspaysv2.com/functions/v1/transactions"

# Configurar Basic Auth
if GHOSTPAY_SECRET_KEY:
    auth_string = f"{GHOSTPAY_SECRET_KEY}:"
    basic_auth = base64.b64encode(auth_string.encode()).decode()
else:
    basic_auth = None

# =============================================================================
# CONFIGURAÇÕES DO PRODUTO
# =============================================================================

PRODUCT_NAME = "Mentoria Venda Hoje - Acesso Vitalício"
PRODUCT_PRICE = 890  # R$ 8.90
COMPANY_EMAIL = "suporte.vendahoje@gmail.com"

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def clean_document(document):
    """Limpa CPF/CNPJ"""
    if document:
        return re.sub(r'\D', '', document)
    return "00000000191"

def create_headers():
    """Cria headers para API GhostPay"""
    headers = {
        'accept': 'application/json',
        'content-type': 'application/json',
        'authorization': f'Basic {basic_auth}',
    }
    if GHOSTPAY_COMPANY_ID:
        headers['Company-ID'] = GHOSTPAY_COMPANY_ID
    return headers

def create_test_qr_code():
    """QR Code de teste para desenvolvimento"""
    return "00020101021226920014br.gov.bcb.pix2560api.ghostpay.io/qrcode/example5204000053039865802BR5913VENDAS+HOJE6009SAO+PAULO62070503***6304E2CA"

# =============================================================================
# MIDDLEWARE CORS - ADICIONE ESTA FUNÇÃO
# =============================================================================

@app.after_request
def after_request(response):
    """Adiciona headers CORS para todas as respostas"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# =============================================================================
# ROTAS DA API
# =============================================================================

@app.route('/health', methods=['GET', 'OPTIONS'])
def health_check():
    """Verifica se a API está online"""
    if request.method == 'OPTIONS':
        return '', 200
    
    return jsonify({
        "status": "OK",
        "service": "Venda Hoje API",
        "version": "1.0.0",
        "product": PRODUCT_NAME,
        "price": f"R$ {PRODUCT_PRICE/100:.2f}",
        "environment": "production" if basic_auth else "development",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cors": "enabled"
    })

@app.route('/create-payment', methods=['POST', 'OPTIONS'])
def create_payment():
    """Cria pagamento PIX"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        # Se não tem chaves configuradas, retorna modo de teste
        if not basic_auth:
            qr_code = create_test_qr_code()
            return jsonify({
                "success": True,
                "test_mode": True,
                "message": "Modo de teste - Configure as chaves no Render",
                "transaction": {
                    "id": f"test_{int(time.time())}",
                    "status": "pending",
                    "amount": PRODUCT_PRICE
                },
                "pix": {
                    "qr_code": qr_code,
                    "code": qr_code,
                    "copy_paste": qr_code
                }
            })
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                "error": True,
                "message": "Dados não recebidos"
            }), 400
        
        # Usar dados do frontend ou padrão
        if 'customer' in data:
            customer = data['customer']
            amount = data.get('amount', PRODUCT_PRICE)
        else:
            return jsonify({
                "error": True,
                "message": "Estrutura de dados inválida"
            }), 400
        
        # Validar
        if not customer.get('name') or not customer.get('email'):
            return jsonify({
                "error": True,
                "message": "Nome e email são obrigatórios"
            }), 400
        
        if amount < 100:
            return jsonify({
                "error": True,
                "message": "Valor mínimo é R$ 1,00"
            }), 400
        
        # Payload para GhostPay
        payload = {
            "paymentMethod": "PIX",
            "customer": {
                "name": customer.get('name', 'Cliente Venda Hoje'),
                "email": customer.get('email', COMPANY_EMAIL),
                "phone": customer.get('phone', '11999999999'),
                "document": {
                    "number": clean_document(customer.get('document')),
                    "type": "CPF"
                }
            },
            "items": [{
                "title": PRODUCT_NAME,
                "unitPrice": amount,
                "quantity": 1,
                "externalRef": f"venda-hoje-{int(time.time())}"
            }],
            "amount": amount,
            "description": data.get('description', PRODUCT_NAME),
            "metadata": {
                "product": "mentoria_venda_hoje",
                "access_type": "vitalicio",
                "source": "landing_page"
            },
            "pix": {},
            "expiresInDays": 1
        }
        
        # Enviar para GhostPay
        response = requests.post(
            GHOSTPAY_URL,
            json=payload,
            headers=create_headers(),
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            response_data = response.json()
            
            # Extrair QR Code
            pix_data = response_data.get('pix', {})
            qr_code = pix_data.get('qrcode') or pix_data.get('qrCode') or pix_data.get('text')
            
            if qr_code:
                return jsonify({
                    "success": True,
                    "transaction": {
                        "id": response_data.get('id'),
                        "status": response_data.get('status'),
                        "amount": response_data.get('amount')
                    },
                    "pix": {
                        "qr_code": qr_code,
                        "code": qr_code,
                        "copy_paste": qr_code
                    }
                })
            else:
                return jsonify({
                    "error": True,
                    "message": "QR Code não recebido"
                }), 500
        else:
            return jsonify({
                "error": True,
                "message": f"Erro na API GhostPay: {response.status_code}",
                "details": response.text[:200] if response.text else "Sem resposta"
            }), response.status_code
            
    except Exception as e:
        return jsonify({
            "error": True,
            "message": f"Erro interno: {str(e)}"
        }), 500

@app.route('/check-payment/<transaction_id>', methods=['GET', 'OPTIONS'])
def check_payment(transaction_id):
    """Verifica status do pagamento"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        if not basic_auth:
            return jsonify({
                "success": True,
                "test_mode": True,
                "status": "paid",
                "message": "Modo de teste - Pagamento simulado"
            })
        
        response = requests.get(
            f"{GHOSTPAY_URL}/{transaction_id}",
            headers=create_headers(),
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                "success": True,
                "status": data.get('status'),
                "paid_at": data.get('paidAt'),
                "transaction": data
            })
        else:
            return jsonify({
                "error": True,
                "message": "Transação não encontrada"
            }), 404
            
    except Exception as e:
        return jsonify({
            "error": True,
            "message": f"Erro: {str(e)}"
        }), 500

@app.route('/', methods=['GET', 'OPTIONS'])
def home():
    """Página inicial da API"""
    if request.method == 'OPTIONS':
        return '', 200
    
    return jsonify({
        "api": "Venda Hoje Checkout API",
        "version": "1.0.0",
        "status": "online",
        "product": PRODUCT_NAME,
        "price": f"R$ {PRODUCT_PRICE/100:.2f}",
        "endpoints": {
            "POST /create-payment": "Criar pagamento PIX",
            "GET /check-payment/<id>": "Verificar status",
            "GET /health": "Status da API"
        },
        "docs": "https://github.com/Joseph001479/venda-hoje"
    })

# =============================================================================
# CONFIGURAÇÃO DO SERVIDOR
# =============================================================================

if __name__ == '__main__':
    # Render usa a porta da variável de ambiente PORT
    port = int(os.environ.get('PORT', 5000))
    
    print("=" * 60)
    print("🚀 VENDA HOJE API - CORS CORRIGIDO")
    print("=" * 60)
    print(f"🌐 URL: http://0.0.0.0:{port}")
    print(f"📦 Produto: {PRODUCT_NAME}")
    print(f"💰 Preço: R$ {PRODUCT_PRICE/100:.2f}")
    print(f"🔑 API Configurada: {'SIM' if basic_auth else 'NÃO (modo teste)'}")
    print(f"🔓 CORS: HABILITADO PARA TODAS AS ORIGENS")
    print("=" * 60)
    
    # No Render, debug deve ser False
    debug_mode = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)