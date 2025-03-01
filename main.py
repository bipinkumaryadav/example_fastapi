from fastapi import FastAPI, File, UploadFile, Form
import fitz  # PyMuPDF
import os
import re
import shutil
from typing import List
import base64

app = FastAPI()

UPLOAD_FOLDER = "uploads"
IMAGE_FOLDER = "images"
BASE_URL = "http://127.0.0.1:8000"  # Change this if deployed
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(IMAGE_FOLDER, exist_ok=True)

def extract_aadhaar_details(text):
    """Extract Aadhaar details using regex patterns."""
    details = {}

    # Extract fields using regex patterns
    details["Enrolment No."] = re.search(r"Enrolment No\.: ([\d\/]+)", text)
    # details["Name"] = re.search(r"\nTo\n([A-Za-z\u0900-\u097F\s]+)\n", text)  # ✅ Handles Hindi & English Names
    details["Name"] = re.search(r"\nTo\n([A-Za-z\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F\u0A80-\u0AFF\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0D80-\u0DFF\u0E00-\u0E7F\u0E80-\u0EFF\s]+)\n", text)
    details["Address (Hindi)"] = re.search(r"पत्ता:\n(.*?)\n\d{4} \d{4} \d{4}", text, re.DOTALL)
    details["Address (English)"] = re.search(r"Address:\n(.*?)\n\d{4} \d{4} \d{4}", text, re.DOTALL)
    details["Aadhaar Number"] = re.search(r"\b\d{4} \d{4} \d{4}\b", text)
    details["VID"] = re.search(r"VID : (\d{4} \d{4} \d{4} \d{4})", text)
    # details["Date of Birth (Hindi)"] = re.search(r"जन्म तारीख/DOB: (\d{2}/\d{2}/\d{4})", text)
    dob_pattern = r"(?:जन्म तारीख|जन्म तिथि|জন্ম তারিখ|ജനന തിയതി|பிறந்த தேதி|జన్మ తేదీ|ಜನ್ಮ ದಿನಾಂಕ|જન્મ તારીખ|ଜନ୍ମ ତାରିଖ|Date of Birth|DOB)[:\s]* (\d{2}/\d{2}/\d{4})"

    details["Date of Birth(Local)"] = re.search(dob_pattern, text)
    details["Date of Birth (English)"] = re.search(r"DOB: (\d{2}/\d{2}/\d{4})", text)
    details["Gender (Hindi)"] = re.search(r"(पुरुष|महिला)", text)
    details["Gender (English)"] = re.search(r"(?:MALE|FEMALE)", text)
    details["Mobile"] = re.search(r"Mobile: (\d+)", text)
    details["Aadhaar Issued Date"] = re.search(r"Aadhaar no. issued: (\d{2}/\d{2}/\d{4})", text)
    details["Details as on"] = re.search(r"Details as on: (\d{2}/\d{2}/\d{4})", text)

    # Convert matched objects to text safely
    for key, match in details.items():
        if match:
            details[key] = match.group(1) if match.groups() else match.group(0)
        else:
            details[key] = None  # If not found, set to None

    return details

def extract_images_from_pdf(pdf_path) -> List[str]:
    """Extract images from the PDF and save them."""
    doc = fitz.open(pdf_path)
    image_paths = []
    image_base64_list = []

    for page_number, page in enumerate(doc):
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]

            # Convert image bytes to Base64
            base64_str = base64.b64encode(image_bytes).decode("utf-8")
            image_base64_list.append(base64_str)

            # Save image file
            image_filename = f"{IMAGE_FOLDER}/image_{page_number + 1}_{img_index + 1}.png"
            with open(image_filename, "wb") as img_file:
                img_file.write(image_bytes)

                # Generate full URL for image
            image_url = f"{BASE_URL}/images/{image_filename}"
            
            image_paths.append(image_url)

    doc.close()
    return image_paths
def extract_images_as_base64(pdf_path) -> List[str]:
    """Extract images from the PDF and return as Base64."""
    doc = fitz.open(pdf_path)
    image_base64_list = []

    for page_number, page in enumerate(doc):
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]

            # Convert image bytes to Base64
            base64_str = base64.b64encode(image_bytes).decode("utf-8")
            image_base64_list.append(base64_str)

    doc.close()
    return image_base64_list

@app.post("/extract")
async def extract_text_and_images(pdf: UploadFile = File(...), password: str = Form("")):
    file_path = os.path.join(UPLOAD_FOLDER, pdf.filename)

    # Save the uploaded file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(pdf.file, buffer)

    try:
        # Open the PDF file
        doc = fitz.open(file_path)
        
        # Check if PDF is encrypted
        if doc.needs_pass:
            if not password:
                return {"error": "PDF is password protected. Please provide a password."}
            
            if not doc.authenticate(password):
                return {"error": "Invalid password. Please try again."}
            
            # 🔹 Try to re-open the document after authentication
            doc.close()
            doc = fitz.open(file_path)
            if doc.needs_pass:
                return {"error": "PDF is still encrypted after authentication."}

        # Extract text from all pages
        text = "\n".join([page.get_text() for page in doc])

        # Extract structured Aadhaar details
        aadhaar_details = extract_aadhaar_details(text)

        # Extract images
        image_paths = extract_images_from_pdf(file_path)

        image_base64_list = extract_images_as_base64(file_path)
        # Close and remove the PDF file after processing
        doc.close()
        os.remove(file_path)

        return {
            "Aadhaar Details": aadhaar_details,
            "Images": image_paths,
            "Images (Base64)": image_base64_list
        }

    except Exception as e:
        return {"error": str(e)}
