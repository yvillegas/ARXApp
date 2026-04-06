# 🩺 ARXAPP · Asistente Radiológico con IA
Este sistema es una herramienta de apoyo al diagnóstico que utiliza Gemini 2.5 Flash para procesar y analizar imágenes de rayos X en tiempo real. Está diseñado para optimizar el flujo de trabajo radiológico, proporcionando informes técnicos preliminares de manera inmediata.

# 🚀 Capacidades del Sistema
Análisis Multimodal: Procesamiento avanzado de imágenes para detectar anomalías en tórax, extremidades y columna.

Informes Técnicos: Generación de reportes estructurados con terminología médica profesional (Campos pulmonares, silueta cardíaca, etc.).

Exportación a PDF: Función integrada para descargar el análisis en un documento listo para revisión.

Interfaz Clínica: Diseño optimizado para entornos médicos utilizando Streamlit.

# 🛠️ Configuración e Instalación
Sigue estos pasos para poner en marcha el asistente en tu entorno local:

1. Clonar y preparar entorno
Primero, instala las dependencias necesarias:

Bash
pip3 install -r requirements.txt

2. Configurar la API de Google
Para que el cerebro de la IA funcione, necesitas una clave de Google AI Studio:

Obtén tu llave en Google AI Studio - API Key.

Abre el archivo app.py y busca la línea de configuración:

Python
genai.configure(api_key='TU_API_KEY_AQUÍ')

3. Ejecutar la Aplicación
Una vez configurado, lanza el servidor local con:

Bash
streamlit run app.py
📋 Estructura del Proyecto
app.py: Núcleo de la aplicación e interfaz de usuario.

configs.py: Configuración del modelo, instrucciones del sistema (prompts) y parámetros de seguridad.

requirements.txt: Lista de librerías necesarias (Streamlit, Google Generative AI, FPDF2, etc.).

# ⚠️ Aviso Legal
Este software es un prototipo para asistencia tecnológica. Los resultados generados por la inteligencia artificial deben ser siempre validados por un médico radiólogo colegiado. No debe utilizarse como única base para decisiones clínicas.

