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

        # Primeiro Acesso
        if user['password_hash'] is None:
            if senha == "":
                session['temp_user_id'] = user['n_inscricao']
                return redirect(url_for("definir_senha"))
            else:
                flash("Primeiro acesso? Deixe a senha em branco.", "info")
                return render_template("login.html")

        # Login Normal
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
            
            # Salva senha
            cur.execute("UPDATE users SET password_hash = %s WHERE n_inscricao = %s", 
                       (hashed, session['temp_user_id']))
            conn.commit()
            
            # Recupera dados para login automático
            user_id = session.pop('temp_user_id')
            cur.execute("SELECT nome FROM users WHERE n_inscricao = %s", (user_id,))
            user_data = cur.fetchone()
            
            # Loga o usuário
            session['user_id'] = user_id
            session['nome'] = user_data['nome']
            
            flash("Senha criada com sucesso!", "success")
            return redirect(url_for("primeira_escolha"))
            
        except Exception as e:
            conn.rollback()
            print(f"Erro ao salvar senha: {e}")
            flash("Erro ao salvar senha. Tente novamente.", "error")
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
                flash("Erro ao salvar. Tente novamente.", "error")

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
    
    # Mapa de Vagas
    cur.execute("SELECT lotacao, vagas FROM lotacao_vagas")
    vagas_map = {r['lotacao']: r['vagas'] for r in cur.fetchall()}
    
    def get_ranking(cidade):
        if not cidade: return []
        # Busca todos que escolheram a cidade em qualquer opção, ordenado por nota
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

    rankings = {}
    # Cria os dados para as 3 abas
    for i in range(1, 4):
        cidade = user.get(f'lotacao_{i}')
        if cidade:
            rankings[f'Opção {i}'] = {
                'cidade': cidade,
                'vagas': vagas_map.get(cidade, 0),
                'lista': get_ranking(cidade)
            }
    
    # Ranking Geral
    cur.execute("""
        SELECT nome, media_final, classificacao_original, 
               lotacao_1, lotacao_2, lotacao_3 
        FROM users ORDER BY media_final DESC LIMIT 200
    """)
    ranking_geral = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template("dashboard.html", user=user, rankings=rankings, ranking_geral=ranking_geral)

if __name__ == "__main__":
    app.run(debug=True)
