import fitz  # PyMuPDF
import os, camelot
import pandas as pd
import re
from itertools import zip_longest

def extract_text_with_fitz(input_pdf, page_num):
    doc = fitz.open(input_pdf)

    # Extract text from each page
    page = doc[page_num]
    text = page.get_text("text")
    match = re.search(r"Product Details\n(.*?)\nTAX INVOICE", text, re.DOTALL)
    if match:
      lines = match.group(1).split("\n")

      # Remove unwanted values
      remove_values = {"Product Details", "Original For Recipient", "TAX INVOICE"}
      filtered_lines = [line for line in lines if line not in remove_values]
      
      keys = filtered_lines[:5]
      values = filtered_lines[5:]
      
      value_chunks = [values[i:i+5] for i in range(0, len(values), 5)]

      # Create a dictionary
      data_dict = {key: list(vals) for key, vals in zip(keys, zip_longest(*value_chunks, fillvalue=""))}
      return data_dict

def extract_text_with_camelot(pdf_path, page_number):
    """ Try extracting table using Camelot (works for structured PDFs). """
    tables = camelot.read_pdf(pdf_path, pages=str(page_number))
    if tables.n > 0:
        df = tables[0].df
        filtered_df = df[df.apply(lambda row: row.astype(str).str.contains("Product Details", case=False, na=False).any(), axis=1)]
        if filtered_df.empty:
          return None
        text = filtered_df.iloc[(0,0)]
        # Split the text by newline
        lines = text.split("\n")

        # Remove unwanted values
        remove_values = {"Product Details", "Original For Recipient", "TAX INVOICE"}
        filtered_lines = [line for line in lines if line not in remove_values]
        
        keys = filtered_lines[:5]
        values = filtered_lines[5:]
        
        value_chunks = [values[i:i+5] for i in range(0, len(values), 5)]

        # Create a dictionary
        data_dict = {key: list(vals) for key, vals in zip(keys, zip_longest(*value_chunks, fillvalue=""))}
        return data_dict      


def split_pdf_custom(input_pdf, output_folder, top_ratio=0.4):
    """
    Splits a PDF page into two parts based on a custom split ratio.
    
    :param input_pdf: Path to the input PDF file
    :param top_ratio: Fraction of the page height for the top part (default is 40%)
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    doc = fitz.open(input_pdf)  # Open the input PDF
    
    order_pages = {}

    for page_num, page in enumerate(doc):
        if result_dict := extract_text_with_fitz(input_pdf, page_num):
            istext = bool(re.fullmatch(r"[a-zA-Z]+", result_dict.get("Order No.", None)[0]))
            if not result_dict.get("Order No.", None) or istext:
                result_dict = extract_text_with_camelot(input_pdf, page_num+1)
        else:
            result_dict = extract_text_with_camelot(input_pdf, page_num+1)
        if result_dict:
            new_doc = fitz.open()  # Create a new PDF document
            page = doc[page_num]  # Get current page
            rect = page.rect  # Get original page size
            top_height = rect.height * top_ratio  # Calculate top section height
            bottom_height = rect.height - top_height  # Remaining height for the bottom section

            # --- Create Top Part (Custom Height) ---
            top_rect = fitz.Rect(0, 0, rect.width, top_height)
            top_page = new_doc.new_page(width=rect.width, height=top_height)
            top_page.show_pdf_page(top_page.rect, doc, page_num, clip=top_rect)

            # --- Create Bottom Part (Custom Height) ---
            bottom_rect = fitz.Rect(0, top_height, rect.width, rect.height)
            bottom_page = new_doc.new_page(width=rect.width, height=bottom_height)
            bottom_page.show_pdf_page(bottom_page.rect, doc, page_num, clip=bottom_rect)

            # Save the new PDF with two pages per original page
            df = pd.DataFrame(result_dict)
            orderid_name = "_".join(set([i.split("_")[0] for i in result_dict.get("Order No.", [])]))
            for i in df.to_dict(orient="records"):
              orderid = i.get("Order No.", None)
              orderid = orderid.split("_")[0]
              order_pages[str(orderid)] = i
              print(f"Order ID: {orderid}, SKU: {i.get("SKU", None)}, Qty: {i.get("Qty", None)}")
              print("-" * 50)
            output_pdf_path = os.path.join(output_folder, f"Order_{orderid_name}.pdf")
            new_doc.save(output_pdf_path)
            print(f"✅ Split PDF saved as: {output_pdf_path}")
        else:
            new_doc = fitz.open(output_pdf_path)
            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            new_doc.insert_page(-1) 
            with open("logfile.txt", "w", encoding="utf-8") as log_file:
              log_file.write(f"❌ Order ID not found in the page {page_num}. Hence concatenating it with previous pdf.")
            output_pdf_path_temp = os.path.join(output_folder, f"Order_{orderid_name}_temp.pdf")
            new_doc.save(output_pdf_path_temp)
            os.remove(output_pdf_path)
            os.rename(output_pdf_path_temp, output_pdf_path)
        new_doc.close()
        
    return order_pages

# Example Usage (30% top, 70% bottom)
output_folder = "meesho_output_pdfs"  # Folder to save separated PDFs
final = split_pdf_custom("MEESHO LABEL INVOICE.pdf", output_folder, top_ratio=0.34)
