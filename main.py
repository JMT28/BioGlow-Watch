from flask import Flask, render_template, request, send_from_directory
import os
import sqlite3
import requests

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def criar_banco():
    conexao = sqlite3.connect("bioglow.db")
    cursor = conexao.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ocorrencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            descricao TEXT,
            foto TEXT,
            latitude REAL,
            longitude REAL
        )
    """)

    conexao.commit()
    conexao.close()


def adicionar_localizacao():
    conexao = sqlite3.connect("bioglow.db")
    cursor = conexao.cursor()

    try:
        cursor.execute(
            "ALTER TABLE ocorrencias ADD COLUMN latitude REAL"
        )
        cursor.execute(
            "ALTER TABLE ocorrencias ADD COLUMN longitude REAL"
        )
    except sqlite3.OperationalError:
        pass

    conexao.commit()
    conexao.close()


def analisar_imagem_com_ia(caminho_imagem):
    """
    IA temporariamente desativada.
    Quando tivermos uma API configurada, colocaremos
    a análise da imagem aqui.
    """
    return (
        50,
        "Risco Moderado",
        "Análise por IA indisponível no momento. "
        "Análise manual necessária."
    )


def obter_clima(lat=-22.28, lon=-42.53):
    """
    Busca a condição meteorológica atual
    através da API Open-Meteo.
    """
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}"
            f"&longitude={lon}"
            "&current_weather=true"
        )

        resposta = requests.get(url, timeout=5).json()

        codigo_tempo = resposta.get(
            "current_weather", {}
        ).get("weathercode", 0)

        if codigo_tempo in [0, 1]:
            return "☀️<br> Ensolarado"

        elif codigo_tempo in [2, 3]:
            return "☁️<br> Nublado"

        elif codigo_tempo in [51, 53, 55, 61, 63, 80]:
            return "🌧️<br> Chovendo"

        elif codigo_tempo in [65, 81, 82, 95, 96, 99]:
            return "⛈️<br> Chuva Forte"

        else:
            return "🌤️<br> Parcialmente Nublado"

    except Exception as e:
        print(f"Erro ao obter clima: {e}")
        return "🌧️<br> Indisponível"


@app.route("/")
def inicio():
    conexao = sqlite3.connect("bioglow.db")

    total = conexao.execute(
        "SELECT COUNT(*) FROM ocorrencias"
    ).fetchone()[0]

    ocorrencias = conexao.execute(
        "SELECT * FROM ocorrencias"
    ).fetchall()

    tipos_registrados = conexao.execute(
        """
        SELECT DISTINCT tipo
        FROM ocorrencias
        WHERE tipo IS NOT NULL
        AND tipo != ''
        """
    ).fetchall()

    ultima_localizacao = conexao.execute(
        """
        SELECT latitude, longitude
        FROM ocorrencias
        WHERE latitude IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    conexao.close()

    nomes_tipos = {
        "deslizamento": "🛘<br> Deslizamento",
        "rachadura": "🪨<br> Rachaduras",
        "erosao": "🏜️<br> Erosão",
        "alagamento": "🌊<br> Alagamento",
        "vegetacao": "🌱<br> Falta de Vegetação"
    }

    lista_riscos = [
        nomes_tipos.get(
            t[0],
            t[0].capitalize()
        )
        for t in tipos_registrados
    ]

    if total <= 2:
        status = "Baixo risco"
        cor_classe = "seguro"

    elif total <= 5:
        status = "Atenção"
        cor_classe = "atencao"

    elif total <= 7:
        status = "Alerta"
        cor_classe = "alerta"

    else:
        status = "Emergência"
        cor_classe = "emergencia"

    tipo_risco_texto = (
        ", ".join(lista_riscos)
        if lista_riscos
        else "🚫<br>Nenhum"
    )

    if (
        ultima_localizacao
        and ultima_localizacao[0]
        and ultima_localizacao[1]
    ):
        clima_atual = obter_clima(
            ultima_localizacao[0],
            ultima_localizacao[1]
        )
    else:
        clima_atual = obter_clima()

    return render_template(
        "index.html",
        status=status,
        cor_classe=cor_classe,
        tipo_risco_texto=tipo_risco_texto,
        clima_atual=clima_atual,
        total=total,
        ocorrencias=ocorrencias
    )


@app.route("/nova-ocorrencia", methods=["GET", "POST"])
def nova_ocorrencia():

    if request.method == "POST":

        tipo = request.form["