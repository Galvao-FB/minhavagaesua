import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
import psycopg2.extras
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "npg_R8YrbUaNDe1J"

DATABASE_URL = "postgresql://neondb_owner:npg_R8YrbUaNDe1J@ep-small-dawn-ac8dbw8e-pooler.sa-east-1.aws.neon.tech/minhavagaesua?sslmode=require&channel_binding=require"


# -------------------------------------------
# 🔧 Função de conexão
# -------------------------------------------
def get_db():
    try:
        return psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.DictCursor,
            connect_timeout=10
        )
    except Exception as e:
        print(f"Erro de conexão: {e}")
        return None


# -------------------------------------------
# 🔐 Middleware
# -------------------------------------------
def require_auth():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return None


# -------------------------------------------
# ROTAS PRINCIPAIS
# -------------------------------------------

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
            flash("Sistema indisponível.", "error")
            return render_template("login.html")

        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE n_inscricao = %s", (inscricao,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user:
            flash("Inscrição não encontrada.", "error")
            return render_template("login.html")

        # Primeiro acesso
        if user["password_hash"] is None:
            if senha == "":
                session["temp_user_id"] = user["n_inscricao"]
                return redirect(url_for("definir_senha"))
            else:
                flash("Primeiro acesso? Deixe a senha em branco.", "info")
                return render_template("login.html")

        # Login normal
        if check_password_hash(user["password_hash"], senha):
            session["user_id"] = user["n_inscricao"]
            session["nome"] = user["nome"]

            if not user.get("lotacao_1"):
                return redirect(url_for("primeira_escolha"))

            return redirect(url_for("dashboard"))
        else:
            flash("Senha incorreta.", "error")

    return render_template("login.html")


@app.route("/definir-senha", methods=["GET", "POST"])
def definir_senha():
    if "temp_user_id" not in session:
        flash("Sessão expirada.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        nova = request.form["nova_senha"]
        conf = request.form["confirma_senha"]

        if nova != conf:
            flash("As senhas não conferem.", "error")
            return render_template("definir_senha.html")

        if len(nova) < 4:
            flash("Senha muito curta.", "error")
            return render_template("definir_senha.html")

        conn = get_db()
        cur = conn.cursor()
        hashed = generate_password_hash(nova)

        cur.execute("UPDATE users SET password_hash=%s WHERE n_inscricao=%s",
                    (hashed, session["temp_user_id"]))
        conn.commit()

        user_id = session.pop("temp_user_id")
        cur.execute("SELECT nome FROM users WHERE n_inscricao=%s", (user_id,))
        nome = cur.fetchone()["nome"]

        session["user_id"] = user_id
        session["nome"] = nome

        cur.close()
        conn.close()

        flash("Senha criada com sucesso!", "success")
        return redirect(url_for("primeira_escolha"))

    return render_template("definir_senha.html")


@app.route("/primeira-escolha", methods=["GET", "POST"])
def primeira_escolha():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT lotacao FROM lotacao_vagas ORDER BY lotacao")
    cidades = [r[0] for r in cur.fetchall()]

    if request.method == "POST":
        l1 = request.form.get("lotacao_1")
        l2 = request.form.get("lotacao_2") or None
        l3 = request.form.get("lotacao_3") or None

        esc = [x for x in [l1, l2, l3] if x]

        if not l1:
            flash("A 1ª Opção é obrigatória.", "error")
        elif len(esc) != len(set(esc)):
            flash("Não repita cidades.", "error")
        else:
            cur.execute("""
                UPDATE users SET lotacao_1=%s, lotacao_2=%s, lotacao_3=%s
                WHERE n_inscricao=%s
            """, (l1, l2, l3, session["user_id"]))
            conn.commit()

            flash("Preferências salvas!", "success")
            return redirect(url_for("dashboard"))

    cur.close()
    conn.close()
    return render_template("escolhas.html", cidades=cidades, primeira_vez=True)


@app.route("/alterar-lotacao", methods=["GET", "POST"])
def alterar_lotacao():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        l1 = request.form.get("lotacao_1")
        l2 = request.form.get("lotacao_2") or None
        l3 = request.form.get("lotacao_3") or None

        esc = [x for x in [l1, l2, l3] if x]

        if not l1:
            flash("A 1ª Opção é obrigatória.", "error")
        elif len(esc) != len(set(esc)):
            flash("Não repita cidades.", "error")
        else:
            cur.execute("""
                UPDATE users SET lotacao_1=%s, lotacao_2=%s, lotacao_3=%s
                WHERE n_inscricao=%s
            """, (l1, l2, l3, session["user_id"]))
            conn.commit()

            flash("Lotações atualizadas.", "success")
            return redirect(url_for("dashboard"))

    cur.execute("SELECT lotacao FROM lotacao_vagas ORDER BY lotacao")
    cidades = [r[0] for r in cur.fetchall()]

    cur.execute("""
        SELECT lotacao_1, lotacao_2, lotacao_3 
        FROM users WHERE n_inscricao=%s
    """, (session["user_id"],))
    escolhas = cur.fetchone()

    cur.close()
    conn.close()

    return render_template("escolhas.html", cidades=cidades, primeira_vez=False,
                           escolhas=[escolhas["lotacao_1"], escolhas["lotacao_2"], escolhas["lotacao_3"]])


# ===============================================================
# 🆕 ATUALIZAÇÃO — DASHBOARD COMPLETO COM VAGAS + MINHAS OPÇÕES
# ===============================================================

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    # Usuário
    cur.execute("SELECT * FROM users WHERE n_inscricao=%s", (session["user_id"],))
    user = cur.fetchone()

    # Caso não tenha escolhido ainda
    if not user["lotacao_1"]:
        return redirect(url_for("primeira_escolha"))

    # ---- 🔹 VAGAS GERAIS ----
    cur.execute("""
        SELECT 
            lotacao,
            vagas,
            (SELECT COUNT(*) FROM users u WHERE u.lotacao_final = lotacao_vagas.lotacao) AS ocupadas
        FROM lotacao_vagas
        ORDER BY lotacao
    """)
    vagas_gerais = cur.fetchall()

    # ---- 🔹 MINHAS OPÇÕES ----
    minhas_opcoes = []
    for op in ["lotacao_1", "lotacao_2", "lotacao_3"]:
        lot = user.get(op)
        if lot:
            cur.execute("""
                SELECT 
                    lotacao,
                    vagas,
                    (SELECT COUNT(*) FROM users u WHERE u.lotacao_final = %s) AS ocupadas
                FROM lotacao_vagas
                WHERE lotacao = %s
            """, (lot, lot))
            row = cur.fetchone()
            if row:
                minhas_opcoes.append(row)

    # ---- 🔹 Rankings por cidade ----
    def get_ranking(cidade):
        cur.execute("""
            SELECT nome, media_final, classificacao_original,
                   lotacao_1, lotacao_2, lotacao_3
            FROM users
            WHERE lotacao_1=%s OR lotacao_2=%s OR lotacao_3=%s
            ORDER BY media_final DESC, nome ASC
        """, (cidade, cidade, cidade))
        return cur.fetchall()

    rankings = {}
    for i in range(1, 3+1):
        cidade = user.get(f"lotacao_{i}")
        if cidade:
            rankings[f"Opção {i}"] = {
                "cidade": cidade,
                "lista": get_ranking(cidade)
            }

    # ---- 🔹 Ranking Geral ----
    cur.execute("""
        SELECT nome, media_final, classificacao_original,
               lotacao_1, lotacao_2, lotacao_3
        FROM users
        ORDER BY media_final DESC
        LIMIT 200
    """)
    ranking_geral = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "dashboard.html",
        user=user,
        rankings=rankings,
        ranking_geral=ranking_geral,
        vagas_gerais=vagas_gerais,
        minhas_opcoes=minhas_opcoes
    )


if __name__ == "__main__":
    app.run(debug=True)
