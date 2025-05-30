import os
import re, csv
import PyPDF2
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract
import camelot
import warnings
from datetime import datetime


def extract_table_with_camelot(pdf_path, page_number):
    """ Try extracting table using Camelot (works for structured PDFs). """
    tables = camelot.read_pdf(pdf_path, pages=str(page_number))
    if tables.n > 0:
        df = tables[0].df  # Convert to DataFrame
        df.columns = df.iloc[0] # Set first row as header
        df = df[1:].reset_index(drop=True) # Remove first row
        df.columns = df.columns.str.replace(r"[\t\n]", " ", regex=True).str.strip()
        df = df.apply(lambda col: col.astype(str).str.replace("\t", " ").str.replace("\n", " ").str.strip())
        desc_col = next((col for col in df.columns if 'item name' in col.lower()), None)
        qty_col = next((col for col in df.columns if 'qty' in col.lower()), None)
        if desc_col and qty_col and "Qty" in df.columns:
          #remove the rows above "TOTAL:"
          idx = df[df.apply(lambda row: row.astype(str).str.contains('Total IGST Amount', case=False, na=False).any(), axis=1)].index
          if not idx.empty and idx[0] > 0:
              df = df.iloc[:idx[0]]  # Keep only the rows above "total"
          df_filtered = df[[desc_col, qty_col]]
          df_filtered = df_filtered.copy()
          sku_pattern = r'Style Code:\s*"([^"]+)"'
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
    # need to change the regex pattern to match the order id
    orderid_match = re.search(r"Order No\s*:\s*([\w\d]+)", text, re.IGNORECASE) or re.search(r"W(\w{1,})(?=\w\s+Sold By)", text, re.IGNORECASE)
    scanner_page_match = re.search(r"Ship to:|Ship From:", text, re.IGNORECASE)
    
    orderid = orderid_match.group(1) if orderid_match else None
    
    return orderid, bool(scanner_page_match)
  
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
            orderid, scanner_page_match = extract_order_details(text)
            if orderid:
                if orderid not in order_pages and not skip_page_for_now:
                    order_pages[orderid] = []
                elif orderid not in order_pages and skip_page_for_now:
                    order_pages[orderid] = skip_page_for_now
                order_pages[orderid].append(i)
                skip_page_for_now = []
                prev_order_id = orderid
            elif scanner_page_match:
                skip_page_for_now = [i]
            else:
                order_pages[prev_order_id].append(i)
                prev_order_id = ""
        if order_details and not skip_page_for_now:
            if orderid:
                order_pages[orderid].append(order_details)
            else:
                order_pages[prev_order_id].append(order_details)
        with open("logs/logfile_firstcry.txt", "a+", encoding="utf-8") as log_file:
          log_file.write(f"{i+1} page completed.\n")
    
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
            with open("logs/logfile_firstcry.txt", "a+", encoding="utf-8") as log_file:
                log_file.write(f"Saved: {output_pdf_path}\n")
    return order_pages

# Example usage
warnings.filterwarnings("ignore", category=UserWarning, module="camelot.parsers.base")
pdf_path = "scrape_with_pdf/FIRSTCRY COMBINE.pdf"  # Replace with your PDF file path
output_folder = "outputs/firstcry_output_pdfs"  # Folder to save separated PDFs
with open("logs/logfile_firstcry.txt", "w+", encoding="utf-8") as log_file:
  log_file.write(f"Starting the log for mentioned time:{datetime.today().strftime("%Y-%m-%d %H:%M:%S")}\n")
op = split_pdf_by_orderid(pdf_path, output_folder)
columns = set()
for values in op.values():
  for i in values:
    if isinstance(i, list):
      columns.update(i[0].keys())

# Sort columns (optional)
columns = sorted(columns)

# Open the CSV file for writing
with open("outputs/output_firstcry.csv", "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    
    # Write header (first column as "Name" + all extracted columns)
    writer.writerow(["orderid"] + columns)
    
    # Write data rows
    for key, values in op.items():
        for v in values:
          if isinstance(v, list):
            for j in v:
              row = [key] + [j.get(col, "") for col in columns]  # Fill missing columns with empty values
        writer.writerow(row)

print("CSV file created successfully!, Closing the Script\n")
