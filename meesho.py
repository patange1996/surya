import fitz  # PyMuPDF
import os, camelot
import pandas as pd
import re

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

      # Create a dictionary
      data_dict = dict(zip(keys, values))
      return data_dict

def extract_text_with_camelot(pdf_path, page_number):
    """ Try extracting table using Camelot (works for structured PDFs). """
    tables = camelot.read_pdf(pdf_path, pages=str(page_number))
    if tables.n > 0:
        df = tables[0].df
        filtered_df = df[df.apply(lambda row: row.astype(str).str.contains("Product Details", case=False, na=False).any(), axis=1)]
        text = filtered_df.iloc[(0,0)]
        # Split the text by newline
        lines = text.split("\n")

        # Remove unwanted values
        remove_values = {"Product Details", "Original For Recipient", "TAX INVOICE"}
        filtered_lines = [line for line in lines if line not in remove_values]
        
        keys = filtered_lines[:5]
        values = filtered_lines[5:]

        # Create a dictionary
        data_dict = dict(zip(keys, values))
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
        new_doc = fitz.open()  # Create a new PDF document
        if result_dict := extract_text_with_fitz(input_pdf, page_num):
            if not result_dict.get("Order No.", None):
                result_dict = extract_text_with_camelot(input_pdf, page_num)
        else:
            result_dict = extract_text_with_camelot(input_pdf, page_num)
        if result_dict.get("Order No.", None):
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
            orderid = result_dict.get("Order No.", None)
            orderid = orderid.split("_")[0]
            sku = result_dict.get("SKU", None)
            qty = result_dict.get("Qty", None)
            if orderid:
              output_pdf_path = os.path.join(output_folder, f"Order_{orderid}.pdf")
              new_doc.save(output_pdf_path)
              order_pages[str(orderid)] = result_dict
              print(f"✅ Split PDF saved as: {output_pdf_path}")
              print(f"Order ID: {orderid}, SKU: {sku}, Qty: {qty}")
              print("-" * 50)
            else:
              print("❌ Order ID not found in the page.")
              print("-" * 50)
        else:
            with open("logfile.txt", "w", encoding="utf-8") as log_file:
              log_file.write(f"❌ Order ID not found in the page.{page_num}")
            print("❌ Order ID not found in the page.{page_num}")
        new_doc.close()
    return order_pages

# Example Usage (30% top, 70% bottom)
output_folder = "meesho_output_pdfs"  # Folder to save separated PDFs
final = split_pdf_custom("MEESHO LABEL INVOICE.pdf", output_folder, top_ratio=0.35)
