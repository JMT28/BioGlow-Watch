from flask import Flask, render_template, request, send_from_directory
import os
import sqlite3
import requests
import json
import mimetypes

from google import genai
from google.genai import types
import math

app = Flask(__name__)
print("foi")

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def criar_banco():
    conexao = sqlite3.connect("bioglow.db")
    cursor = conexao.cursor()

ONESIGNAL_APP_ID = os.getenv("ONESIGNAL_APP_ID")
ONESIGNAL_REST_KEY = os.getenv("ONESIGNAL_REST_KEY")

def disparar_alerta_emergencia(mensagem):
    if not ONESIGNAL_APP_ID or not ONESIGNAL_REST_KEY:
        print("Chaves do OneSignal não configuradas.")
        return

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Basic {ONESIGNAL_REST_KEY}"
    }

    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "included_segments": ["All"], # Envia para todos os inscritos
        "headings": {"pt": "⚠️ ALERTA DE EMERGÊNCIA - BIOGLOW"},
        "contents": {"pt": mensagem},
        "chrome_web_icon": "https://seu-app.onrender.com/static/logotipo2.png"
    }

    try:
        resposta = requests.post(
            "https://onesignal.com/api/v1/notifications",
            headers=headers,
            data=json.dumps(payload),
            timeout=10
        )
        print(f"Notificação disparada: {resposta.status_code} - {resposta.text}")
    except Exception as e:
        print(f"Erro ao enviar notificação OneSignal: {e}")
    
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

import time
import mimetypes
import json
import os
from google import genai
from google.genai import types

def analisar_imagem_com_ia(caminho_imagem):
    print("GEMINI FOI CHAMADA!", flush=True)

    chave = os.getenv("GEMINI_API_KEY")

    if not chave:
        return {"observacao": "Chave da IA não encontrada.", "risco": 0}

    client = genai.Client(api_key=chave)

    mime_type, _ = mimetypes.guess_type(caminho_imagem)
    if not mime_type:
        mime_type = "image/webp"

    with open(caminho_imagem, "rb") as arquivo:
        imagem = arquivo.read()

    prompt = """
Analise esta imagem para o BioGlow Watch.

Identifique somente sinais VISÍVEIS relacionados ao ambiente:
- rachaduras
- erosão
- água acumulada ou alagamento
- falta de vegetação
- sinais visíveis de deslizamento

Calcule uma nota de risco ambiental numérico de 0 a 100 baseando-se na gravidade dos problemas encontrados (0 = sem perigo, 100 = risco extremo de desastre).

Responda EXCLUSIVAMENTE em formato JSON:
{
  "rachadura": false,
  "erosao": false,
  "agua": false,
  "falta_vegetacao": false,
  "deslizamento": false,
  "observacao": "descrição curta",
  "risco": 50
}
"""

    # Tenta até 3 vezes em caso de erro 503 (Servidor Ocupado)
    tentativas = 3
    for tentativa in range(tentativas):
        try:
            resposta = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=[
                    types.Part.from_bytes(
                        data=imagem,
                        mime_type=mime_type
                    ),
                    prompt
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

            dados = json.loads(resposta.text)
            return dados

        except Exception as e:
            print(f"Tentativa {tentativa + 1} falhou. Erro: {repr(e)}")
            if tentativa < tentativas - 1:
                time.sleep(2)  # Aguarda 2 segundos antes de tentar novamente
            else:
                return {
                    "observacao": "Serviço de IA instável no momento. Tente novamente em instantes.",
                    "risco": 0
                }

def obter_clima(lat=-22.28, lon=-42.53):
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


@app.route("/OneSignalSDKWorker.js")
def onesignal_worker():
    return send_from_directory("static", "OneSignalSDKWorker.js")

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
        for t in tipos_registrados]

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
    print("OCORRENCIA CHAMADA")

    if request.method == "POST":
        tipo = request.form["tipo"]
        descricao_usuario = request.form["descricao"]
        foto = request.files["foto"]

        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")

        # 1. Monta o caminho e salva a imagem corretamente
        caminho_foto = os.path.join(UPLOAD_FOLDER, foto.filename)
        foto.save(caminho_foto)

        # 2. Executa a análise da imagem usando a IA do Gemini
        resultado_ia = analisar_imagem_com_ia(caminho_foto)
        nivel_risco = resultado_ia.get("risco", 0)
        observacao_ia = resultado_ia.get("observacao", "")

        # 3. Salva os dados da ocorrência no banco de dados SQLite
        conexao = sqlite3.connect("bioglow.db")
        cursor = conexao.cursor()
        cursor.execute(
            """
            INSERT INTO ocorrencias (tipo, descricao, foto, latitude, longitude, risco, observacao_ia)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tipo, descricao_usuario, foto.filename, latitude, longitude, nivel_risco, observacao_ia)
        )
        conexao.commit()

        # 4. Consulta a quantidade atual de registros para a regra do alerta
        total_ocorrencias = cursor.execute("SELECT COUNT(*) FROM ocorrencias").fetchone()[0]
        conexao.close()

        # 5. Se atingiu o nível de emergência, dispara o alerta via OneSignal
        if total_ocorrencias > 7 or nivel_risco >= 80:
            msg = f"Atenção! Uma nova ocorrência de {tipo} foi registrada. O nível da região mudou para EMERGÊNCIA."
            disparar_alerta_emergencia(msg)

        return redirect(url_for("index"))

    return render_template("nova-ocorrencia.html")


@app.route("/ocorrencias")
def ocorrencias():
    conexao = sqlite3.connect("bioglow.db")
    conexao.row_factory = sqlite3.Row

    ocorrencias = conexao.execute(
        "SELECT * FROM ocorrencias"
    ).fetchall()

    conexao.close()

    return render_template(
        "ocorrencias.html",
        ocorrencias=ocorrencias
    )


@app.route("/uploads/<nome_arquivo>")
def mostrar_foto(nome_arquivo):
    return send_from_directory(
        UPLOAD_FOLDER,
        nome_arquivo
    )


@app.route("/mapa")
def mapa():
    return render_template("mapa.html")


if __name__ == "__main__":
    criar_banco()
    adicionar_localizacao()

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5001)),
        debug=False
    )
