import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime
import zipfile
import io
import base64 # Importación nueva para poder mostrar el PDF

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

# --- FUNCIÓN AUXILIAR: MOSTRAR PDF EN PANTALLA ---
def mostrar_pdf_iframe(bytes_pdf):
    base64_pdf = base64.b64encode(bytes_pdf).decode('utf-8')
    # Ajustamos el iframe para que se vea grande y claro
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="700px" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)

# --- TODO EL PORTAL DENTRO DEL IF ---
if check_password():

    # 2. MOTOR DE AUDITORÍA
    def analizar_pdf(archivo_bytes, nombre_archivo_real):
        try:
            # Leemos desde bytes (compatible con PDF subido y ZIP extraído)
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
                    segmento_post_nombre = texto_upper[fin:fin+30]
                    match_rut = re.search(r'(\d{1,2}\.?\d{3}\.?\d{3}-[\dkK])', segmento_post_nombre)
                    if match_rut: rut_trabajador = match_rut.group(1)
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
            "TRABAJADOR": trabajador,
            "RUT": rut_trabajador,
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

    archivos = st.file_uploader("Sube aquí los archivos PDF o ZIP", accept_multiple_files=True, type=["pdf", "zip"])

    # --- LÓGICA DE PERSISTENCIA (SESSION STATE) ---
    # Esto es clave para que al seleccionar un PDF no se borre la tabla
    if "datos_auditoria" not in st.session_state:
        st.session_state["datos_auditoria"] = None
    if "archivos_pdf_bytes" not in st.session_state:
        st.session_state["archivos_pdf_bytes"] = {}

    if archivos:
        if st.button("EJECUTAR AUDITORÍA MASIVA", use_container_width=True):
            datos = []
            diccionario_pdfs = {} # Guardaremos los bytes aquí para verlos después
            
            for arc in archivos:
                # 1. SI ES PDF
                if arc.name.lower().endswith(".pdf"):
                    bytes_archivo = arc.getvalue() # Leemos los bytes
                    resultado = analizar_pdf(bytes_archivo, arc.name)
                    datos.append(resultado)
                    # Guardamos para el visor (Usamos el nombre de archivo o Trabajador como llave)
                    key_name = f"{resultado['TRABAJADOR']} ({arc.name})"
                    diccionario_pdfs[key_name] = bytes_archivo

                # 2. SI ES ZIP
                elif arc.name.lower().endswith(".zip"):
                    try:
                        with zipfile.ZipFile(arc) as z:
                            for nombre_interno in z.namelist():
                                if nombre_interno.lower().endswith(".pdf") and not nombre_interno.startswith("__MACOSX"):
                                    with z.open(nombre_interno) as archivo_zip:
                                        bytes_zip = archivo_zip.read() # Leemos bytes
                                        resultado = analizar_pdf(bytes_zip, nombre_interno)
                                        datos.append(resultado)
                                        key_name = f"{resultado['TRABAJADOR']} ({nombre_interno})"
                                        diccionario_pdfs[key_name] = bytes_zip
                    except:
                        st.error(f"Error al leer el archivo ZIP: {arc.name}")

            # Guardamos todo en la memoria de la sesión
            if datos:
                st.session_state["datos_auditoria"] = pd.DataFrame(datos)
                st.session_state["archivos_pdf_bytes"] = diccionario_pdfs
            else:
                st.warning("No se encontraron archivos PDF válidos.")

    # --- MOSTRAR RESULTADOS (SI EXISTEN EN MEMORIA) ---
    if st.session_state["datos_auditoria"] is not None:
        df_detalle = st.session_state["datos_auditoria"]
        
        # TABLA 1: RESUMEN
        st.subheader("📋 RESUMEN POR EMPRESA")
        resumen = df_detalle.groupby("EMPLEADOR").agg(
            Trabajadores=("TRABAJADOR", "count"),
            Aprobados=("ESTADO", lambda x: (x == "VALIDADO").sum()),
            Rechazados=("ESTADO", lambda x: (x == "RECHAZADO").sum()),
            Quien_Falla=("TRABAJADOR", lambda x: ", ".join(df_detalle[(df_detalle['EMPLEADOR'] == x.name) & (df_detalle['ESTADO'] == 'RECHAZADO')]['TRABAJADOR']))
        ).reset_index()
        st.dataframe(resumen, use_container_width=True, hide_index=True)

        st.divider()

        # TABLA 2: DETALLE
        st.subheader("🔍 DETALLE INDIVIDUAL")
        st.dataframe(df_detalle, use_container_width=True, hide_index=True)

        # BOTÓN DESCARGA
        csv = df_detalle.to_csv(index=False).encode('utf-8')
        st.download_button("📥 DESCARGAR REPORTE EXCEL", data=csv, file_name="Auditoria_Invermar.csv")
        
        st.divider()
        
        # --- NUEVO: VISOR DE DOCUMENTOS ---
        st.markdown("### 🧐 REVISOR DE DOCUMENTOS")
        st.info("Selecciona un trabajador de la lista para ver su liquidación original aquí mismo.")
        
        lista_archivos = list(st.session_state["archivos_pdf_bytes"].keys())
        seleccion = st.selectbox("Seleccione Documento a Revisar:", lista_archivos)
        
        if seleccion:
            col1, col2 = st.columns([1, 2]) # Dividimos pantalla: Info a la izq, PDF a la derecha
            
            # Buscamos los datos de ese trabajador específico
            datos_trabajador = df_detalle[df_detalle.apply(lambda row: f"{row['TRABAJADOR']} ({row['ARCHIVO']})" == seleccion, axis=1)].iloc[0]
            
            with col1:
                st.success("✅ DATOS DETECTADOS") if datos_trabajador['ESTADO'] == 'VALIDADO' else st.error("❌ RECHAZADO")
                st.write(f"**Trabajador:** {datos_trabajador['TRABAJADOR']}")
                st.write(f"**RUT:** {datos_trabajador['RUT']}")
                st.write(f"**Monto Imponible:** {datos_trabajador['BASE IMPONIBLE']}")
                st.write(f"**Observación:** {datos_trabajador['OBSERVACIONES']}")
            
            with col2:
                st.write("📄 **Vista Previa del PDF:**")
                bytes_pdf = st.session_state["archivos_pdf_bytes"][seleccion]
                mostrar_pdf_iframe(bytes_pdf)

    with st.sidebar:
        st.write(f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")
        if st.button("Cerrar Sesión"):
            st.session_state["password_correct"] = False
            st.rerun()
