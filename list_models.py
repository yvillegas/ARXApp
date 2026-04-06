import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

API_KEY = os.getenv("GOOGLE_API_KEY")

genai.configure(api_key=API_KEY)

models = list(genai.list_models())
for m in models:
    # muestra el nombre y si soporta generateContent (lo que necesitas)
    methods = getattr(m, "supported_generation_methods", [])
    print(m.name, methods)
