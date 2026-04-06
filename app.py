from PIL import Image
import streamlit as st
import os
from dotenv import load_dotenv
import google.generativeai as genai
from fpdf import FPDF

load_dotenv()

from configs import SYSTEM_PROMPT, SAFETY_SETTINGS, GENERATION_CONFIG, MODEL_NAME

# -------------------------
# PDF
# -------------------------
def generar_pdf(texto):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=12)

    texto = texto.replace("\r", "")
    texto = texto.encode("latin-1", "replace").decode("latin-1")

    pdf.multi_cell(0, 8, texto)
    return bytes(pdf.output())

# -------------------------
# CONFIG
# -------------------------
st.set_page_config(page_title='ANALIZADOR RX', page_icon="🩺", layout="wide")

# -------------------------
# SESSION STATE
# -------------------------
if "reporte" not in st.session_state:
    st.session_state["reporte"] = None

if "image_data" not in st.session_state:
    st.session_state["image_data"] = None

if "analizado" not in st.session_state:
    st.session_state["analizado"] = False

# -------------------------
# HEADER
# -------------------------
st.markdown("""
<div style="padding:20px;border-radius:15px;background:#0B3B8C;color:white;">
<h1>Analizador RX - ARX APP</h1>
<p>Asistente clínico para análisis preliminar de radiografías mediante IA</p>
</div>
""", unsafe_allow_html=True)

# -------------------------
# MODELO
# -------------------------
API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=API_KEY)

model = genai.GenerativeModel(
    model_name=MODEL_NAME,
    safety_settings=SAFETY_SETTINGS,
    generation_config=GENERATION_CONFIG,
    system_instruction=SYSTEM_PROMPT
)

# -------------------------
# UI
# -------------------------
st.markdown("### Carga de imagen")

uploaded_file = st.file_uploader(
    "Sube una radiografía",
    type=['png', 'jpg', 'jpeg']
)

submit_btn = st.button("🩺 ANALIZAR", use_container_width=True)

# -------------------------
# MANEJO DE IMAGEN (CLAVE)
# -------------------------
if uploaded_file:
    nueva_imagen = Image.open(uploaded_file).convert("RGB")

    # Si la imagen cambió → resetear estado
    if st.session_state["image_data"] is None or nueva_imagen.tobytes() != st.session_state["image_data"].tobytes():
        st.session_state["image_data"] = nueva_imagen
        st.session_state["analizado"] = False
        st.session_state["reporte"] = None

image_data = st.session_state["image_data"]

# -------------------------
# COLUMNAS
# -------------------------
col1, col2 = st.columns([2, 4])

with col1:
    st.markdown("### Vista previa")
    if image_data:
        st.image(image_data, use_column_width=True)
    else:
        st.info("Sube una imagen")

# -------------------------
# ANÁLISIS CONTROLADO
# -------------------------
with col2:
    st.markdown("### Informe")

    if submit_btn:
        if image_data is None:
            st.warning("Primero sube una radiografía.")
            st.stop()

        # 🔥 CONTROL: evita reenvío
        if not st.session_state["analizado"]:
            with st.spinner("Analizando con IA..."):
                try:
                    content = [
                        "Analiza esta radiografía y responde únicamente en español. "
                        "Estructura la respuesta en: Hallazgos, Interpretación, Recomendaciones y Descargo de responsabilidad.",
                        image_data
                    ]

                    chat_session = model.start_chat()
                    response = chat_session.send_message(content)

                    st.session_state["reporte"] = response.text
                    st.session_state["analizado"] = True

                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.info("Esta imagen ya fue analizada. Sube otra para un nuevo análisis.")

    # -------------------------
    # MOSTRAR RESULTADO
    # -------------------------
    if st.session_state["reporte"]:
        with st.chat_message("assistant"):
            st.write(st.session_state["reporte"])

        pdf_bytes = generar_pdf(st.session_state["reporte"])

        st.download_button(
            label="📄 Descargar PDF",
            data=pdf_bytes,
            file_name="informe_rx.pdf",
            mime="application/pdf",
            use_container_width=True
        )