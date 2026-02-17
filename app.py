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

# --- FUNCIONES AUXILIARES ---
def normalize_rut(rut_str):
    """Limpia el RUT para comparaciones (quita puntos, espacios y deja mayúsculas)"""
    if not isinstance(rut_str, str):
        return "SIN_RUT"
    # Eliminar puntos y espacios, y pasar a mayúsculas
    clean = rut_str.replace(".", "").replace(" ", "").strip().upper()
    return clean

# --- SISTEMA DE SEGURIDAD (LOGIN) ---
def check_password():
    def password_entered():
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

    # 2. MOTOR DE AUDITORÍA
    def analizar_pdf(archivo_bytes, nombre_archivo_real):
        try:
            with pdfplumber.open(io.BytesIO(archivo_bytes)) as pdf:
                texto_completo = ""
                for pagina in pdf.pages:
                    texto_completo += pagina.extract_text() or ""
        except:
            return {"ARCHIVO": nombre_archivo_real, "ESTADO": "ERROR", "OBSERVACIONES": "Ilegible"}
                
        texto_upper = texto_completo.upper()
        
        # --- EXTRACCIÓN DE DATOS ---
        trabajador = "NO DETECTADO"
        rut_trabajador = "NO DETECTADO"
        
        if "SR.(A)" in texto_upper:
            try:
                inicio = texto_upper.find("SR.(A)") + 6
                fin = texto_upper.find("RUT", inicio)
                if fin != -1:
                    trabajador = texto_upper[inicio:fin].replace(":", "").strip()
                    # Buscar RUT
                    segmento = texto_upper[fin:fin+30]
                    match = re.search(r'(\d{1,2}\.?\d{3}\.?\d{3}-[\dkK])', segmento)
                    if match: rut_trabajador = match.group(1)
            except: trabajador = "ERROR"

        empleador = "NO DETECTADO"
        if "EMPLEADOR" in texto_upper:
            try:
                inicio = texto_upper.find("EMPLEADOR") + 10
                fin = texto_upper.find("RUT", inicio)
                if fin != -1: empleador = texto_upper[inicio:fin].replace(":", "").strip()
            except: empleador = "ERROR"

        imponible_valor = 0
        try:
            montos = re.findall(r'\$\s*(\d+\.?\d+\.?\d+)', texto_upper)
            if not montos: montos = re.findall(r'IMPONIBLE\s*(\d+\.?\d+\.?\d+)', texto_upper)
            for m in montos:
                valor = int(m.replace(".", ""))
                if valor > 400000:
                    imponible_valor = valor
                    break
        except: imponible_valor = 0

        faltas = []
        if not any(x in texto_upper for x in ["PROVIDA", "MODELO", "HABITAT", "CUPRUM", "COTIZACION"]): faltas.append("AFP")
        if "FONASA" not in texto_upper and "ISAPRE" not in texto_upper: faltas.append("SALUD")
        if "AFC" not in texto_upper and "CESANTIA" not in texto_upper: faltas.append("SEGURO")
        if "ACHS" not in texto_upper and "MUTUAL" not in texto_upper: faltas.append("MUTUAL")
        
        estado = "VALIDADO" if len(faltas) == 0 else "RECHAZADO"
        revision_monto = "RAZONABLE (CUMPLE % LEGAL)" if (imponible_valor > 0 and estado == "VALIDADO") else "VERIFICAR"

        return {
            "ARCHIVO": nombre_archivo_real,
            "TRABAJADOR_PDF": trabajador,
            "RUT": rut_trabajador,
            "EMPLEADOR_PDF": empleador,
            "BASE IMPONIBLE": f"${imponible_valor:,}" if imponible_valor > 0 else "N/A",
            "ANÁLISIS MONTOS": revision_monto,
            "ESTADO_PDF": estado,
            "OBSERVACIONES": "CUMPLIMIENTO TOTAL" if estado == "VALIDADO" else f"FALTA: {', '.join(faltas)}"
        }

    # 3. INTERFAZ VISUAL
    st.markdown("# PORTAL DE GESTIÓN Y VALIDACIÓN DE DOCUMENTOS")
    st.write("### Herramienta de Revisión Masiva y Cruce de Nómina")
    st.divider()

    # --- SECCIÓN DE CARGA (AHORA CON DOS SUBIDAS) ---
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("📂 **PASO 1 (Opcional):** Cargar Nómina")
        archivo_nomina = st.file_uploader("Subir CSV/Excel de Trabajadores (Pronexo)", type=["csv", "xlsx"])

    with col2:
        st.info("📄 **PASO 2:** Cargar Documentos")
        archivos_pdfs = st.file_uploader("Subir PDFs o ZIP de Cotizaciones", accept_multiple_files=True, type=["pdf", "zip"])

    st.divider()

    if st.button("🚀 EJECUTAR AUDITORÍA Y CRUCE", use_container_width=True):
        
        if not archivos_pdfs:
            st.warning("⚠️ Debes subir al menos los archivos PDF/ZIP para auditar.")
        else:
            # 1. PROCESAR PDFs (EXTRACCIÓN)
            datos_pdf = []
            with st.spinner('Analizando documentos...'):
                for arc in archivos_pdfs:
                    # Leer bytes según tipo
                    if arc.name.lower().endswith(".pdf"):
                        datos_pdf.append(analizar_pdf(arc.getvalue(), arc.name))
                    elif arc.name.lower().endswith(".zip"):
                        try:
                            with zipfile.ZipFile(arc) as z:
                                for nombre_interno in z.namelist():
                                    if nombre_interno.lower().endswith(".pdf") and not nombre_interno.startswith("__MACOSX"):
                                        with z.open(nombre_interno) as archivo_zip:
                                            datos_pdf.append(analizar_pdf(archivo_zip.read(), nombre_interno))
                        except:
                            st.error(f"Error al leer ZIP: {arc.name}")

            df_pdfs = pd.DataFrame(datos_pdf)
            
            # Normalizar RUT del PDF para el cruce
            if not df_pdfs.empty:
                df_pdfs['RUT_CLEAN'] = df_pdfs['RUT'].apply(normalize_rut)

            # 2. LOGICA DEL CRUCE (SI HAY NÓMINA)
            if archivo_nomina is not None:
                try:
                    # Leemos el CSV saltando las primeras 9 filas (ajuste específico para Pronexo)
                    try:
                        df_nomina = pd.read_csv(archivo_nomina, header=9)
                    except:
                        df_nomina = pd.read_excel(archivo_nomina, header=9)

                    # Limpieza básica de la nómina
                    if 'Rut' in df_nomina.columns and 'Contratista' in df_nomina.columns:
                        df_nomina['RUT_CLEAN'] = df_nomina['Rut'].apply(normalize_rut)
                        
                        # --- EL CRUCE MAESTRO (LEFT JOIN) ---
                        # Unimos la Nómina (Izquierda) con los PDFs encontrados (Derecha) usando el RUT
                        df_final = pd.merge(df_nomina, df_pdfs, on='RUT_CLEAN', how='left')

                        # Definir Estado Final
                        def definir_estado(row):
                            if pd.isna(row['ESTADO_PDF']): # No cruzó (no se encontró PDF)
                                return "⚠️ FALTANTE"
                            elif row['ESTADO_PDF'] == "VALIDADO":
                                return "✅ OK"
                            else:
                                return "❌ RECHAZADO"

                        df_final['ESTADO_FINAL'] = df_final.apply(definir_estado, axis=1)

                        # --- MOSTRAR RESULTADOS ORDENADOS POR EMPRESA ---
                        st.subheader("📊 CRUCE CONTRA NÓMINA (Resultados por Empresa)")
                        
                        empresas = df_final['Contratista'].unique()
                        
                        for emp in empresas:
                            if pd.isna(emp): continue
                            
                            st.markdown(f"#### 🏢 {emp}")
                            df_emp = df_final[df_final['Contratista'] == emp]
                            
                            # Métricas de la empresa
                            total = len(df_emp)
                            ok = len(df_emp[df_emp['ESTADO_FINAL'] == "✅ OK"])
                            faltantes = len(df_emp[df_emp['ESTADO_FINAL'] == "⚠️ FALTANTE"])
                            rechazados = len(df_emp[df_emp['ESTADO_FINAL'] == "❌ RECHAZADO"])
                            
                            col_m1, col_m2, col_m3 = st.columns(3)
                            col_m1.metric("Dotación Nómina", total)
                            col_m2.metric("Documentados OK", ok)
                            col_m3.metric("Faltantes", faltantes, delta_color="inverse")

                            # Tabla detalle de la empresa
                            cols_visual = ['Nombre', 'Apellidos', 'Rut', 'ESTADO_FINAL', 'OBSERVACIONES', 'ARCHIVO']
                            st.dataframe(df_emp[cols_visual].fillna("-"), use_container_width=True, hide_index=True)
                            st.divider()

                        # Botón descarga consolidado
                        csv_final = df_final.to_csv(index=False).encode('utf-8-sig')
                        st.download_button("📥 DESCARGAR REPORTE CONSOLIDADO (CRUCE)", data=csv_final, file_name="Reporte_Cruce_Invermar.csv")

                    else:
                        st.error("El archivo de nómina no tiene las columnas 'Rut' o 'Contratista'. Verifique el formato.")
                except Exception as e:
                    st.error(f"Error al procesar la nómina: {e}")

            # 3. SI NO HAY NÓMINA (MUESTRA SOLO LO QUE SE SUBIÓ)
            else:
                st.subheader("📋 RESULTADOS DE AUDITORÍA (Solo archivos subidos)")
                if not df_pdfs.empty:
                    st.dataframe(df_pdfs.drop(columns=['RUT_CLEAN'], errors='ignore'), use_container_width=True)
                    csv = df_pdfs.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("📥 DESCARGAR REPORTE SIMPLE", data=csv, file_name="Auditoria_Simple.csv")
                else:
                    st.warning("No se encontraron datos en los archivos.")

    with st.sidebar:
        st.write(f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")
        if st.button("Cerrar Sesión"):
            st.session_state["password_correct"] = False
            st.rerun()
