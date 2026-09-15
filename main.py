from flask import Flask, render_template, request, send_from_directory
import os
import sqlite3
import requests  # Para buscar o clima
from PIL import Image

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Substitua pela sua chave do Google AI Studio


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
        cursor.execute("ALTER TABLE ocorrencias ADD COLUMN latitude REAL")
        cursor.execute("ALTER TABLE ocorrencias ADD COLUMN longitude REAL")
    except sqlite3.OperationalError:
        pass  # Colunas já existem

    conexao.commit()
    conexao.close()


def analisar_imagem_com_ia(caminho_imagem):
    return (
        50,
        "Risco Moderado",
        "Análise por IA indisponível no momento. Análise manual necessária"
    )

        if len(partes) >= 3:
            risco = int(partes[0].strip())
            nivel = partes[1].strip()
            parecer = partes[2].strip()
            return risco, nivel, parecer

    except Exception as e:
        print(f"Erro na análise de IA: {e}")

    return 50, "Risco Moderado", "Análise manual necessária."


def obter_clima(lat=-22.28, lon=-42.53):
    """
    Busca a condição meteorológica atual via Open-Meteo API.
    """
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        resposta = requests.get(url, timeout=5).json()
        codigo_tempo = resposta.get("current_weather", {}).get("weathercode", 0)

        # Mapeamento dos códigos WMO da Open-Meteo
        if codigo_tempo in [0, 1]:
            return "☀️<br> Ensolarado"
        elif codigo_tempo in [2, 3]:
            return "☁️<br> Nublado"
        elif codigo_tempo in [51, 53, 55, 61, 63, 80]:
            return "🌧️<br>Chovendo"
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

    total = conexao.execute("SELECT COUNT(*) FROM ocorrencias").fetchone()[0]
    ocorrencias = conexao.execute("SELECT * FROM ocorrencias").fetchall()

    tipos_registrados = conexao.execute(
        "SELECT DISTINCT tipo FROM ocorrencias WHERE tipo IS NOT NULL AND tipo != ''"
    ).fetchall()

    # Busca a última ocorrência para pegar a localização atual do mapa
    ultima_localizacao = conexao.execute(
        "SELECT latitude, longitude FROM ocorrencias WHERE latitude IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()

    conexao.close()

    nomes_tipos = {
        "deslizamento":"🛘<br> Deslizamento",
        "rachadura":"🪨<br> Rachaduras",
        "erosao": "🏜️<br> Erosão",
        "alagamento":"🌊<br> Alagamento",
        "vegetacao": "🌱<br> Falta de Vegetação"
    }

    lista_riscos = [nomes_tipos.get(t[0], t[0].capitalize()) for t in tipos_registrados]

    if total <= 2:
        status = "Baixo risco"
        cor_classe = "seguro"     # Ícone VERDE (#28a745)
    elif total <= 5:
        status = "Atenção"
        cor_classe = "atencao"    # Ícone AMARELO (#ffc107)
    elif total <= 7:
        status = "Alerta"
        cor_classe = "alerta"     # Ícone LARANJA (#ffa900)
    else:
        status = "Emergência"
        cor_classe = "emergencia" # Ícone VERMELHO (#dc3545)


    tipo_risco_texto = ", ".join(lista_riscos) if lista_riscos else "🚫<br>Nenhum"

    # Se houver ocorrências cadastradas, usa as coordenadas da última cadastrada para o clima
    if ultima_localizacao and ultima_localizacao[0] and ultima_localizacao[1]:
        clima_atual = obter_clima(ultima_localizacao[0], ultima_localizacao[1])
    else:
        clima_atual = obter_clima()

    return render_template(
        "index.html",
        status=status,
        cor_classe=cor_classe,tipo_risco_texto=tipo_risco_texto,clima_atual=clima_atual,
        total=total,
        ocorrencias=ocorrencias
    )


@app.route("/nova-ocorrencia", methods=["GET", "POST"])
def nova_ocorrencia():
    if request.method == "POST":
        tipo = request.form["tipo"]
        descricao_usuario = request.form["descricao"]
        foto = request.files["foto"]
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")

        # 1. Salva a foto na pasta 'uploads'
        caminho_foto = os.path.join(UPLOAD_FOLDER, foto.filename)
        foto.save(caminho_foto)

        # 2. IA analisa a imagem salva
        risco, nivel, parecer_ia = analisar_imagem_com_ia(caminho_foto)

        # Junta a descrição do usuário com o laudo da IA
        descricao_final = f"{descricao_usuario} (IA: {parecer_ia})"

        # 3. Salva no banco de dados SQLite
        conexao = sqlite3.connect("bioglow.db")
        cursor = conexao.cursor()

        cursor.execute("""
            INSERT INTO ocorrencias
            (tipo, descricao, foto, latitude, longitude)
            VALUES (?, ?, ?, ?, ?)
        """, (tipo, descricao_final, foto.filename, latitude, longitude))

        conexao.commit()
        conexao.close()

        # 4. Retorna a tela de resultado
        return render_template(
            "resultado.html",
            tipo=tipo,descricao=descricao_final,foto=foto.filename,
            latitude=latitude,
            longitude=longitude,
            risco=risco,
            nivel=nivel
        )

    return render_template("nova-ocorrencia.html")


@app.route("/ocorrencias")
def ocorrencias():
    conexao = sqlite3.connect("bioglow.db")
    conexao.row_factory = sqlite3.Row

    ocorrencias = conexao.execute("SELECT * FROM ocorrencias").fetchall()
    conexao.close()

    return render_template("ocorrencias.html", ocorrencias=ocorrencias)


@app.route("/uploads/<nome_arquivo>")
def mostrar_foto(nome_arquivo):
    return send_from_directory(UPLOAD_FOLDER, nome_arquivo)


@app.route("/mapa")
def mapa():
    return render_template("mapa.html")


if __name__ == "__main__":
    criar_banco()
    adicionar_localizacao()

app.run(
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 5004)),
    debug=False
)