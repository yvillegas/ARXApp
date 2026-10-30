from PIL import Image, ImageDraw, ImageFont
import streamlit as st
import os
import re
import json
import io
import uuid
import time
from dotenv import load_dotenv
import google.generativeai as genai
from fpdf import FPDF
from fpdf.enums import XPos, YPos
# pyrefly: ignore [missing-import]
from supabase import create_client

load_dotenv()

from configs import SYSTEM_PROMPT, SAFETY_SETTINGS, GENERATION_CONFIG, MODEL_NAME

# -------------------------
# SUPABASE
# -------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase_client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        # No bloqueamos el inicio de la app, solo advertimos
        pass

def subir_imagen_supabase(image, file_name):
    if supabase_client:
        try:
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)
            
            supabase_client.storage.from_("radiology-images").upload(
                path=file_name,
                file=buffer.getvalue(),
                file_options={"content-type": "image/png", "upsert": "true"}
            )
            url = supabase_client.storage.from_("radiology-images").get_public_url(file_name)
            return url
        except Exception as e:
            st.error(f"Error al subir imagen a Supabase Storage: {e}")
    return None

def guardar_reporte(image_name, report_text, anatomy_region, original_image_url=None, annotated_image_url=None, classification=None):
    if supabase_client:
        try:
            data = {
                "image_name": image_name,
                "report_text": report_text,
                "anatomy_region": anatomy_region,
                "original_image_url": original_image_url,
                "annotated_image_url": annotated_image_url,
                "classification": classification
            }
            supabase_client.table("radiology_reports").insert(data).execute()
        except Exception as e:
            st.error(f"Error al guardar el reporte en Supabase: {e}")

def obtener_historial():
    if supabase_client:
        try:
            response = supabase_client.table("radiology_reports").select("*").order("created_at", desc=True).limit(20).execute()
            return response.data
        except Exception as e:
            st.error(f"Error al cargar el historial desde Supabase: {e}")
    return []

# -------------------------
# DIBUJO DE ANOMALÍAS (BOXES)
# -------------------------
def extraer_reporte_y_cajas(texto_completo):
    """
    Extrae el informe clínico y las cajas delimitadoras de la respuesta de Gemini.
    Retorna (texto_limpio, lista_cajas)
    """
    patron_json = r"```json\s*(\[\s*\{.*?\}\s*\])\s*```"
    match = re.search(patron_json, texto_completo, re.DOTALL)
    
    if match:
        json_str = match.group(1)
        texto_limpio = texto_completo.replace(match.group(0), "").strip()
        try:
            cajas = json.loads(json_str)
            return texto_limpio, cajas
        except Exception:
            return texto_completo, []
            
    patron_generico = r"```\s*(\[\s*\{.*?\}\s*\])\s*```"
    match_gen = re.search(patron_generico, texto_completo, re.DOTALL)
    if match_gen:
        json_str = match_gen.group(1)
        texto_limpio = texto_completo.replace(match_gen.group(0), "").strip()
        try:
            cajas = json.loads(json_str)
            return texto_limpio, cajas
        except Exception:
            pass
            
    return texto_completo, []

def dibujar_cajas(imagen, cajas):
    if not cajas:
        return imagen
    
    imagen_anotada = imagen.copy()
    dibujo = ImageDraw.Draw(imagen_anotada)
    ancho, alto = imagen_anotada.size
    
    try:
        fuente = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", max(12, int(ancho / 45)))
    except IOError:
        try:
            fuente = ImageFont.truetype("Arial.ttf", max(12, int(ancho / 45)))
        except IOError:
            fuente = ImageFont.load_default()
            
    for caja in cajas:
        box = caja.get("box_2d")
        label = caja.get("label", "Anomalía")
        
        if isinstance(box, list) and len(box) == 4:
            ymin = int(box[0] * alto / 1000)
            xmin = int(box[1] * ancho / 1000)
            ymax = int(box[2] * alto / 1000)
            xmax = int(box[3] * ancho / 1000)
            
            grosor = max(3, int(ancho / 180))
            
            dibujo.rectangle([xmin, ymin, xmax, ymax], outline="#FF3B30", width=grosor)
            
            try:
                # Pillow 10+
                left, top, right, bottom = dibujo.textbbox((xmin, ymin), label, font=fuente)
                dibujo.rectangle([xmin, ymin - (bottom - top) - 6, right + 6, ymin], fill="#FF3B30")
                dibujo.text((xmin + 3, ymin - (bottom - top) - 4), label, fill="white", font=fuente)
            except AttributeError:
                # Pillow < 10 fallback
                try:
                    text_width, text_height = dibujo.textsize(label, font=fuente)
                    dibujo.rectangle([xmin, ymin - text_height - 6, xmin + text_width + 6, ymin], fill="#FF3B30")
                    dibujo.text((xmin + 3, ymin - text_height - 4), label, fill="white", font=fuente)
                except:
                    dibujo.text((xmin, max(0, ymin - 15)), label, fill="#FF3B30")
                    
    return imagen_anotada

# -------------------------
# PDF
# -------------------------
def generar_pdf(texto, region="No especificada"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.set_text_color(11, 59, 140)  # Azul médico (#0B3B8C)
    pdf.cell(0, 10, "ARX APP · INFORME RADIOLÓGICO", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    
    pdf.set_font("Helvetica", style="I", size=10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"Región Anatómica: {region} | Documento técnico preliminar", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    
    # Línea divisoria
    pdf.set_draw_color(11, 59, 140)
    pdf.set_line_width(0.5)
    pdf.line(10, 28, 200, 28)
    pdf.ln(10)
    
    # Contenido
    pdf.set_font("Helvetica", size=11)
    pdf.set_text_color(15, 23, 42)  # Oscuro (#0F172A)
    
    texto = texto.replace("\r", "")
    texto = texto.encode("latin-1", "replace").decode("latin-1")
    
    pdf.multi_cell(0, 7, texto)
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

if "reporte_limpio" not in st.session_state:
    st.session_state["reporte_limpio"] = None

if "cajas" not in st.session_state:
    st.session_state["cajas"] = []

if "image_data" not in st.session_state:
    st.session_state["image_data"] = None

if "nombre_archivo" not in st.session_state:
    st.session_state["nombre_archivo"] = "radiografía.png"

if "ultimo_archivo_nombre" not in st.session_state:
    st.session_state["ultimo_archivo_nombre"] = None

if "ultimo_archivo_tamanio" not in st.session_state:
    st.session_state["ultimo_archivo_tamanio"] = None

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
# SIDEBAR / CONFIGURACIONES
# -------------------------
st.sidebar.markdown("""
<div style="padding:10px;border-radius:10px;background:#f0f4f9;border:1px solid #dcdcdc;margin-bottom:15px;text-align:center;">
    <h4 style="margin:0;color:#0B3B8C;">🩺 ARXAPP</h4>
    <small style="color:#666;">Panel de Control Clínico</small>
</div>
""", unsafe_allow_html=True)

# Selector de Región Anatómica
region_anatomica = st.sidebar.selectbox(
    "Región Anatómica de Análisis",
    ["Tórax", "Extremidad Superior", "Extremidad Inferior", "Columna", "Abdomen", "Pelvis / Cadera", "No especificada"],
    index=0
)

# Estado de la conexión
st.sidebar.markdown("---")
st.sidebar.markdown("### Estado del Sistema")
if supabase_client:
    st.sidebar.success("Base de datos: Conectada 🗄️")
else:
    st.sidebar.warning("Base de datos: Inactiva ⚠️\n\nConfigura `SUPABASE_URL` y `SUPABASE_KEY` en tu `.env` para activar el historial.")

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
# MAIN TABS
# -------------------------
tab_analisis, tab_historial = st.tabs(["🩺 Analizar Radiografía", "🕒 Historial Clínico"])

# -------------------------
# PESTAÑA: ANALIZAR IMAGEN
# -------------------------
with tab_analisis:
    st.markdown("### Carga de imagen")

    uploaded_file = st.file_uploader(
        "Sube una radiografía",
        type=['png', 'jpg', 'jpeg'],
        key="analisis_uploader"
    )

    submit_btn = st.button("🩺 ANALIZAR", use_container_width=True)

    # -------------------------
    # MANEJO DE IMAGEN (CLAVE)
    # -------------------------
    if uploaded_file:
        nombre_actual = uploaded_file.name
        tamanio_actual = uploaded_file.size

        # Si la imagen cambió → resetear estado
        if (st.session_state["image_data"] is None or 
            st.session_state["ultimo_archivo_nombre"] != nombre_actual or 
            st.session_state["ultimo_archivo_tamanio"] != tamanio_actual):
            
            uploaded_file.seek(0)
            st.session_state["image_data"] = Image.open(uploaded_file).convert("RGB")
            st.session_state["nombre_archivo"] = nombre_actual
            st.session_state["ultimo_archivo_nombre"] = nombre_actual
            st.session_state["ultimo_archivo_tamanio"] = tamanio_actual
            st.session_state["analizado"] = False
            st.session_state["reporte"] = None
            st.session_state["reporte_limpio"] = None
            st.session_state["cajas"] = []

    image_data = st.session_state["image_data"]

    # -------------------------
    # COLUMNAS
    # -------------------------
    col1, col2 = st.columns([2, 4])

    with col1:
        st.markdown("### Vista previa")
        if image_data:
            # Dibujar cajas dinámicamente si el análisis se completó y se encontraron anomalías
            if st.session_state["analizado"] and st.session_state["cajas"]:
                ver_anomalias = st.checkbox("Ver anomalías detectadas 🟥", value=True)
                if ver_anomalias:
                    imagen_mostrar = dibujar_cajas(image_data, st.session_state["cajas"])
                else:
                    imagen_mostrar = image_data
            else:
                imagen_mostrar = image_data
                
            st.image(imagen_mostrar, use_column_width=True)
        else:
            st.info("Sube una imagen para comenzar.")

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
                with st.spinner("Analizando con IA (Gemini Pro)..."):
                    try:
                        content = [
                            f"Analiza esta imagen de rayos X de la región '{region_anatomica}' y genera el informe estructurado siguiendo estrictamente el protocolo médico definido en las instrucciones del sistema.",
                            image_data
                        ]

                        chat_session = model.start_chat()
                        response = chat_session.send_message(content)

                        raw_text = response.text
                        st.session_state["reporte"] = raw_text
                        
                        # Extraer el reporte limpio de texto y el JSON de cajas
                        reporte_limpio, cajas = extraer_reporte_y_cajas(raw_text)
                        st.session_state["reporte_limpio"] = reporte_limpio
                        st.session_state["cajas"] = cajas
                        
                        st.session_state["analizado"] = True

                        # Subir imágenes a Supabase Storage
                        original_image_url = None
                        annotated_image_url = None
                        if supabase_client:
                            unique_id = uuid.uuid4().hex[:8]
                            timestamp = int(time.time())
                            base_name, _ = os.path.splitext(st.session_state["nombre_archivo"])
                            base_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', base_name)
                            
                            orig_filename = f"original_{timestamp}_{unique_id}_{base_name}.png"
                            ann_filename = f"annotated_{timestamp}_{unique_id}_{base_name}.png"
                            
                            with st.spinner("Subiendo imágenes al servidor..."):
                                original_image_url = subir_imagen_supabase(image_data, orig_filename)
                                if cajas:
                                    imagen_anotada = dibujar_cajas(image_data, cajas)
                                    annotated_image_url = subir_imagen_supabase(imagen_anotada, ann_filename)
                                else:
                                    annotated_image_url = original_image_url

                        # Determinar clasificación: si hay cajas es anormal, de lo contrario normal
                        classification = "anormal" if cajas else "normal"

                        # Guardar reporte en Supabase automáticamente (guardamos la versión limpia de texto y las URLs)
                        guardar_reporte(
                            st.session_state["nombre_archivo"],
                            reporte_limpio,
                            region_anatomica,
                            original_image_url,
                            annotated_image_url,
                            classification
                        )
                        
                        # Recargar interfaz para mostrar el checkbox
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                st.info("Esta imagen ya fue analizada. Sube otra para un nuevo análisis.")

        # -------------------------
        # MOSTRAR RESULTADO
        # -------------------------
        if st.session_state["reporte_limpio"]:
            with st.chat_message("assistant"):
                st.write(st.session_state["reporte_limpio"])
                
                # Mostrar un badge si se detectaron anomalías
                if st.session_state["cajas"]:
                    st.markdown(f"⚠️ *Se han detectado {len(st.session_state['cajas'])} zonas sospechosas en la imagen (ver recuadros en la vista previa).*")

            pdf_bytes = generar_pdf(st.session_state["reporte_limpio"], region_anatomica)

            st.download_button(
                label="📄 Descargar PDF",
                data=pdf_bytes,
                file_name=f"informe_{region_anatomica.replace(' ', '_').lower()}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

# -------------------------
# PESTAÑA: HISTORIAL
# -------------------------
with tab_historial:
    st.markdown("### 🕒 Reportes Almacenados en la Nube")

    if not supabase_client:
        st.info("El historial clínico está inactivo. Por favor, configura las variables `SUPABASE_URL` y `SUPABASE_KEY` en tu archivo `.env` para conectar con Supabase.")
    else:
        if st.button("🔄 Actualizar Historial", use_container_width=True):
            st.rerun()

        historial = obtener_historial()

        if not historial:
            st.info("No se encontraron reportes en el historial. ¡Comienza analizando imágenes para guardarlos aquí!")
        else:
            for item in historial:
                fecha_raw = item.get("created_at", "")
                try:
                    fecha_legible = fecha_raw.replace("T", " ")[:16]
                except:
                    fecha_legible = fecha_raw

                # Deducir la clasificación para registros previos o nuevos
                classification = item.get("classification")
                if not classification:
                    orig_url = item.get("original_image_url")
                    ann_url = item.get("annotated_image_url")
                    if ann_url and orig_url and ann_url != orig_url:
                        classification = "anormal"
                    else:
                        classification = "normal"

                emoji = "🟢 [NORMAL]" if classification == "normal" else "🔴 [ANORMAL]"
                titulo = f"{emoji} Reporte - {item.get('anatomy_region', 'No especificada')} | {item.get('image_name', 'Archivo')} ({fecha_legible})"

                with st.expander(titulo):
                    col_diag, col_img = st.columns([4, 3])
                    
                    with col_diag:
                        if classification == "normal":
                            st.markdown(
                                '<div style="background-color: #d1e7dd; color: #0f5132; padding: 6px 12px; border-radius: 8px; font-weight: bold; margin-bottom: 12px; display: inline-block; border: 1px solid #badbcc;">🟢 ESTUDIO NORMAL</div>',
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown(
                                '<div style="background-color: #f8d7da; color: #842029; padding: 6px 12px; border-radius: 8px; font-weight: bold; margin-bottom: 12px; display: inline-block; border: 1px solid #f5c2c7;">🔴 ESTUDIO ANORMAL</div>',
                                unsafe_allow_html=True
                            )
                            
                        st.markdown("**Informe Médico:**")
                        st.write(item.get("report_text", ""))

                        st.markdown("---")
                        pdf_bytes_historial = generar_pdf(
                            item.get("report_text", ""),
                            item.get("anatomy_region", "No especificada")
                        )

                        st.download_button(
                            label="📄 Descargar PDF de este Reporte",
                            data=pdf_bytes_historial,
                            file_name=f"informe_historial_{item.get('id')}.pdf",
                            mime="application/pdf",
                            key=f"dl_{item.get('id')}",
                            use_container_width=True
                        )

                    with col_img:
                        orig_url = item.get("original_image_url")
                        ann_url = item.get("annotated_image_url")
                        
                        if classification == "normal":
                            st.markdown("**Imagen del Estudio:**")
                            if orig_url:
                                st.image(orig_url, caption="Imagen Original (Normal)", use_column_width=True)
                            else:
                                st.info("Imagen original no disponible.")
                        else:
                            st.markdown("**Visualización de Imágenes:**")
                            ver_remarcada = st.checkbox(
                                "Ver imagen con secciones remarcadas 🟥", 
                                value=True, 
                                key=f"chk_{item.get('id')}"
                            )
                            
                            if ver_remarcada:
                                if ann_url:
                                    st.image(ann_url, caption="Imagen con Secciones Remarcadas (Anormal)", use_column_width=True)
                                else:
                                    st.info("Imagen anotada no disponible.")
                            else:
                                if orig_url:
                                    st.image(orig_url, caption="Imagen Original", use_column_width=True)
                                else:
                                    st.info("Imagen original no disponible.")