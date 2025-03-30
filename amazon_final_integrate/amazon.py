import os, csv
import re
import PyPDF2
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract
import warnings
from datetime import datetime
import pandas as pd

##made

def extract_order_details(text, second_page_flag= False):
    """Extract Order ID, SKU, and Quantity from text."""
    # orderid_match = re.search(r"Order\s*(ld|Id|Number):\s*[^0-9]*?(\d+)\s*[-~]?\s*(\d+)\s*[-~]?\s*(\d+)(?=$|\s|[^0-9])", text, re.IGNORECASE)
    if not second_page_flag:
      # orderid_match = re.search(r"Order\s*(1d|ld|Id):\s*[^0-9]*?(\d+)[\s.\-~]*(\d+)[\s.\-~]*(\d+)", text, re.IGNORECASE)
      orderid_match = re.search(r"Order\s*(1d|ld|Id|Number):\s*[^0-9]*?(\d+)[\s.\-~]*(\d+)[\s.\-~]*(\d+)", text, re.IGNORECASE)
      first_page_match = re.search(r"Ship to:|Ship From:", text, re.IGNORECASE)
      
      orderid = f"{orderid_match.group(2)}-{orderid_match.group(3)}-{orderid_match.group(4)}" if orderid_match else None
      number_or_id = orderid_match.group(1) if orderid_match else None
    else:
      orderid_match = re.search(r"Order\s*(1d|ld|Id|Number):\s*[^0-9]*?(\d+)[\s.\-~]*(\d+)[\s.\-~]*(\d+)", text, re.IGNORECASE)
      number_or_id = None
      first_page_match = re.search(r"Ship to:|Ship From:", text, re.IGNORECASE) 
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
    # if not text.strip():
    #     # Convert page to image and apply OCR
    #     pix = page.get_pixmap()
    #     image = convert_from_path(pdf_path, first_page=page.number+1, last_page=page.number+1)[0]
    #     custom_config = r'--oem 3 --psm 6'
    #     text = pytesseract.image_to_string(image, config = custom_config)
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
        #if first page text is empty which is always empty go find order id on the next page or skip that page for now with detals of the page in 
        if text:
            orderid, number_or_id, first_page_match = extract_order_details(text)
            if orderid:
                orderid = orderid.replace("-","")
                orderid = f"{orderid[:3]}-{orderid[3:10]}-{orderid[10:]}"
                order_details = {orderid: [{"sku": d["sku"], "qty": d["quantity-purchased"]} for d in final_output_dict if d["order-id"] == orderid]}
                if orderid not in order_pages and not skip_page_for_now:
                    order_pages[orderid] = []
                elif orderid not in order_pages and skip_page_for_now:
                    #check if order_details is appended in orderpages for that id.
                    order_pages[orderid] = skip_page_for_now
                    order_pages[orderid].append(order_details[orderid])
                    order_details = {}
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
        else:
          skip_page_for_now = [i]
        if order_details and not skip_page_for_now:
            if orderid:
                order_pages[orderid].append(order_details[orderid])
                order_details = {}
            else:
                order_pages[prev_order_id].append(order_details[orderid])
                order_details = {}
        with open("logs/logfile_amazon.txt", "a+", encoding="utf-8") as log_file:
          log_file.write(f"{i+1} page completed.\n")
          log_file.write(f"found {orderid} in {i+1} page with {order_details}\n" if not skip_page_for_now else f"skipping page {i}\n")
    
    # Create PDFs for each OrderID
    with open(pdf_path, "rb") as infile:
        reader = PyPDF2.PdfReader(infile)
        
        for orderid, pages in order_pages.items():
            writer = PyPDF2.PdfWriter()
            for page_num in pages:
                if isinstance(page_num, int):
                  writer.add_page(reader.pages[page_num])
            
            output_pdf_path = os.path.join(output_folder, f"Order_{orderid}.pdf")
            order_pages[orderid].append({"output_pdf_location": output_pdf_path})
            with open(output_pdf_path, "wb") as output_pdf:
                writer.write(output_pdf)
            with open("logs/logfile_amazon.txt", "a+", encoding="utf-8") as log_file:
              log_file.write(f"Saved: {output_pdf_path}\n")
    return order_pages

def txt_to_dataframe(file_path):
    """
    Reads a tab-delimited .txt file and converts it to a Pandas DataFrame.
    :param file_path: Path to the .txt file
    :return: Pandas DataFrame
    """
    df = pd.read_csv(file_path, delimiter='\t')
    return df

def grab_required_fields(data):
    required_columns = ["order-id", "sku", "quantity-purchased"]  # Replace with actual column names
    filtered_data = [{col: row[col] for col in required_columns if col in row} for row in data]
    return filtered_data


if __name__ == "__main__":
    file_path = "scrape_with_excel/amazon_new/amazon.txt"  # Replace with the actual file path
    df = txt_to_dataframe(file_path)
    final_output_dict = grab_required_fields(df.to_dict(orient="records"))
    # Example usage
    warnings.filterwarnings("ignore", category=UserWarning, module="camelot.parsers.base")
    pdf_path = "amazon_final_integrate/amazon.pdf"  # Replace with your PDF file path
    output_folder = "outputs_test/amazon_output_pdfs"  # Folder to save separated PDFs
    with open("logs/logfile_amazon.txt", "w+", encoding="utf-8") as log_file:
      log_file.write(f"Starting the log for mentioned time:{datetime.today().strftime("%Y-%m-%d %H:%M:%S")}\n")
    op = split_pdf_by_orderid(pdf_path, output_folder, final_output_dict)