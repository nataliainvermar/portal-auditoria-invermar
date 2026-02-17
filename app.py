import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime
import zipfile
import io

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(page_title="Portal de Gestión y Validación", page_icon="🐟", layout="wide")

# ESTILOS (Ocultar menú)
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- FUNCIÓN DE LIMPIEZA DE RUT ---
def limpiar_rut(rut):
    """Deja el RUT solo con números y K para poder comparar."""
    if pd.isna(rut): return ""
    return str(rut).replace(".", "").replace(" ", "").upper().strip()

# --- SISTEMA DE SEGURIDAD ---
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

# --- MOTOR PRINCIPAL ---
if check_password():

    # Lógica de análisis de PDF (RECUPERADO EL FORMATO ORIGINAL)
    def analizar_pdf(archivo_bytes, nombre_archivo_real):
        try:
            with pdfplumber.open(io.BytesIO(archivo_bytes)) as pdf:
                texto_completo = ""
                for pagina in pdf.pages:
                    texto_completo += pagina.extract_text() or ""
        except:
            return {"ARCHIVO": nombre_archivo_real, "ESTADO_PDF": "ERROR", "OBSERVACIONES": "Ilegible", "RUT_PDF": ""}
                
        texto_upper = texto_completo.upper()
        
        # Extracción de Datos
        trabajador = "NO DETECTADO"
        rut_pdf = ""
        
        if "SR.(A)" in texto_upper:
            try:
                inicio = texto_upper.find("SR.(A)") + 6
                fin = texto_upper.find("RUT", inicio)
                if fin != -1:
                    trabajador = texto_upper[inicio:fin].replace(":", "").strip()
                    # Buscar RUT
                    segmento = texto_upper[fin:fin+30]
                    match = re.search(r'(\d{1,2}\.?\d{3}\.?\d{3}-[\dkK])', segmento)
                    if match: rut_pdf = match.group(1)
            except: pass

        empleador = "NO DETECTADO"
        if "EMPLEADOR" in texto_upper:
            try:
                inicio = texto_upper.find("EMPLEADOR") + 10
                fin = texto_upper.find("RUT", inicio)
                if fin != -1: empleador = texto_upper[inicio:fin].replace(":", "").strip()
            except: pass

        imponible_valor = 0
        try:
            montos = re.findall(r'\$\s*(\d+\.?\d+\.?\d+)', texto_upper)
            if not montos: montos = re.findall(r'IMPONIBLE\s*(\d+\.?\d+\.?\d+)', texto_upper)
            for m in montos:
                valor = int(m.replace(".", ""))
                if valor > 400000:
                    imponible_valor = valor
                    break
        except: pass

        faltas = []
        if not any(x in texto_upper for x in ["PROVIDA", "MODELO", "HABITAT", "CUPRUM", "COTIZACION"]): faltas.append("AFP")
        if "FONASA" not in texto_upper and "ISAPRE" not in texto_upper: faltas.append("SALUD")
        if "AFC" not in texto_upper and "CESANTIA" not in texto_upper: faltas.append("SEGURO")
        if "ACHS" not in texto_upper and "MUTUAL" not in texto_upper: faltas.append("MUTUAL")
        
        estado = "VALIDADO" if len(faltas) == 0 else "RECHAZADO"
        # Recuperamos esta columna que te gustaba
        revision_monto = "RAZONABLE" if (imponible_valor > 0 and estado == "VALIDADO") else "VERIFICAR"

        return {
            "ARCHIVO": nombre_archivo_real,
            "TRABAJADOR_PDF": trabajador,
            "RUT_PDF": rut_pdf,
            "EMPLEADOR_PDF": empleador,
            "BASE IMPONIBLE": f"${imponible_valor:,}" if imponible_valor > 0 else "N/A",
            "ANÁLISIS MONTOS": revision_monto,
            "ESTADO_PDF": estado,
            "OBSERVACIONES": "CUMPLIMIENTO TOTAL" if estado == "VALIDADO" else f"FALTA: {', '.join(faltas)}"
        }

    # --- INTERFAZ VISUAL ---
    st.markdown("# PORTAL DE GESTIÓN Y VALIDACIÓN DE DOCUMENTOS")
    st.write("### 🏢 Control Maestro: Nómina vs Respaldos")
    st.divider()

    col1, col2 = st.columns(2)
    
    with col1:
        st.info("📂 **PASO 1:** Cargar Nómina (Excel/CSV Pronexo)")
        archivo_nomina = st.file_uploader("Subir archivo de Trabajadores", type=["xlsx", "csv"])

    with col2:
        st.info("📄 **PASO 2:** Cargar Respaldos (PDFs/ZIP)")
        archivos_respaldos = st.file_uploader("Subir Liquidaciones", accept_multiple_files=True, type=["pdf", "zip"])

    st.divider()

    # --- BOTÓN DE EJECUCIÓN ---
    if st.button("🚀 EJECUTAR CRUCE DE INFORMACIÓN", use_container_width=True):
        
        if not archivo_nomina or not archivos_respaldos:
            st.warning("⚠️ Por favor, sube AMBOS archivos (Nómina y PDFs) para hacer el cruce.")
        else:
            # 1. PROCESAR NÓMINA
            with st.spinner('Leyendo nómina de Pronexo...'):
                try:
                    if archivo_nomina.name.endswith('.csv'):
                        df_nomina = pd.read_csv(archivo_nomina, header=9)
                    else:
                        df_nomina = pd.read_excel(archivo_nomina, header=9)
                    
                    df_nomina['RUT_CLEAN'] = df_nomina['Rut'].apply(limpiar_rut)
                except Exception as e:
                    st.error(f"Error leyendo la nómina: {e}")
                    st.stop()

            # 2. PROCESAR PDFS
            datos_pdfs = []
            with st.spinner('Analizando documentos PDF...'):
                barra = st.progress(0)
                total_archivos = len(archivos_respaldos)
                
                for i, arc in enumerate(archivos_respaldos):
                    if arc.name.lower().endswith(".pdf"):
                        datos_pdfs.append(analizar_pdf(arc.getvalue(), arc.name))
                    elif arc.name.lower().endswith(".zip"):
                        try:
                            with zipfile.ZipFile(arc) as z:
                                for nombre_int in z.namelist():
                                    if nombre_int.lower().endswith(".pdf") and not nombre_int.startswith("__MACOSX"):
                                        with z.open(nombre_int) as f_zip:
                                            datos_pdfs.append(analizar_pdf(f_zip.read(), nombre_int))
                        except: pass
                    barra.progress((i + 1) / total_archivos)

            if datos_pdfs:
                df_pdfs = pd.DataFrame(datos_pdfs)
                df_pdfs['RUT_CLEAN'] = df_pdfs['RUT_PDF'].apply(limpiar_rut)
            else:
                df_pdfs = pd.DataFrame(columns=['RUT_CLEAN', 'ESTADO_PDF', 'OBSERVACIONES', 'ARCHIVO'])

            # 3. EL CRUCE MAESTRO
            df_final = pd.merge(df_nomina, df_pdfs, on='RUT_CLEAN', how='left')

            def definir_estado(row):
                if pd.isna(row['ESTADO_PDF']):
                    return "⚠️ FALTANTE"
                elif row['ESTADO_PDF'] == "VALIDADO":
                    return "✅ OK"
                else:
                    return "❌ RECHAZADO"

            df_final['ESTADO_FINAL'] = df_final.apply(definir_estado, axis=1)

            # 4. MOSTRAR RESULTADOS
            st.success("✅ Cruce finalizado con éxito")
            
            # FILTRO: Solo empresas involucradas en la subida actual
            empresas_activas = df_final[df_final['ESTADO_PDF'].notna()]['Contratista'].unique()
            
            if len(empresas_activas) == 0:
                st.warning("⚠️ Se procesaron los archivos, pero no hubo coincidencia con la nómina.")
            else:
                # Filtrar el DataFrame Principal para mostrar solo las empresas activas
                df_filtrado = df_final[df_final['Contratista'].isin(empresas_activas)].copy()

                # --- RESUMEN DE MÉTRICAS (Arriba) ---
                st.subheader("📋 RESUMEN POR EMPRESA")
                for emp in empresas_activas:
                    if pd.isna(emp): continue
                    
                    df_emp = df_filtrado[df_filtrado['Contratista'] == emp]
                    
                    st.markdown(f"**🏢 {emp}**")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Dotación", len(df_emp))
                    c2.metric("OK", len(df_emp[df_emp['ESTADO_FINAL'] == "✅ OK"]))
                    c3.metric("Faltan/Rechazo", len(df_emp[df_emp['ESTADO_FINAL'] != "✅ OK"]), delta_color="inverse")
                    st.divider()

                # --- EL DETALLE INDIVIDUAL (LO QUE FALTABA) ---
                st.subheader("🔍 DETALLE INDIVIDUAL COMPLETO")
                st.info("Lista consolidada de trabajadores de las empresas procesadas.")
                
                # Seleccionamos y renombramos columnas para que se vea ordenado
                columnas_finales = {
                    'Rut': 'RUT',
                    'Apellidos': 'APELLIDOS',
                    'Nombre': 'NOMBRES',
                    'Contratista': 'EMPRESA',
                    'ESTADO_FINAL': 'ESTADO',
                    'BASE IMPONIBLE': 'RENTA IMP.',
                    'ANÁLISIS MONTOS': 'ANÁLISIS',
                    'OBSERVACIONES': 'OBSERVACIONES',
                    'ARCHIVO': 'ARCHIVO'
                }
                
                # Mostramos la tabla con las columnas que existen
                cols_a_mostrar = [c for c in columnas_finales.keys() if c in df_filtrado.columns]
                df_display = df_filtrado[cols_a_mostrar].rename(columns=columnas_finales).fillna("-")
                
                st.dataframe(df_display, use_container_width=True, hide_index=True)

                # Descarga
                csv = df_display.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 DESCARGAR REPORTE EXCEL", data=csv, file_name="Auditoria_Consolidada.csv")

    with st.sidebar:
        st.write(f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")
        if st.button("Cerrar Sesión"):
            st.session_state["password_correct"] = False
            st.rerun()
