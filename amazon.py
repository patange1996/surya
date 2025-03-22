import os
import re
import PyPDF2
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract
import camelot
import warnings

##made

def extract_table_with_camelot(pdf_path, page_number):
    """ Try extracting table using Camelot (works for structured PDFs). """
    tables = camelot.read_pdf(pdf_path, pages=str(page_number))
    if tables.n > 0:
        df = tables[0].df  # Convert to DataFrame
        df.columns = df.iloc[0] # Set first row as header
        df = df[1:].reset_index(drop=True) # Remove first row
        desc_col = next((col for col in df.columns if 'description' in col.lower()), None)
        qty_col = next((col for col in df.columns if 'qty' in col.lower()), None)
        if desc_col and qty_col and "Qty" in df.columns:
          #remove the rows above "TOTAL:"
          idx = df[df.apply(lambda row: row.astype(str).str.contains('TOTAL:', case=False, na=False).any(), axis=1)].index
          if not idx.empty and idx[0] > 0:
              df = df.iloc[:idx[0]]  # Keep only the rows above "total"
          df_filtered = df[[desc_col, qty_col]]
          df_filtered = df_filtered.copy()
          sku_pattern = r"\(([^)]+)\)\s*HSN:"
          # df_filtered["sku"] = df_filtered[desc_col].str.extract(sku_pattern)
          df_filtered.loc[:, "sku"] = (
              df_filtered[desc_col]
              .str.extract(sku_pattern)[0]  # Extract the first matched group
              .astype(str)
              .str.replace(r"\s+", " ", regex=True)  # Remove newlines and extra spaces
              .str.strip()  # Trim spaces
          )
          df_filtered.drop(columns=desc_col, inplace=True, errors="ignore")
          return df_filtered.to_dict(orient='records')
    return None


def extract_order_details(text):
    """Extract Order ID, SKU, and Quantity from text."""
    # orderid_match = re.search(r"Order\s*(ld|Id|Number):\s*[^0-9]*?(\d+)\s*[-~]?\s*(\d+)\s*[-~]?\s*(\d+)(?=$|\s|[^0-9])", text, re.IGNORECASE)
    orderid_match = re.search(r"Order\s*(ld|Id|Number):\s*[^0-9]*?(\d+)[\s.\-~]*(\d+)[\s.\-~]*(\d+)", text, re.IGNORECASE)
    first_page_match = re.search(r"Ship to:|Ship From:", text, re.IGNORECASE)
    
    orderid = f"{orderid_match.group(2)}-{orderid_match.group(3)}-{orderid_match.group(4)}" if orderid_match else None
    number_or_id = orderid_match.group(1) if orderid_match else None
    
    return orderid, number_or_id, bool(first_page_match)
  
def clean_text(text):
    """Clean text by removing extra spaces, newlines, etc."""
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)  # Remove non-ASCII characters
    text = re.sub(r'\s+', ' ', text).strip()  # Normalize whitespace
    text = text.replace("—", "-")  # Replace OCR misrecognized dashes
    return text

def extract_text_from_page(page):
    """Extract text using PyMuPDF or OCR if necessary."""
    text = page.get_text("text")
    if not text.strip():
        # Convert page to image and apply OCR
        pix = page.get_pixmap()
        image = convert_from_path(pdf_path, first_page=page.number+1, last_page=page.number+1)[0]
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(image, config = custom_config)
    return clean_text(text)

def split_pdf_by_orderid(pdf_path, output_folder):
    """Splits a PDF into separate PDFs based on OrderID."""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    order_pages = {}
    doc = fitz.open(pdf_path)
    skip_page_for_now = []
    prev_order_id= ""
    
    for i, page in enumerate(doc):
        text = extract_text_from_page(page)
        if text:
            order_details = extract_table_with_camelot(pdf_path, i+1)
            orderid, number_or_id, first_page_match = extract_order_details(text)
            if orderid and len(orderid.split("-")[0]) == 3:
                if orderid not in order_pages and not skip_page_for_now:
                    order_pages[orderid] = []
                elif orderid not in order_pages and skip_page_for_now:
                    order_pages[orderid] = skip_page_for_now
                order_pages[orderid].append(i)
                skip_page_for_now = []
                prev_order_id = orderid
            elif number_or_id and number_or_id != "Number":
                skip_page_for_now = [i]
            elif first_page_match:
                skip_page_for_now = [i]
            else:
                order_pages[prev_order_id].append(i)
                prev_order_id = ""
        if order_details and not skip_page_for_now:
            if orderid:
                order_pages[orderid].append(order_details)
            else:
                order_pages[prev_order_id].append(order_details)
        with open("logfile_amazon.txt", "w", encoding="utf-8") as log_file:
          log_file.write(f"{i+1} page completed.")
    
    # Create PDFs for each OrderID
    with open(pdf_path, "rb") as infile:
        reader = PyPDF2.PdfReader(infile)
        
        for orderid, pages in order_pages.items():
            writer = PyPDF2.PdfWriter()
            for page_num in pages:
                if isinstance(page_num, int):
                  writer.add_page(reader.pages[page_num])
            
            output_pdf_path = os.path.join(output_folder, f"Order_{orderid}.pdf")
            with open(output_pdf_path, "wb") as output_pdf:
                writer.write(output_pdf)
            print(f"Saved: {output_pdf_path}")

# Example usage
warnings.filterwarnings("ignore", category=UserWarning, module="camelot.parsers.base")
pdf_path = "AMAZON ORDER LABEL.pdf"  # Replace with your PDF file path
output_folder = "amazon_output_pdfs"  # Folder to save separated PDFs
split_pdf_by_orderid(pdf_path, output_folder)
