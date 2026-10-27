import streamlit as st
from pdf2image import convert_from_bytes
import pytesseract
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException
from PIL import Image
import io
import fitz
import os
import tempfile
from docx import Document

try:
    import argostranslate.package
    import argostranslate.translate
    HAS_ARGOS = True
except Exception:
    HAS_ARGOS = False

st.set_page_config(page_title="transDoc v3", layout="wide")

st.title("Document Translator - Multi-format OCR")
st.write("Upload PDF, DOC, or DOCX files. OCR, detect language, translate to English while preserving images (offline)")

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

uploaded_file = st.file_uploader("Choose a file", type=["pdf", "doc", "docx"], key="v3")

if uploaded_file is not None:
    file_id = f"v3_{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.get('processed_id_v3') != file_id:
        with st.spinner("Processing document... This may take a while"):
            try:
                file_bytes = uploaded_file.read()
                filename = uploaded_file.name.lower()
                
                all_images = []
                detected_lang = "en"
                
                if filename.endswith('.pdf'):
                    pages = convert_from_bytes(file_bytes)
                    all_images = pages
                    try:
                        sample_text = pytesseract.image_to_string(pages[0])
                        if sample_text.strip():
                            detected_lang = detect(sample_text)
                    except Exception:
                        pass
                elif filename.endswith('.docx'):
                    doc = Document(io.BytesIO(file_bytes))
                    # Extract text for language detection
                    full_text = []
                    for para in doc.paragraphs:
                        full_text.append(para.text)
                    try:
                        if ' '.join(full_text).strip():
                            detected_lang = detect(' '.join(full_text)[:1000])
                    except Exception:
                        pass
                    # For DOCX, convert to images via PDF approach is complex offline
                    # Save as temp and convert
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
                        tmp.write(file_bytes)
                        tmp_path = tmp.name
                    try:
                        # Try to convert using libreoffice if available, else use python
                        # Fallback: create images from text
                        # For simplicity, we'll use pymupdf to render if possible
                        import subprocess
                        pdf_path = tmp_path.replace('.docx', '.pdf')
                        # Try libreoffice
                        result = subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', tmp_path, '--outdir', os.path.dirname(tmp_path)], 
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                        if os.path.exists(pdf_path):
                            with open(pdf_path, 'rb') as f:
                                pdf_bytes = f.read()
                            pages = convert_from_bytes(pdf_bytes)
                            all_images = pages
                            os.unlink(pdf_path)
                        else:
                            # Create a simple image from text
                            from PIL import Image, ImageDraw, ImageFont
                            img = Image.new('RGB', (1700, 2200), color='white')
                            draw = ImageDraw.Draw(img)
                            y = 50
                            for para in doc.paragraphs[:80]:
                                if para.text.strip():
                                    translated_para = translate_text_offline(para.text, detected_lang)
                                    draw.text((50, y), translated_para[:100], fill='black')
                                    y += 40
                            all_images = [img]
                    except Exception:
                        from PIL import Image, ImageDraw
                        img = Image.new('RGB', (1700, 2200), color='white')
                        draw = ImageDraw.Draw(img)
                        y = 50
                        for para in doc.paragraphs[:80]:
                            if para.text.strip():
                                translated_para = translate_text_offline(para.text, detected_lang)
                                draw.text((50, y), translated_para[:100], fill='black')
                                y += 40
                        all_images = [img]
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except:
                            pass
                elif filename.endswith('.doc'):
                    # Try similar approach
                    try:
                        import subprocess
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.doc') as tmp:
                            tmp.write(file_bytes)
                            tmp_path = tmp.name
                        pdf_path = tmp_path.replace('.doc', '.pdf')
                        result = subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', tmp_path, '--outdir', os.path.dirname(tmp_path)], 
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                        if os.path.exists(pdf_path):
                            with open(pdf_path, 'rb') as f:
                                pdf_bytes = f.read()
                            pages = convert_from_bytes(pdf_bytes)
                            all_images = pages
                            try:
                                sample_text = pytesseract.image_to_string(pages[0])
                                if sample_text.strip():
                                    detected_lang = detect(sample_text)
                            except Exception:
                                pass
                            os.unlink(pdf_path)
                        else:
                            all_images = []
                        os.unlink(tmp_path)
                    except Exception as e:
                        st.error(f"Could not process .DOC file: {e}")
                        all_images = []
                
                st.info(f"Processing {len(all_images)} pages with OCR...")
                st.write(f"Detected language: {detected_lang}")
                
                new_doc = fitz.open()
                progress_bar = st.progress(0)
                
                for page_num, img in enumerate(all_images):
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='PNG')
                    img_bytes = img_byte_arr.getvalue()
                    
                    page_width = img.width * 0.75
                    page_height = img.height * 0.75
                    new_page = new_doc.new_page(width=page_width, height=page_height)
                    new_page.insert_image(fitz.Rect(0, 0, page_width, page_height), stream=img_bytes)
                    
                    try:
                        ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                        n_boxes = len(ocr_data['text'])
                        for i in range(n_boxes):
                            text = ocr_data['text'][i].strip()
                            if int(ocr_data['conf'][i]) > 30 and text:
                                translated = translate_text_offline(text, detected_lang)
                                if translated and translated.strip():
                                    x = ocr_data['left'][i] * 0.75
                                    y = ocr_data['top'][i] * 0.75
                                    w = ocr_data['width'][i] * 0.75
                                    h = ocr_data['height'][i] * 0.75
                                    try:
                                        new_page.insert_textbox(
                                            fitz.Rect(x, y, x + w + 60, y + h + 12),
                                            translated,
                                            fontsize=7,
                                            fontname="helv"
                                        )
                                    except Exception:
                                        pass
                    except Exception as e:
                        pass
                    
                    progress_bar.progress((page_num + 1) / len(all_images))
                
                pdf_output = io.BytesIO()
                new_doc.save(pdf_output)
                pdf_output.seek(0)
                new_doc.close()
                
                st.session_state['processed_id_v3'] = file_id
                st.session_state['pdf_output_v3'] = pdf_output.getvalue()
                st.session_state['detected_lang_v3'] = detected_lang
                st.rerun()
            except Exception as e:
                st.error(f"Error processing document: {e}")
                st.exception(e)
    else:
        detected_lang = st.session_state.get('detected_lang_v3', 'unknown')
        if detected_lang == 'en':
            st.success("Document is in English - ready to download")
        else:
            st.success(f"Translated from {detected_lang} to English (offline OCR)")
        st.download_button(
            label="Download Translated PDF",
            data=st.session_state['pdf_output_v3'],
            file_name=f"translated_{uploaded_file.name.rsplit('.',1)[0]}.pdf",
            mime="application/pdf",
            key="download_btn_v3"
        )
