import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
import psycopg2.extras
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
# Em produção, use uma chave secreta segura e aleatória
app.secret_key = "npg_R8YrbUaNDe1J"

# --- CONFIGURAÇÕES ---
DATABASE_URL = "postgresql://neondb_owner:npg_R8YrbUaNDe1J@ep-small-dawn-ac8dbw8e-pooler.sa-east-1.aws.neon.tech/minhavagaesua?sslmode=require&channel_binding=require"

# Função de conexão com o banco de dados
def get_db():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
    except Exception as e:
        print(f"Erro de conexão com o Banco: {e}")
        return None

# Middleware de Autenticação
def require_auth():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return None

# -------------------------------------------------------------------------
# ROTAS DE LOGIN E ACESSO
# -------------------------------------------------------------------------

@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    # Se o utilizador já estiver autenticado, redireciona para o dashboard
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        inscricao = request.form.get("inscricao", "").strip()
        senha = request.form.get("senha", "").strip()
        
        conn = get_db()
        if not conn:
            flash("Erro de conexão com o banco de dados.", "error")
            return render_template("login.html")
            
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE n_inscricao = %s", (inscricao,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user:
            flash("Número de inscrição não encontrado.", "error")
            return render_template("login.html")

        # CASO 1: PRIMEIRO ACESSO (Senha no banco é NULL)
        # O utilizador deve deixar o campo senha em branco
        if user['password_hash'] is None:
            if senha == "":
                # Guarda o ID temporariamente para o cadastro de senha
                session['temp_user_id'] = user['n_inscricao']
                return redirect(url_for("definir_senha"))
            else:
                flash("Primeiro acesso identificado. Por favor, deixe o campo de senha EM BRANCO e clique em Entrar.", "info")
                return render_template("login.html")

        # CASO 2: LOGIN PADRÃO
        if check_password_hash(user['password_hash'], senha):
            # Login bem-sucedido
            session['user_id'] = user['n_inscricao']
            session['nome'] = user['nome']
            
            # Verifica se o utilizador já escolheu as cidades
            if not user['lotacao_1']:
                return redirect(url_for("primeira_escolha"))
            
            return redirect(url_for("dashboard"))
        else:
            flash("Senha incorreta.", "error")

    return render_template("login.html")

@app.route("/definir-senha", methods=["GET", "POST"])
def definir_senha():
    # Segurança: Só acede se tiver passado pela validação de inscrição no login
    if 'temp_user_id' not in session:
        return redirect(url_for("login"))
    
    if request.method == "POST":
        nova_senha = request.form.get("nova_senha")
        confirma_senha = request.form.get("confirma_senha")
        
        if nova_senha != confirma_senha:
            flash("As senhas digitadas não conferem.", "error")
        elif len(nova_senha) < 4:
            flash("A senha deve ter pelo menos 4 caracteres.", "error")
        else:
            conn = get_db()
            cur = conn.cursor()
            
            # 1. Atualiza a senha
            hashed = generate_password_hash(nova_senha)
            cur.execute("UPDATE users SET password_hash = %s WHERE n_inscricao = %s", 
                       (hashed, session['temp_user_id']))
            conn.commit()
            
            # 2. Busca nome para a sessão real
            cur.execute("SELECT nome FROM users WHERE n_inscricao = %s", (session['temp_user_id'],))
            user_data = cur.fetchone()
            cur.close()
            conn.close()
            
            # 3. LOGA O UTILIZADOR AUTOMATICAMENTE (Sem pedir login de novo)
            user_id_real = session.pop('temp_user_id') # Remove temp
            session['user_id'] = user_id_real
            session['nome'] = user_data['nome']
            
            flash("Senha cadastrada com sucesso! Bem-vindo.", "success")
            
            # Redireciona para escolher vagas
            return redirect(url_for("primeira_escolha"))
            
    return render_template("definir_senha.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -------------------------------------------------------------------------
# ROTAS DE ESCOLHA E RANKING
# -------------------------------------------------------------------------

@app.route("/primeira-escolha", methods=["GET", "POST"])
def primeira_escolha():
    auth = require_auth()
    if auth: return auth

    conn = get_db()
    cur = conn.cursor()
    
    # Carrega lista de cidades do BD
    cur.execute("SELECT lotacao FROM lotacao_vagas ORDER BY lotacao")
    cidades = [r[0] for r in cur.fetchall()]
    
    if request.method == "POST":
        l1 = request.form.get("lotacao_1")
        l2 = request.form.get("lotacao_2") or None
        l3 = request.form.get("lotacao_3") or None
        
        # Validações
        erros = []
        if not l1:
            erros.append("A 1ª Opção é obrigatória.")
        
        # Verifica duplicatas (ignorando Nones)
        escolhas = [x for x in [l1, l2, l3] if x]
        if len(escolhas) != len(set(escolhas)):
             erros.append("Você não pode escolher a mesma cidade mais de uma vez.")

        if erros:
            for e in erros: flash(e, "error")
        else:
            cur.execute("""
                UPDATE users SET lotacao_1=%s, lotacao_2=%s, lotacao_3=%s 
                WHERE n_inscricao=%s
            """, (l1, l2, l3, session['user_id']))
            conn.commit()
            flash("Preferências salvas! Veja agora a sua classificação.", "success")
            return redirect(url_for("dashboard"))

    cur.close()
    conn.close()
    # Reutiliza o template de escolhas, flag 'primeira_vez' controla botão cancelar
    return render_template("escolhas.html", cidades=cidades, primeira_vez=True, escolhas=[])

@app.route("/alterar-lotacao", methods=["GET", "POST"])
def alterar_lotacao():
    auth = require_auth()
    if auth: return auth
    
    # (Futuramente: Adicionar trava se a data limite passou)

    conn = get_db()
    cur = conn.cursor()
    
    if request.method == "POST":
        l1 = request.form.get("lotacao_1")
        l2 = request.form.get("lotacao_2") or None
        l3 = request.form.get("lotacao_3") or None
        
        # Validações (mesma lógica)
        escolhas = [x for x in [l1, l2, l3] if x]
        if not l1:
            flash("A 1ª Opção não pode ficar vazia.", "error")
        elif len(escolhas) != len(set(escolhas)):
            flash("Não repita cidades nas opções.", "error")
        else:
            cur.execute("""
                UPDATE users SET lotacao_1=%s, lotacao_2=%s, lotacao_3=%s 
                WHERE n_inscricao=%s
            """, (l1, l2, l3, session['user_id']))
            conn.commit()
            flash("As suas opções de lotação foram atualizadas.", "success")
            return redirect(url_for("dashboard"))

    # Carrega dados para preencher o form
    cur.execute("SELECT lotacao FROM lotacao_vagas ORDER BY lotacao")
    cidades = [r[0] for r in cur.fetchall()]
    
    cur.execute("SELECT lotacao_1, lotacao_2, lotacao_3 FROM users WHERE n_inscricao=%s", (session['user_id'],))
    user_row = cur.fetchone()
    # Converte row para lista para facilitar no template
    escolhas_atuais = [user_row['lotacao_1'], user_row['lotacao_2'], user_row['lotacao_3']]
    
    cur.close()
    conn.close()
    
    return render_template("escolhas.html", cidades=cidades, primeira_vez=False, escolhas=escolhas_atuais)

@app.route("/dashboard")
def dashboard():
    auth = require_auth()
    if auth: return auth
    
    conn = get_db()
    cur = conn.cursor()
    
    # 1. Dados do Utilizador Logado
    cur.execute("SELECT * FROM users WHERE n_inscricao=%s", (session['user_id'],))
    user = cur.fetchone()
    
    # Se por algum motivo (bug) o utilizador não tiver escolhas, joga para escolha
    if not user['lotacao_1']:
        return redirect(url_for("primeira_escolha"))
    
    # 2. Lógica de Ranking
    # Esta função busca todo mundo que escolheu a cidade X (seja como op 1, 2 ou 3)
    # e ordena pela nota oficial.
    def get_ranking_cidade(cidade_nome):
        if not cidade_nome: return []
        query = """
            SELECT nome, media_final, classificacao_original,
                   lotacao_1, lotacao_2, lotacao_3,
                   CASE 
                       WHEN lotacao_1 = %s THEN '1ª Opção'
                       WHEN lotacao_2 = %s THEN '2ª Opção'
                       WHEN lotacao_3 = %s THEN '3ª Opção'
                   END as prioridade
            FROM users 
            WHERE lotacao_1 = %s OR lotacao_2 = %s OR lotacao_3 = %s
            ORDER BY media_final DESC, nome ASC
        """
        # Passamos a cidade várias vezes para preencher os %s
        cur.execute(query, (cidade_nome, cidade_nome, cidade_nome, cidade_nome, cidade_nome, cidade_nome))
        return cur.fetchall()

    # Monta o dicionário de rankings para o template
    rankings = {}
    
    if user['lotacao_1']:
        rankings['Opção 1'] = {
            'cidade': user['lotacao_1'], 
            'lista': get_ranking_cidade(user['lotacao_1'])
        }
        
    if user['lotacao_2']:
        rankings['Opção 2'] = {
            'cidade': user['lotacao_2'], 
            'lista': get_ranking_cidade(user['lotacao_2'])
        }
        
    if user['lotacao_3']:
        rankings['Opção 3'] = {
            'cidade': user['lotacao_3'], 
            'lista': get_ranking_cidade(user['lotacao_3'])
        }
    
    # 3. Ranking Geral (Opcional: Top 100 para não sobrecarregar)
    cur.execute("SELECT nome, media_final, classificacao_original FROM users ORDER BY media_final DESC LIMIT 100")
    ranking_geral = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template("dashboard.html", user=user, rankings=rankings, ranking_geral=ranking_geral)

if __name__ == "__main__":
    # Em produção, debug deve ser False
    app.run(debug=True)