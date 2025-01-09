import os
import gspread
import streamlit as st
import time
from fpdf import FPDF
import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Google API credentials setup
SERVICE_ACCOUNT_INFO = st.secrets["gcp_service_account"]
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

creds = Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPES)
sheets_service = gspread.authorize(creds)
drive_service = build('drive', 'v3', credentials=creds)

# Google Sheets and Drive settings
SPREADSHEET_ID = "1JonYqjiZjkpqK2Cw8pmQbjFp6Vlr1OGvUUxiXxBaNZM"  # Replace with your Google Sheet ID
SHEET_NAME = "Customer Data"  # Replace with your worksheet name
PARENT_FOLDER_ID = "1-eebJdPTUnltZtisdVPdcGLl3tAZPOoE"  # ST-IBTEST folder in Drive

# Initialize session state
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "responses" not in st.session_state:
    st.session_state.responses = {}
if "show_summary" not in st.session_state:
    st.session_state.show_summary = False
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []


def authenticate(username, password):
    """Validate the username and password against stored credentials."""
    users = st.secrets["auth"]["users"]
    for user in users:
        if user["username"] == username and user["password"] == password:
            return True
    return False

def login():
    """Render the login form and handle authentication."""
    st.title("Login")
    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")

    if st.button("Login"):
        if authenticate(username, password):
            st.session_state["authenticated"] = True
            st.success("Login successful!")
        else:
            st.error("Invalid username or password.")


# Initialize file state
if "file" not in st.session_state:
    st.session_state["file"] = "not done"


def reset_form():
    # Clear specific keys related to the form
    keys_to_clear = ["responses", "show_summary", "uploaded_files"]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    # Reinitialize the required session state variables
    st.session_state.responses = {}
    st.session_state.show_summary = False
    st.session_state.uploaded_files = []

    # Notify the user that the form has been reset
    st.info("Form has been reset. You can start filling it again.")

# Trigger Reset at the Start if Needed
if "reset_triggered" not in st.session_state:
    reset_form()
    st.session_state.reset_triggered = True  # Prevent repeated resets


# # Function to update session state when files are uploaded
# def change_file_state():
#     st.session_state["file"] = "done"

# # File uploader to allow multiple PDF files
# pdfs = col2.file_uploader("Upload your PDFs", type=["pdf"], accept_multiple_files=True, on_change=change_file_state)

# Function to handle uploading files to Google Drive
# Function to upload user files to Google Drive
def upload_files_to_drive(files, folder_id):
    progress_bar = st.progress(0)
    total_files = len(files)
    local_files = []  # Lista para rastrear archivos locales creados

    for i, file in enumerate(files):
        try:
            file_name = file.name
            local_path = os.path.join("", file_name)
            local_files.append(local_path)

            # Guardar archivo localmente
            with open(local_path, "wb") as f:
                f.write(file.getbuffer())

            # Subir archivo a Google Drive
            file_metadata = {"name": file_name, "parents": [folder_id]}
            media = MediaFileUpload(local_path, mimetype="application/pdf")
            uploaded_file = drive_service.files().create(
                body=file_metadata, media_body=media, fields="id, name"
            ).execute()

            st.success(f"Uploaded {file_name} to Google Drive.")

            # Actualizar barra de progreso
            progress = int((i + 1) / total_files * 100)
            progress_bar.progress(progress)

        except Exception as e:
            st.error(f"Error uploading {file.name}: {e}")

    # # Eliminar todos los archivos locales después de procesarlos
    # for local_file in local_files:
    #     try:
    #         if os.path.exists(local_file):
    #             os.remove(local_file)
    #     except Exception as e:
    #         st.error(f"Error deleting file {local_file}: {e}")


# Function to save the generated PDF and user-uploaded files to Google Drive
def save_to_drive(responses, pdfs):
    try:
        folder_id = create_drive_folder("Customer_Folder", parent_folder_id=PARENT_FOLDER_ID)

        # Save the generated PDF
        pdf_filename = generate_pdf(responses)
        upload_to_drive(pdf_filename, "Assessment_Summary.pdf", folder_id)

        # Save the user-uploaded files
        upload_files_to_drive(pdfs, folder_id)

        st.success("All files saved to Google Drive successfully!")
    except Exception as e:
        st.error(f"Error saving files to Google Drive: {e}")

# Function to generate PDF
def generate_pdf(data):
    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        pdf.cell(200, 10, txt="FCT System Assessment Summary", ln=True, align='C')
        pdf.ln(10)

        for section, content in data.items():
            pdf.set_font("Arial", style='B', size=12)
            pdf.cell(0, 10, txt=section, ln=True)
            pdf.ln(5)

            pdf.set_font("Arial", size=12)
            if isinstance(content, dict):
                for key, value in content.items():
                    pdf.multi_cell(0, 10, f"{key}: {value}")
            else:
                pdf.multi_cell(0, 10, f"{section}: {content}")
            pdf.ln(5)

        pdf_file = "FCT_System_Assessment_Summary.pdf"
        pdf.output(pdf_file)
        return pdf_file
    except Exception as e:
        st.error(f"Error generating PDF: {e}")
        raise e


# Function to append data to Google Sheets
def append_to_google_sheet(sheet_id, sheet_name, data):
    try:
        # Open the Google Sheet
        sheet = sheets_service.open_by_key(sheet_id)
        worksheet = sheet.worksheet(sheet_name)

        # Add headers if the worksheet is empty
        if worksheet.row_count == 1:
            headers = list(data.keys())
            worksheet.append_row(headers)

        # Remove blank values
        cleaned_data = {k: v for k, v in data.items() if v}

        # Convert to list
        values = list(cleaned_data.values())

        # Append the new row
        worksheet.append_row(values)
        st.write("Data successfully appended to Google Sheets.")
    except Exception as e:
        st.error(f"Error appending to Google Sheets: {e}")



# Function to create a folder in Google Drive
def create_drive_folder(folder_name, parent_folder_id=None):
    try:
        folder_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_folder_id] if parent_folder_id else [],
        }
        folder = drive_service.files().create(body=folder_metadata, fields="id, name, parents").execute()
        st.write(f"Folder created: {folder}")
        return folder.get("id")
    except Exception as e:
        st.error(f"Error creating folder in Google Drive: {e}")

# Function to upload a file to Google Drive
def upload_to_drive(file_path, file_name, folder_id):
    try:
        file_metadata = {"name": file_name, "parents": [folder_id]}
        media = MediaFileUpload(file_path, mimetype="application/pdf")
        uploaded_file = drive_service.files().create(
            body=file_metadata, media_body=media, fields="id, name, parents"
        ).execute()
        st.write(f"File uploaded: {uploaded_file}")
        return uploaded_file.get("id")
    except Exception as e:
        st.error(f"Error uploading file to Google Drive: {e}")

# Function to flatten nested dictionary for Google Sheets
def flatten_responses(data):
    """Flatten nested response dictionary for Google Sheets."""
    flat_data = {}
    for section, content in data.items():
        # Si el contenido es un diccionario, procesa sus elementos
        if isinstance(content, dict):
            for key, value in content.items():
                # Convertir valores a cadena
                value = convert_to_string(value)
                flat_data[f"{section} - {key}"] = value
        else:
            # Si el contenido no es un diccionario, convertir a cadena
            flat_data[section] = convert_to_string(content)
    return flat_data

def convert_to_string(value):
    """Helper to convert non-string values to strings."""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    elif not isinstance(value, str):
        return str(value)
    return value

# Function to render a 3D cuboid using matplotlib
def render_cuboid_matplotlib(length, width, height, color):
    vertices = [
        [0, 0, 0],
        [length, 0, 0],
        [length, width, 0],
        [0, width, 0],
        [0, 0, height],
        [length, 0, height],
        [length, width, height],
        [0, width, height],
    ]

    faces = [
        [vertices[0], vertices[1], vertices[5], vertices[4]],
        [vertices[1], vertices[2], vertices[6], vertices[5]],
        [vertices[2], vertices[3], vertices[7], vertices[6]],
        [vertices[3], vertices[0], vertices[4], vertices[7]],
        [vertices[0], vertices[1], vertices[2], vertices[3]],
        [vertices[4], vertices[5], vertices[6], vertices[7]],
    ]

    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    poly3d = Poly3DCollection(faces, alpha=0.5, facecolors=color, edgecolor='gray')
    ax.add_collection3d(poly3d)

    ax.set_xlim(0, max(length, 200))
    ax.set_ylim(0, max(width, 200))
    ax.set_zlim(0, max(height, 200))

    ax.set_xlabel("Length")
    ax.set_ylabel("Width")
    ax.set_zlabel("Height")

    st.pyplot(fig)

#Function to render dimensions in interactive mode, in order to work with Questions from excel
def render_dimensions():
    st.header("Testing Conditions")
    st.subheader("3D Visualizations")
    
    # Sliders para las dimensiones
    col1, col2 = st.columns(2)
    with col1:
        length = st.slider("Length (cm)", min_value=10, max_value=200, value=150, key="custom_length")
        width = st.slider("Width (cm)", min_value=10, max_value=200, value=125, key="custom_width")
        height = st.slider("Height (cm)", min_value=10, max_value=200, value=200, key="custom_height")

    # Renderización interactiva
    col1, col2 = st.columns(2)
    with col1:
        st.write("FCT Dimension requirements")
        render_cuboid_matplotlib(length, width, height, "blue")
    with col2:
        st.write("Typical Functional Test system dimensions")
        render_cuboid_matplotlib(150, 125, 200, "gray")
    
    return {
        "Length": length,
        "Width": width,
        "Height": height
    }

#Function to load Questions from excel file
def load_questions_from_excel(file_path):
    return pd.read_excel(file_path)
questions_df = load_questions_from_excel("questions.xlsx")

# Renderiza las preguntas dinámicamente en Streamlit
def render_dynamic_form(questions_df):
    sections = questions_df['Sección'].unique()
    responses = {}
    for section in sections:
        st.header(section)
        section_questions = questions_df[questions_df['Sección'] == section]
        for _, row in section_questions.iterrows():
            question_text = row['Pregunta']
            question_type = row['Tipo']
            key = row['Clave']
            options = str(row['Opciones']).split(',') if pd.notna(row['Opciones']) else None

            if question_type == 'radio':
                responses[key] = st.radio(question_text, options, key=key)
            elif question_type == 'checkbox':
                responses[key] = st.checkbox(question_text, key=key)
            elif question_type == 'text_input':
                responses[key] = st.text_input(question_text, key=key)
            elif question_type == 'multiselect':
                responses[key] = st.multiselect(question_text, options, key=key)
            elif question_type == 'number_input':
                responses[key] = st.number_input(question_text, key=key)
    return responses


# Function to reset the form
def reset_form():
    # Clear specific keys related to the form
    keys_to_clear = ["responses", "show_summary", "uploaded_files"]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    # Reinitialize the required session state variables
    st.session_state.responses = {}
    st.session_state.show_summary = False
    st.session_state.uploaded_files = []

    # Notify the user that the form has been reset
    st.info("Form has been reset. You can start filling it again.")


# Streamlit App Initialization
if "responses" not in st.session_state:
    st.session_state.responses = {}
if "show_summary" not in st.session_state:
    st.session_state.show_summary = False
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []


if not st.session_state["authenticated"]:
    login()
else:
        # Main app content
    st.title("FCT System Assessment Questionnaire")
    
    # Logout button
    if st.button("Logout"):
        st.session_state["authenticated"] = False
        st.experimental_rerun()  # Reload the app to show the login page

    # Add your existing app logic here
    st.write("Welcome to the FCT System Assessment App!")


# Streamlit App Title
st.title("FCT System Assessment Questionnaire")

# File Uploader Section
st.header("Upload Supporting Documents")
uploaded_files = st.file_uploader(
    "Upload your supporting documents (PDFs only)", 
    type=["pdf"], 
    accept_multiple_files=True
)

if uploaded_files:
    st.session_state.uploaded_files = uploaded_files
    st.success(f"{len(uploaded_files)} file(s) uploaded successfully!")

# Summary Section or Form Display
if st.session_state.show_summary:
    # Display Summary
    st.header("Summary")
    responses = st.session_state.responses

    if not responses:
        st.error("No responses available. Please fill out the form.")
    else:
        for section, content in responses.items():
            if isinstance(content, dict):
                st.subheader(section)
                for key, value in content.items():
                    st.text(f"{key}: {value}")
            else:
                st.write(f"{section}: {content}")

    # Save to Google Button
    st.subheader("Next Steps")
    if st.button("Save to Google"):
        try:
            # Process Responses and Save to Google Sheets
            flat_responses = flatten_responses(st.session_state.responses)
            append_to_google_sheet(SPREADSHEET_ID, SHEET_NAME, flat_responses)

            # Create Folder in Google Drive
            folder_id = create_drive_folder("Customer_Folder", parent_folder_id=PARENT_FOLDER_ID)

            # Upload PDF of the Form
            pdf_filename = generate_pdf(st.session_state.responses)
            if pdf_filename and os.path.exists(pdf_filename):
                upload_to_drive(pdf_filename, "Assessment_Summary.pdf", folder_id)
            else:
                st.error("PDF file was not generated correctly.")

            # Upload Supporting Files
            if st.session_state.uploaded_files:
                upload_files_to_drive(st.session_state.uploaded_files, folder_id)

            st.success("Data and files saved to Google Drive successfully!")
        except Exception as e:
            st.error(f"Error during save operation: {e}")

    # Edit Responses Button
    if st.button("Edit Responses"):
        st.session_state.show_summary = False

else:
    # Conditional to re-render form if reset
    responses = render_dynamic_form(questions_df)
    responses["Testing Conditions"] = render_dimensions()


# Reset Form Button
    if st.button("Reset Form"):
        reset_form()



    # Submit Button
    if st.button("Submit"):
        st.session_state.responses = responses
        st.session_state.show_summary = True

        try:
            st.write("Responses before saving:", st.session_state.responses)

            # Flatten Responses and Save to Google Sheets
            flat_responses = flatten_responses(st.session_state.responses)
            st.write("Flattened Responses:", flat_responses)
            append_to_google_sheet(SPREADSHEET_ID, SHEET_NAME, flat_responses)

            # Create Folder in Google Drive
            folder_id = create_drive_folder("Customer_Folder", parent_folder_id=PARENT_FOLDER_ID)

            # Generate and Upload the Form PDF
            pdf_filename = generate_pdf(st.session_state.responses)
            upload_to_drive(pdf_filename, "Assessment_Summary.pdf", folder_id)

            # Upload Supporting Files
            if st.session_state.uploaded_files:
                upload_files_to_drive(st.session_state.uploaded_files, folder_id)

            st.success("Data and files saved to Google Drive successfully!")
        except Exception as e:
            st.error(f"Error during save operation: {e}")
