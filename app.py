import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime
import zipfile
import io

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(page_title="Portal de Gestión y Validación", page_icon=":fish:", layout="wide")

# CÓDIGO PARA OCULTAR EL MENÚ Y EL BOTÓN DE GITHUB
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- SISTEMA DE SEGURIDAD (LOGIN) ---
def check_password():
    def password_entered():
        # Tu clave corporativa para el equipo
        if st.session_state["password"] == "Invermar2026": 
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.markdown("# 🔐 ACCESO RESTRINGIDO")
        st.info("Departamento de Subcontratación - Invermar")
        st.text_input("Ingrese la Contraseña Corporativa", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Ingrese la Contraseña Corporativa", type="password", on_change=password_entered, key="password")
        st.error("😕 Contraseña incorrecta. Intente de nuevo.")
        return False
    return True

# --- TODO EL PORTAL DENTRO DEL IF ---
if check_password():

    # 2. MOTOR DE AUDITORÍA (MODIFICADO PARA ACEPTAR NOMBRE EXTERNO)
    def analizar_pdf(archivo_pdf, nombre_archivo_real):
        try:
            with pdfplumber.open(archivo_pdf) as pdf:
                texto_completo = ""
                for pagina in pdf.pages:
                    texto_completo += pagina.extract_text() or ""
        except:
            return {"ARCHIVO": nombre_archivo_real, "ESTADO": "ERROR", "OBSERVACIONES": "Ilegible"}
                
        texto_upper = texto_completo.upper()
        
        # Extracción de nombres
        trabajador = "NO DETECTADO"
        if "SR.(A)" in texto_upper:
            try:
                inicio = texto_upper.find("SR.(A)") + 6
                fin = texto_upper.find("RUT", inicio)
                if fin != -1:
                    trabajador = texto_upper[inicio:fin].replace(":", "").strip()
            except: trabajador = "ERROR"

        empleador = "NO DETECTADO"
        if "EMPLEADOR" in texto_upper:
            try:
                inicio = texto_upper.find("EMPLEADOR") + 10
                fin = texto_upper.find("RUT", inicio)
                if fin != -1:
                    empleador = texto_upper[inicio:fin].replace(":", "").strip()
            except: empleador = "ERROR"

        # Auditoría de Montos (Ley Chilena: AFP ~11.5%, Salud 7%)
        imponible_valor = 0
        try:
            montos = re.findall(r'\$\s*(\d+\.?\d+\.?\d+)', texto_upper)
            if not montos:
                montos = re.findall(r'IMPONIBLE\s*(\d+\.?\d+\.?\d+)', texto_upper)
            for m in montos:
                valor = int(m.replace(".", ""))
                if valor > 400000: # Filtro para identificar sueldos
                    imponible_valor = valor
                    break
        except: imponible_valor = 0

        # Verificación de parámetros
        faltas = []
        if not any(x in texto_upper for x in ["PROVIDA", "MODELO", "HABITAT", "CUPRUM", "COTIZACION"]): faltas.append("AFP")
        if "FONASA" not in texto_upper and "ISAPRE" not in texto_upper: faltas.append("SALUD")
        if "AFC" not in texto_upper and "CESANTIA" not in texto_upper: faltas.append("SEGURO")
        if "ACHS" not in texto_upper and "MUTUAL" not in texto_upper: faltas.append("MUTUAL")
        
        estado = "VALIDADO" if len(faltas) == 0 else "RECHAZADO"
        revision_monto = "RAZONABLE (CUMPLE % LEGAL)" if (imponible_valor > 0 and estado == "VALIDADO") else "VERIFICAR"

        return {
            "ARCHIVO": nombre_archivo_real,
            "TRABAJADOR": trabajador,
            "EMPLEADOR": empleador,
            "BASE IMPONIBLE": f"${imponible_valor:,}" if imponible_valor > 0 else "N/A",
            "ANÁLISIS MONTOS": revision_monto,
            "ESTADO": estado,
            "OBSERVACIONES": "CUMPLIMIENTO TOTAL" if estado == "VALIDADO" else f"FALTA: {', '.join(faltas)}"
        }

    # 3. INTERFAZ VISUAL
    st.markdown("# PORTAL DE GESTIÓN Y VALIDACIÓN DE DOCUMENTOS")
    st.write("### Herramienta de Revisión Masiva: Certificados de Cotizaciones Previsionales")
    st.divider()

    # MODIFICADO: AHORA ACEPTA ZIP
    archivos = st.file_uploader("Sube aquí los archivos PDF o ZIP", accept_multiple_files=True, type=["pdf", "zip"])

    if archivos:
        if st.button("EJECUTAR AUDITORÍA MASIVA", use_container_width=True):
            datos = []
            
            # NUEVA LÓGICA PARA PROCESAR ZIP O PDF
            for arc in archivos:
                # Caso 1: Es un PDF normal
                if arc.name.lower().endswith(".pdf"):
                    datos.append(analizar_pdf(arc, arc.name))
                
                # Caso 2: Es un archivo ZIP
                elif arc.name.lower().endswith(".zip"):
                    try:
                        with zipfile.ZipFile(arc) as z:
                            for nombre_interno in z.namelist():
                                # Solo procesamos si el archivo dentro del zip es un PDF
                                if nombre_interno.lower().endswith(".pdf") and not nombre_interno.startswith("__MACOSX"):
                                    with z.open(nombre_interno) as archivo_zip:
                                        # Leemos el PDF en memoria
                                        pdf_bytes = io.BytesIO(archivo_zip.read())
                                        datos.append(analizar_pdf(pdf_bytes, nombre_interno))
                    except:
                        st.error(f"Error al leer el archivo ZIP: {arc.name}")

            if datos:
                df_detalle = pd.DataFrame(datos)

                # TABLA 1: RESUMEN POR EMPRESA (Para Nicole y Jessica)
                st.subheader("📋 RESUMEN POR EMPRESA")
                resumen = df_detalle.groupby("EMPLEADOR").agg(
                    Trabajadores=("TRABAJADOR", "count"),
                    Aprobados=("ESTADO", lambda x: (x == "VALIDADO").sum()),
                    Rechazados=("ESTADO", lambda x: (x == "RECHAZADO").sum()),
                    Quien_Falla=("TRABAJADOR", lambda x: ", ".join(df_detalle[(df_detalle['EMPLEADOR'] == x.name) & (df_detalle['ESTADO'] == 'RECHAZADO')]['TRABAJADOR']))
                ).reset_index()
                st.dataframe(resumen, use_container_width=True, hide_index=True)

                st.divider()

                # TABLA 2: DETALLE INDIVIDUAL
                st.subheader("🔍 DETALLE INDIVIDUAL")
                st.dataframe(df_detalle, use_container_width=True, hide_index=True)
                
                # Exportación
                csv = df_detalle.to_csv(index=False).encode('utf-8')
                st.download_button("📥 DESCARGAR REPORTE EXCEL", data=csv, file_name="Auditoria_Invermar.csv")
            else:
                st.warning("No se encontraron archivos PDF válidos para procesar.")

    with st.sidebar:
        st.write(f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")
        if st.button("Cerrar Sesión"):
            st.session_state["password_correct"] = False
            st.rerun()
