import os, csv
import re, camelot
import PyPDF2
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract
import warnings
from datetime import datetime
import pandas as pd

##made
def extract_table_with_camelot(pdf_path, page_number):
    """ Try extracting table using Camelot (works for structured PDFs). """
    tables = camelot.read_pdf(pdf_path, pages=str(page_number))
    if tables.n > 0:
        df = tables[0].df  # Convert to DataFrame
        df.columns = df.iloc[0] # Set first row as header
        df = df[1:].reset_index(drop=True) # Remove first row
        desc_col = next((col for col in df.columns if 'item' in col.lower()), None)
        qty_col = next((col for col in df.columns if 'qty' in col.lower()), None)
        if desc_col and qty_col and any("Qty" in col for col in df.columns):
          #remove the rows above "TOTAL:"
          idx = df[df.apply(lambda row: row.astype(str).str.contains('Total', case=False, na=False).any(), axis=1)].index
          if not idx.empty and idx[0] > 0:
              df = df.iloc[:idx[0]]  # Keep only the rows above "total"
          df_filtered = df[[desc_col, qty_col]]
          df_filtered = df_filtered.copy()
          df_filtered["Item\tName"] = df_filtered["Item\tName"].map(
              lambda x: re.sub(r"\s+", " ", str(x)).strip() if pd.notnull(x) else None
          )
          sku_pattern = r'Style.*Code:.*"(.*)"'
          # df_filtered["sku"] = df_filtered[desc_col].str.extract(sku_pattern)
          df_filtered.loc[:, "sku"] = (
              df_filtered[desc_col]
              .str.extract(sku_pattern)[0]  # Extract the first matched group
              .astype(str)
              .str.replace(r"\s+", " ", regex=True)  # Remove newlines and extra spaces
              .str.strip()  # Trim spaces
          )
          matching_cols = [col for col in df_filtered.columns if "Qty" in col]
          if matching_cols:
              df.rename(columns={matching_cols[0]: "Qty"}, inplace=True)
          df_filtered.drop(columns=desc_col, inplace=True, errors="ignore")
          return df_filtered.to_dict(orient='records')
    return {}

def extract_order_details(text):
    """Extract Order ID, SKU, and Quantity from text."""
    # need to change the regex pattern to match the order id
    orderid_match = re.search(r"Order No\s*:\s*([\w\d]+)", text, re.IGNORECASE)
    scanner_page_match = re.search(r"Ship to:|Ship From:", text, re.IGNORECASE)
    shipment_id_match = re.search(r"Shipment ID\s*:\s*(\d+)", text)
    
    orderid = orderid_match.group(1) if orderid_match else None
    shipment_id = shipment_id_match.group(1) if shipment_id_match else "Not Found"
    
    return orderid, bool(scanner_page_match), shipment_id
  
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

def split_pdf_by_orderid(pdf_path, output_folder, final_output_dict):
    """Splits a PDF into separate PDFs based on OrderID."""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    order_pages = {}
    doc = fitz.open(pdf_path)
    skip_page_for_now = []
    prev_order_id= ""
    order_details = {}
    
    for i, page in enumerate(doc):
        text = extract_text_from_page(page)
        if text:
            orderid, scanner_page_match, shipmentid = extract_order_details(text)
            if orderid != prev_order_id:
              if orderid:
                prev_order_id = orderid
            if orderid:
                order_details = {orderid: [{"sku": d["Vendor Style Code"], "Qty": d["Total Qty"], "Items": d["Total Items"], "shipment_id": d["AWB No"]} for d in final_output_dict if d["Order ID"] == orderid]}
                if not order_details[orderid]:
                  order_details[orderid] = extract_table_with_camelot(pdf_path, i+1)
                  [d.update({'Items': len(order_details[orderid])}) for d in order_details[orderid]]
                  [d.update({'shipment_id': shipmentid}) for d in order_details[orderid]]
                  with open("logs/logfile_firstcry.txt", "a+", encoding="utf-8") as log_file:
                    log_file.write(f"{orderid} Not found from csv, hence scraping it from pdf itself.\n")
                else:
                  with open("logs/logfile_firstcry.txt", "a+", encoding="utf-8") as log_file:
                    log_file.write(f"{orderid} found from csv.\n")
                if orderid not in order_pages and not skip_page_for_now:
                    order_pages[orderid] = []
                elif orderid not in order_pages and skip_page_for_now:
                    order_pages[orderid] = skip_page_for_now
                order_pages[orderid].append(i)
                skip_page_for_now = []
            elif scanner_page_match:
                skip_page_for_now = [i]
            else:
                order_pages[prev_order_id].append(i)
        if order_details and not skip_page_for_now:
            if orderid:
                order_pages[orderid].append(order_details[orderid])
                order_details = {}
            else:
                order_pages[prev_order_id].append(order_details[orderid])
                order_details = {}
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
            order_pages[orderid].append({"output_pdf_location" : output_pdf_path})
            with open(output_pdf_path, "wb") as output_pdf:
                writer.write(output_pdf)
            with open("logs/logfile_firstcry.txt", "a+", encoding="utf-8") as log_file:
                log_file.write(f"Saved: {output_pdf_path}\n")
    #For testing created a csv.
    rows = [{"item": item} for _, items in order_pages.items() for item in items if isinstance(item, list)]
    flat_list = [item for entry in rows for item in entry["item"]]
    df = pd.DataFrame(flat_list)
    df.to_csv("order_pages.csv", index=False)
    return order_pages

def excel_to_dataframe(file_path):
    """
    Reads a tab-delimited .txt file and converts it to a Pandas DataFrame.
    :param file_path: Path to the .txt file
    :return: Pandas DataFrame
    """
    df = pd.read_excel(file_path)
    return df

def grab_required_fields(data):
    required_columns = ["Order ID", "Vendor Style Code", "Total Items", "Total Qty", "AWB No"]  # Replace with actual column names
    filtered_data = [{col: row[col] for col in required_columns if col in row} for row in data]
    return filtered_data


if __name__ == "__main__":
    pd.set_option('future.no_silent_downcasting', True)
    file_path = "first_cry_final_integrate/firstcry.xlsx"  # Replace with the actual file path
    df = excel_to_dataframe(file_path)
    final_output_dict = grab_required_fields(df.to_dict(orient="records"))
    # Example usage
    warnings.filterwarnings("ignore", category=UserWarning, module="camelot.parsers.base")
    pdf_path = "first_cry_final_integrate/firstcry.pdf"  # Replace with your PDF file path
    output_folder = "outputs/firstcry_output_pdfs"  # Folder to save separated PDFs
    with open("logs/logfile_firstcry.txt", "w+", encoding="utf-8") as log_file:
      log_file.write(f"Starting the log for mentioned time:{datetime.today().strftime("%Y-%m-%d %H:%M:%S")}\n")
    op = split_pdf_by_orderid(pdf_path, output_folder, final_output_dict)