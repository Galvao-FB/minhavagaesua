import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
import psycopg2.extras
from werkzeug.security import check_password_hash, generate_password_hash

# --- CONFIGURAÇÕES DA APLICAÇÃO ---
app = Flask(__name__)

# Chave secreta robusta
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a5f2e8b0c4d9f7a1b3c5d7e9f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0')

DATABASE_URL = os.environ.get('DATABASE_URL')

# --- Funções de Banco de Dados ---
def get_db():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor, connect_timeout=10)
    except Exception as e:
        print(f"Erro de conexão: {e}")
        return None

# --- Middleware de Autenticação ---
def require_auth():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return None

# -------------------------------------------------------------------------
# ROTAS
# -------------------------------------------------------------------------

@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        inscricao = request.form.get("inscricao", "").strip()
        senha = request.form.get("senha", "").strip()
        
        conn = get_db()
        if not conn:
            flash("Sistema indisponível. Tente mais tarde.", "error")
            return render_template("login.html")
            
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE n_inscricao = %s", (inscricao,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user:
            flash("Inscrição não encontrada.", "error")
            return render_template("login.html")

        if user['password_hash'] is None:
            if senha == "":
                session['temp_user_id'] = user['n_inscricao']
                return redirect(url_for("definir_senha"))
            else:
                flash("Primeiro acesso? Deixe a senha em branco.", "info")
                return render_template("login.html")

        if check_password_hash(user['password_hash'], senha):
            session['user_id'] = user['n_inscricao']
            session['nome'] = user['nome']
            
            if not user.get('lotacao_1'):
                return redirect(url_for("primeira_escolha"))
            
            return redirect(url_for("dashboard"))
        else:
            flash("Senha incorreta.", "error")

    return render_template("login.html")

@app.route("/definir-senha", methods=["GET", "POST"])
def definir_senha():
    if 'temp_user_id' not in session:
        flash("Sessão expirada. Faça login novamente.", "error")
        return redirect(url_for("login"))
    
    if request.method == "POST":
        nova_senha = request.form.get("nova_senha", "")
        confirma_senha = request.form.get("confirma_senha", "")
        
        if nova_senha != confirma_senha:
            flash("As senhas não conferem.", "error")
            return render_template("definir_senha.html")
            
        if len(nova_senha) < 4:
            flash("A senha é muito curta.", "error")
            return render_template("definir_senha.html")
        
        conn = get_db()
        if not conn: return render_template("definir_senha.html")
            
        try:
            cur = conn.cursor()
            hashed = generate_password_hash(nova_senha)
            cur.execute("UPDATE users SET password_hash = %s WHERE n_inscricao = %s", 
                       (hashed, session['temp_user_id']))
            conn.commit()
            
            user_id = session.pop('temp_user_id')
            cur.execute("SELECT nome FROM users WHERE n_inscricao = %s", (user_id,))
            user_data = cur.fetchone()
            
            session['user_id'] = user_id
            session['nome'] = user_data['nome']
            
            flash("Senha criada com sucesso!", "success")
            return redirect(url_for("primeira_escolha"))
            
        except Exception as e:
            conn.rollback()
            print(f"Erro ao salvar senha: {e}")
            flash("Erro ao salvar senha.", "error")
            return render_template("definir_senha.html")
        finally:
            if conn: conn.close()

    return render_template("definir_senha.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/primeira-escolha", methods=["GET", "POST"])
def primeira_escolha():
    if "user_id" not in session: return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT lotacao FROM lotacao_vagas ORDER BY lotacao")
    cidades = [r[0] for r in cur.fetchall()]
    
    if request.method == "POST":
        l1 = request.form.get("lotacao_1")
        l2 = request.form.get("lotacao_2") or None
        l3 = request.form.get("lotacao_3") or None
        
        escolhas = [x for x in [l1, l2, l3] if x]
        if not l1:
            flash("A 1ª Opção é obrigatória.", "error")
        elif len(escolhas) != len(set(escolhas)):
             flash("Não repita cidades.", "error")
        else:
            try:
                cur.execute("""
                    UPDATE users SET lotacao_1=%s, lotacao_2=%s, lotacao_3=%s 
                    WHERE n_inscricao=%s
                """, (l1, l2, l3, session['user_id']))
                conn.commit()
                flash("Preferências salvas!", "success")
                return redirect(url_for("dashboard"))
            except Exception as e:
                conn.rollback()
                flash("Erro ao salvar.", "error")

    cur.close()
    conn.close()
    return render_template("escolhas.html", cidades=cidades, primeira_vez=True, escolhas=[None]*3)

@app.route("/alterar-lotacao", methods=["GET", "POST"])
def alterar_lotacao():
    if "user_id" not in session: return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == "POST":
        l1 = request.form.get("lotacao_1")
        l2 = request.form.get("lotacao_2") or None
        l3 = request.form.get("lotacao_3") or None
        
        escolhas = [x for x in [l1, l2, l3] if x]
        if not l1:
            flash("A 1ª Opção é obrigatória.", "error")
        elif len(escolhas) != len(set(escolhas)):
            flash("Não repita cidades.", "error")
        else:
            try:
                cur.execute("""
                    UPDATE users SET lotacao_1=%s, lotacao_2=%s, lotacao_3=%s 
                    WHERE n_inscricao=%s
                """, (l1, l2, l3, session['user_id']))
                conn.commit()
                flash("Lotações atualizadas.", "success")
                return redirect(url_for("dashboard"))
            except:
                conn.rollback()
                flash("Erro ao atualizar.", "error")

    cur.execute("SELECT lotacao FROM lotacao_vagas ORDER BY lotacao")
    cidades = [r[0] for r in cur.fetchall()]
    
    cur.execute("SELECT lotacao_1, lotacao_2, lotacao_3 FROM users WHERE n_inscricao=%s", (session['user_id'],))
    user_row = cur.fetchone()
    
    cur.close()
    conn.close()
    return render_template("escolhas.html", cidades=cidades, primeira_vez=False, 
                           escolhas=[user_row['lotacao_1'], user_row['lotacao_2'], user_row['lotacao_3']])

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session: return redirect(url_for("login"))
    
    conn = get_db()
    if not conn: return "Erro de conexão"
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM users WHERE n_inscricao=%s", (session['user_id'],))
    user = cur.fetchone()
    
    if not user or not user['lotacao_1']:
        return redirect(url_for("primeira_escolha"))
    
    # --- 1. Mapa de Vagas (Essencial para o template novo) ---
    cur.execute("SELECT lotacao, vagas FROM lotacao_vagas")
    # Cria um dicionário { 'Cidade A': 10, 'Cidade B': 5 ... }
    vagas_map = {r['lotacao']: r['vagas'] for r in cur.fetchall()}
    
    # --- 2. Função de Ranking ---
    def get_ranking(cidade):
        if not cidade: return []
        cur.execute("""
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
        """, (cidade, cidade, cidade, cidade, cidade, cidade))
        return cur.fetchall()

    # --- 3. Monta os Rankings das 3 Opções ---
    rankings = {}
    for i in range(1, 4):
        cidade = user.get(f'lotacao_{i}')
        if cidade:
            rankings[f'Opção {i}'] = {
                'cidade': cidade,
                'vagas': vagas_map.get(cidade, 0), # IMPORTANTE: Passa o número de vagas
                'lista': get_ranking(cidade)
            }
    
    # --- 4. Ranking Geral ---
    cur.execute("""
        SELECT nome, media_final, classificacao_original, 
               lotacao_1, lotacao_2, lotacao_3 
        FROM users ORDER BY media_final DESC LIMIT 200
    """)
    ranking_geral = cur.fetchall()
    
    cur.close()
    conn.close()
    
    # IMPORTANTE: Passa todas as variáveis que o template dashboard.html espera
    return render_template("dashboard.html", 
                           user=user, 
                           rankings=rankings, 
                           ranking_geral=ranking_geral, 
                           vagas_map=vagas_map) # Opcional, mas útil se o template usar

if __name__ == "__main__":
    app.run(debug=True)
