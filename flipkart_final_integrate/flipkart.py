import fitz  # PyMuPDF
import os, camelot
import pandas as pd
import re, csv
from itertools import zip_longest
from datetime import datetime
import numpy as np

def extract_text_with_fitz(input_pdf, page_num, only_orderid=False):
    doc = fitz.open(input_pdf)

    # Extract text from each page
    if only_orderid:
      page = doc[page_num-1]
    else:
      page = doc[page_num]
    text = page.get_text("text")
    order_id_match = re.search(r"E-Kart Logistics\s*\n*(OD\d+)", text)
    if only_orderid:
      return order_id_match.group(1)
    match = re.search(r"SKU(.*?)Invoice", text, re.DOTALL)
    if match:
      lines = match.group(1).split("\n")
      # lines = re.sub(r'FMPC.*', '', match.group(1), flags=re.DOTALL)

      # Remove unwanted values
      filtered_lines = lines[:4]
      
      keys = filtered_lines[:2]
      values = filtered_lines[2:]
      
      value_chunks = [values[i:i+2] for i in range(0, len(values), 2)]

      # Create a dictionary
      data_dict = {key: list(vals) for key, vals in zip(keys, zip_longest(*value_chunks, fillvalue=""))}
      data_dict["Order No."] = [order_id_match.group(1)]
      #check if qty is a digit
      if not re.search(r"^\d+$", data_dict["QTY"][0]):
        return {}
      return data_dict
    else:
      return {}

def extract_text_with_camelot(pdf_path, page_number):
    """ Try extracting table using Camelot (works for structured PDFs). """
    tables = camelot.read_pdf(pdf_path, pages=str(page_number), flavor="lattice")
    if tables.n > 0:
        digit_match = re.compile(r"\d_\d", re.IGNORECASE)
        df = tables[0].df
        # Find indices of rows where any cell contains "SKU"
        sku_indices = df.index[
            df.apply(lambda row: row.astype(str).str.contains("SKU", case=False, na=False).any(), axis=1)
        ].tolist()

        # Include the next row index as well (if within bounds)
        extended_indices = sku_indices + [i + 1 for i in sku_indices if i + 1 < len(df)]

        # Drop duplicates and sort to maintain order
        extended_indices = sorted(set(extended_indices))

        # Extract those rows
        filtered_df = df.loc[extended_indices].reset_index(drop=True)
        if filtered_df.empty:
          return {}
        filtered_df = filtered_df.replace(r'^\s*$', np.nan, regex=True)
        filtered_df = filtered_df.where(pd.notnull(filtered_df), np.nan)
        filtered_df.dropna(how='all', inplace=True)  
        filtered_df.dropna(axis=1, how='all', inplace=True)
        filtered_df.reset_index(drop=True, inplace=True)
        filtered_df.columns = filtered_df.iloc[0]
        filtered_df = filtered_df[1:]
        order_id = extract_text_with_fitz(pdf_path, page_number, only_orderid=True)
        filtered_df.loc[:, 'Order No.'] = [order_id]
        filtered_df = filtered_df.rename(columns={'SKU ID | Description': ' ID | Description'})
        return filtered_df.to_dict(orient='list')
    else:
      return {} 


def split_pdf_custom(input_pdf, output_folder, final_output_dict, top_ratio=0.4):
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
            if not result_dict.get("Order No.", None):
              result_dict = extract_text_with_camelot(input_pdf, page_num+1)
        else:
            result_dict = extract_text_with_camelot(input_pdf, page_num+1)
        if result_dict.get("Order No.", None):
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
              order_details = {orderid: [{"sku": d["SKU"], "Qty": d["Quantity"]} for d in final_output_dict if d["Order Id"] == orderid]}
              if not order_details[orderid]:
                sku = i.get(" ID | Description", None).split("|")[0].split(" ")[1] if i.get(" ID | Description", None) else ""
                order_details[orderid] = {
                "sku" : sku,
                "Qty" : i.get("QTY", None),
              }
              order_pages[str(orderid)] = order_details[orderid]
              with open("logs/logfile_flipkart.txt", "a+", encoding="utf-8") as log_file:
                log_file.write(f"Order ID: {orderid}, SKU: {sku}, Qty: {i.get("QTY", None)}\n")
                log_file.write("-" * 50 + "\n")
            output_pdf_path = os.path.join(output_folder, f"Order_{orderid_name}.pdf")
            new_doc.save(output_pdf_path)
            with open("logs/logfile_flipkart.txt", "a+", encoding="utf-8") as log_file:
              log_file.write(f"✅ Split PDF saved as: {output_pdf_path}\n")
        else:
            new_doc = fitz.open(output_pdf_path)
            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            new_doc.insert_page(-1) 
            with open("logs/logfile_flipkart.txt", "a+", encoding="utf-8") as log_file:
              log_file.write(f"❌ Order ID not found in the page {page_num}. Hence concatenating it with previous pdf.\n")
            output_pdf_path_temp = os.path.join(output_folder, f"Order_{orderid_name}_temp.pdf")
            new_doc.save(output_pdf_path_temp)
            os.remove(output_pdf_path)
            os.rename(output_pdf_path_temp, output_pdf_path)
        new_doc.close()
        
    return order_pages
  
def csv_to_dataframe(file_path):
    """
    Reads a tab-delimited .txt file and converts it to a Pandas DataFrame.
    :param file_path: Path to the .txt file
    :return: Pandas DataFrame
    """
    df = pd.read_csv(file_path, delimiter=',')
    return df
  
def grab_required_fields(data):
    required_columns = ["Order Id", "SKU", "Quantity"]  # Replace with actual column names
    filtered_data = [{col: row[col] for col in required_columns if col in row} for row in data]
    return filtered_data
  

if __name__ == "__main__":
    pd.set_option('future.no_silent_downcasting', True)
    file_path = "flipkart_final_integrate/flipkart.csv"  # Replace with the actual file path
    df = csv_to_dataframe(file_path)
    final_output_dict = grab_required_fields(df.to_dict(orient="records"))
    output_folder = "outputs/flipkart_output_pdfs"  # Folder to save separated PDFs
    with open("logs/logfile_flipkart.txt", "w+", encoding="utf-8") as log_file:
      log_file.write(f"Starting the log for mentioned time:{datetime.today().strftime("%Y-%m-%d %H:%M:%S")}\n")
    op = split_pdf_custom("flipkart_final_integrate/flipkart.pdf", output_folder, final_output_dict, top_ratio=0.46)