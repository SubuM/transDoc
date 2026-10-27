import streamlit as st
from pdf2image import convert_from_bytes
import pytesseract
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException
from PIL import Image
import io
import fitz

try:
    import argostranslate.package
    import argostranslate.translate
    HAS_ARGOS = True
except Exception:
    HAS_ARGOS = False

st.set_page_config(page_title="transDoc v2 (OCR)", layout="wide")

st.title("Document Translator - OCR Version")
st.write("Upload a multi-page PDF, OCR with Tesseract, detect language, translate to English while preserving images (offline)")

@st.cache_data
def translate_text_offline(text, from_code):
    if from_code == 'en' or not text.strip():
        return text
    try:
        if HAS_ARGOS:
            translated = argostranslate.translate.translate(text, from_code, 'en')
            if translated:
                return translated
    except Exception:
        pass
    return text

uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"], key="v2")

if uploaded_file is not None:
    file_id = f"v2_{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.get('processed_id_v2') != file_id:
        with st.spinner("Converting and OCR-ing PDF... This may take a while"):
            try:
                pdf_bytes = uploaded_file.read()
                
                # Convert PDF to images
                pages = convert_from_bytes(pdf_bytes)
                st.info(f"Processing {len(pages)} pages with OCR...")
                
                # Detect language from first page
                detected_lang = "en"
                try:
                    sample_text = pytesseract.image_to_string(pages[0])
                    if sample_text.strip():
                        detected_lang = detect(sample_text)
                except LangDetectException:
                    pass
                except Exception:
                    pass
                
                st.write(f"Detected language: {detected_lang}")
                
                new_doc = fitz.open()
                progress_bar = st.progress(0)
                
                for page_num, img in enumerate(pages):
                    # Save image to bytes
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='PNG')
                    img_bytes = img_byte_arr.getvalue()
                    
                    # Create new page
                    new_page = new_doc.new_page(width=img.width * 0.75, height=img.height * 0.75)  # Convert points roughly
                    
                    # Insert original image
                    new_page.insert_image(fitz.Rect(0, 0, img.width * 0.75, img.height * 0.75), stream=img_bytes)
                    
                    # OCR to get text with bounding boxes
                    try:
                        ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                        n_boxes = len(ocr_data['text'])
                        for i in range(n_boxes):
                            text = ocr_data['text'][i].strip()
                            if int(ocr_data['conf'][i]) > 30 and text:
                                translated = translate_text_offline(text, detected_lang)
                                if translated and translated.strip() and translated != text:
                                    x = ocr_data['left'][i] * 0.75
                                    y = ocr_data['top'][i] * 0.75
                                    w = ocr_data['width'][i] * 0.75
                                    h = ocr_data['height'][i] * 0.75
                                    try:
                                        new_page.insert_textbox(
                                            fitz.Rect(x, y, x + w + 50, y + h + 10),
                                            translated,
                                            fontsize=8,
                                            fontname="helv"
                                        )
                                    except Exception:
                                        pass
                    except Exception as e:
                        st.warning(f"OCR issue on page {page_num+1}: {e}")
                    
                    progress_bar.progress((page_num + 1) / len(pages))
                
                pdf_output = io.BytesIO()
                new_doc.save(pdf_output)
                pdf_output.seek(0)
                new_doc.close()
                
                st.session_state['processed_id_v2'] = file_id
                st.session_state['pdf_output_v2'] = pdf_output.getvalue()
                st.session_state['detected_lang_v2'] = detected_lang
                st.rerun()
            except Exception as e:
                st.error(f"Error processing PDF: {e}")
                st.exception(e)
    else:
        detected_lang = st.session_state.get('detected_lang_v2', 'unknown')
        if detected_lang == 'en':
            st.success("Document is in English - ready to download")
        else:
            st.success(f"Translated from {detected_lang} to English (offline OCR)")
        st.download_button(
            label="Download Translated PDF",
            data=st.session_state['pdf_output_v2'],
            file_name=f"translated_ocr_{uploaded_file.name}",
            mime="application/pdf",
            key="download_btn_v2"
        )
