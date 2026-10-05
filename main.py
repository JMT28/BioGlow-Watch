import mimetypes
import os
import json
import sqlite3
import requests
import time
import traceback

from flask import Flask, render_template, request, send_from_directory

from google import genai
from google.genai import types


# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(__name__)

print("BIOGLOW WATCH INICIADO", flush=True)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ONESIGNAL_APP_ID = os.getenv("ONESIGNAL_APP_ID")
ONESIGNAL_REST_KEY = os.getenv("ONESIGNAL_REST_KEY")


# ============================================================
# BANCO DE DADOS
# ============================================================

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
            longitude REAL,
            risco REAL
        )
    """)

    conexao.commit()
    conexao.close()


def adicionar_colunas():
    conexao = sqlite3.connect("bioglow.db")
    cursor = conexao.cursor()

    cursor.execute("PRAGMA table_info(ocorrencias)")
    colunas = [coluna[1] for coluna in cursor.fetchall()]

    if "latitude" not in colunas:
        try:
            cursor.execute("ALTER TABLE ocorrencias ADD COLUMN latitude REAL")
        except sqlite3.OperationalError:
            pass

    if "longitude" not in colunas:
        try:
            cursor.execute("ALTER TABLE ocorrencias ADD COLUMN longitude REAL")
        except sqlite3.OperationalError:
            pass

    if "risco" not in colunas:
        try:
            cursor.execute("ALTER TABLE ocorrencias ADD COLUMN risco REAL")
        except sqlite3.OperationalError:
            pass

    conexao.commit()
    conexao.close()


# Garante que o banco e as colunas existem na inicialização do módulo (funciona no Gunicorn/Render)
criar_banco()
adicionar_colunas()


# ============================================================
# ONESIGNAL
# ============================================================

def disparar_alerta_emergencia(mensagem):
    if not ONESIGNAL_APP_ID or not ONESIGNAL_REST_KEY:
        print("⚠️ Chaves do OneSignal não encontradas.", flush=True)
        return

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Basic {ONESIGNAL_REST_KEY}"
    }

    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "included_segments": ["All"],
        "headings": {"pt": "⚠️ ALERTA DE EMERGÊNCIA - BIOGLOW"},
        "contents": {"pt": mensagem}
    }

    try:
        resposta = requests.post(
            "https://onesignal.com/api/v1/notifications",
            headers=headers,
            data=json.dumps(payload),
            timeout=10
        )
        print(f"📢 Status OneSignal: {resposta.status_code}", flush=True)
    except Exception as e:
        print(f"❌ Erro no OneSignal: {repr(e)}", flush=True)


# ============================================================
# CLASSIFICAÇÃO DO RISCO
# ============================================================

def classificar_risco(risco):
    try:
        risco = float(risco)
    except (TypeError, ValueError):
        risco = 0

    if risco >= 70:
        return "Emergência", "emergencia"
    elif risco >= 50:
        return "Alerta", "alerta"
    elif risco >= 25:
        return "Atenção", "atencao"
    else:
        return "Baixo risco", "seguro"


# ============================================================
# GEMINI - ANÁLISE DA IMAGEM
# ============================================================

def analisar_imagem_com_ia(caminho_imagem):
    print("🔥 GEMINI FOI CHAMADA!", flush=True)

    chave = os.getenv("GEMINI_API_KEY")

    if not chave:
        print("❌ GEMINI_API_KEY não encontrada!", flush=True)
        return {
            "rachadura": False,
            "erosao": False,
            "agua": False,
            "falta_vegetacao": False,
            "deslizamento": False,
            "observacao": "Chave da IA não encontrada.",
            "risco": 0
        }

    try:
        client = genai.Client(api_key=chave)

        mime_type, _ = mimetypes.guess_type(caminho_imagem)
        if not mime_type:
            mime_type = "image/jpeg"

        print(f"📷 Tipo da imagem: {mime_type}", flush=True)

        with open(caminho_imagem, "rb") as arquivo:
            imagem = arquivo.read()

        print(f"📦 Imagem carregada: {len(imagem)} bytes", flush=True)

        prompt = """
Você é o sistema de análise ambiental do aplicativo BioGlow Watch.

Analise cuidadosamente a imagem enviada.

Identifique SOMENTE sinais VISÍVEIS na imagem relacionados a:

- rachaduras
- erosão
- água acumulada ou alagamento
- falta de vegetação
- sinais visíveis de deslizamento

Não invente informações.

Considere somente aquilo que pode ser observado na imagem.

Depois determine um nível de risco ambiental de 0 a 100.

Use esta escala:

0 a 24 = pouco risco
25 a 49 = atenção
50 a 69 = alerta
70 a 100 = emergência

O valor de "risco" deve obrigatoriamente ser um número entre 0 e 100.

Responda SOMENTE em JSON.

Use exatamente esta estrutura:

{
    "rachadura": false,
    "erosao": false,
    "agua": false,
    "falta_vegetacao": false,
    "deslizamento": false,
    "observacao": "Descrição curta dos sinais ambientais visíveis.",
    "risco": 0
}
"""

        for tentativa in range(1, 4):
            try:
                print(f"🤖 Tentativa Gemini {tentativa}/3...", flush=True)

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

                print("✅ Gemini respondeu!", flush=True)
                print(f"📄 Resposta do Gemini: {resposta.text}", flush=True)

                dados = json.loads(resposta.text)
                risco = dados.get("risco", 0)

                try:
                    risco = float(risco)
                except (TypeError, ValueError):
                    risco = 0

                risco = max(0, min(100, risco))
                dados["risco"] = risco

                print(f"🚨 RISCO FINAL: {risco}", flush=True)
                print(f"📝 OBSERVAÇÃO: {dados.get('observacao', '')}", flush=True)

                return dados

            except Exception as erro:
                print(f"⚠️ Tentativa {tentativa} falhou: {repr(erro)}", flush=True)
                if tentativa < 3:
                    print("⏳ Aguardando 5 segundos...", flush=True)
                    time.sleep(5)

        print("❌ Gemini não respondeu após 3 tentativas.", flush=True)
        return {
            "rachadura": False,
            "erosao": False,
            "agua": False,
            "falta_vegetacao": False,
            "deslizamento": False,
            "observacao": "A análise automática da IA não ficou disponível. É necessária análise manual.",
            "risco": 0
        }

    except Exception as e:
        print("❌ ERRO COMPLETO DO GEMINI:", flush=True)
        print(repr(e), flush=True)
        return {
            "rachadura": False,
            "erosao": False,
            "agua": False,
            "falta_vegetacao": False,
            "deslizamento": False,
            "observacao": "A análise automática da IA não ficou disponível.",
            "risco": 0
        }


# ============================================================
# CLIMA
# ============================================================

def obter_clima(lat=-22.28, lon=-42.53):
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}"
            f"&longitude={lon}"
            "&current_weather=true"
        )

        resposta = requests.get(url, timeout=5).json()
        codigo_tempo = resposta.get("current_weather", {}).get("weathercode", 0)

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
        print(f"❌ Erro ao obter clima: {repr(e)}", flush=True)
        return "🌧️<br> Indisponível"


# ============================================================
# PÁGINA INICIAL
# ============================================================

@app.route("/")
def inicio():
    try:
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
            AND longitude IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        maior_risco = conexao.execute(
            """
            SELECT MAX(risco)
            FROM ocorrencias
            """
        ).fetchone()[0]

        conexao.close()

        if maior_risco is None:
            maior_risco = 0

        status, cor_classe = classificar_risco(maior_risco)

        nomes_tipos = {
            "deslizamento": "🛘<br> Deslizamento",
            "rachadura": "🪨<br> Rachaduras",
            "erosao": "🏜️<br> Erosão",
            "alagamento": "🌊<br> Alagamento",
            "vegetacao": "🌱<br> Falta de Vegetação"
        }

        lista_riscos = [
            nomes_tipos.get(t[0], str(t[0]).capitalize())
            for t in tipos_registrados
        ]

        tipo_risco_texto = (
            ", ".join(lista_riscos)
            if lista_riscos
            else "🚫<br>Nenhum"
        )

        if (
            ultima_localizacao
            and ultima_localizacao[0] is not None
            and ultima_localizacao[1] is not None
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
            maior_risco=maior_risco,
            ocorrencias=ocorrencias
        )

    except Exception as e:
        print("=" * 50, flush=True)
        print("❌ ERRO NA ROTA /:", flush=True)
        traceback.print_exc()
        print("=" * 50, flush=True)
        return f"Erro no servidor ao carregar a página inicial: {str(e)}", 500


# ============================================================
# ONESIGNAL SERVICE WORKER
# ============================================================

@app.route("/OneSignalSDKWorker.js")
def onesignal_worker():
    return send_from_directory("static", "OneSignalSDKWorker.js")


# ============================================================
# NOVA OCORRÊNCIA
# ============================================================

@app.route("/nova-ocorrencia", methods=["GET", "POST"])
def nova_ocorrencia():
    print("📌 OCORRÊNCIA CHAMADA", flush=True)

    if request.method == "POST":
        tipo = request.form.get("tipo", "")
        descricao_usuario = request.form.get("descricao", "")
        foto = request.files.get("foto")
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")

        if not foto:
            return "Erro: nenhuma foto foi enviada.", 400

        caminho_foto = os.path.join(UPLOAD_FOLDER, foto.filename)
        foto.save(caminho_foto)

        print(f"📸 Foto salva: {caminho_foto}", flush=True)

        resultado_ia = analisar_imagem_com_ia(caminho_foto)
        parecer_ia = resultado_ia.get("observacao", "")
        nivel_risco = resultado_ia.get("risco", 0)

        try:
            nivel_risco = float(nivel_risco)
        except (TypeError, ValueError):
            nivel_risco = 0

        nivel_risco = max(0, min(100, nivel_risco))

        descricao_final = f"{descricao_usuario} (IA: {parecer_ia})"

        conexao = sqlite3.connect("bioglow.db")
        cursor = conexao.cursor()

        cursor.execute(
            """
            INSERT INTO ocorrencias
            (tipo, descricao, foto, latitude, longitude, risco)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                tipo,
                descricao_final,
                foto.filename,
                latitude,
                longitude,
                nivel_risco
            )
        )

        conexao.commit()
        conexao.close()

        print(f"💾 Ocorrência salva com risco {nivel_risco}", flush=True)

        if nivel_risco >= 70:
            disparar_alerta_emergencia(
                "Nova ocorrência de alto risco registrada no BioGlow Watch!"
            )

        return render_template(
            "resultado.html",
            tipo=tipo,
            descricao=descricao_final,
            foto=foto.filename,
            latitude=latitude,
            longitude=longitude,
            risco=nivel_risco
        )

    return render_template("nova-ocorrencia.html")


# ============================================================
# OCORRÊNCIAS
# ============================================================

@app.route("/ocorrencias")
def ocorrencias():
    conexao = sqlite3.connect("bioglow.db")
    conexao.row_factory = sqlite3.Row

    ocorrencias_dados = conexao.execute(
        "SELECT * FROM ocorrencias"
    ).fetchall()

    conexao.close()

    return render_template("ocorrencias.html", ocorrencias=ocorrencias_dados)


# ============================================================
# FOTOS
# ============================================================

@app.route("/uploads/<nome_arquivo>")
def mostrar_foto(nome_arquivo):
    return send_from_directory(UPLOAD_FOLDER, nome_arquivo)


# ============================================================
# MAPA
# ============================================================

@app.route("/mapa")
def mapa():
    return render_template("mapa.html")


# ============================================================
# INICIALIZAÇÃO LOCAL
# ============================================================

if __name__ == "__main__":
    print("✅ Banco de dados preparado.", flush=True)
    print("🚀 Servidor BioGlow iniciando...", flush=True)

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5001)),
        debug=False
    )
