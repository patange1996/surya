import fitz  # PyMuPDF
import os, camelot
import pandas as pd
import re, csv
from itertools import zip_longest
from datetime import datetime

def clean_dict(dict):
  length = len(dict["Qty"])
  filter_len = len(list(filter(lambda x: re.search(r"^\d+$", x), dict["Qty"])))
  if length == filter_len:
    return dict
  cleaned_dict = {}

  for k, v in dict.items():
      key_lower = k.lower()
      if v == "":
          continue
      elif isinstance(v, list):
        cleaned_list = [item for item in v if item != ""]  # Remove empty strings

        if not cleaned_list:
            cleaned_list.append("")  # Skip if list is now empty

        if key_lower == "sku":
            merged = " ".join(str(item) for item in cleaned_list)
            cleaned_dict[k] = [merged]
        elif len(cleaned_list) == 1:
            cleaned_dict[k] = cleaned_list
        elif len(cleaned_list) == 2:
            cleaned_dict[k] = [cleaned_list[0]]  # Keep only the first
        else:
            cleaned_dict[k] = cleaned_list
      else:
          cleaned_dict[k] = v
  return cleaned_dict

def extract_text_with_fitz(input_pdf, page_num, read_all = False):
    doc = fitz.open(input_pdf)

    # Extract text from each page
    data_dict = {}
    page = doc[page_num]
    text = page.get_text("text")
    awb = re.search(r"(\b[A-Z0-9]{6,}\b)\s*Product Details", text.replace("\n"," "))
    match = re.search(r"Product Details\n(.*?)\nTAX INVOICE", text, re.DOTALL)
    purchase_order_no = re.search(r"Purchase Order No.(.*?)Invoice", text.replace("\n"," "), re.IGNORECASE)
    # if purchase_order_no:
    if match and purchase_order_no and read_all:
      lines = match.group(1).split("\n")

      # Remove unwanted values
      remove_values = {"Product Details", "Original For Recipient", "TAX INVOICE"}
      filtered_lines = [line for line in lines if line not in remove_values]
      
      keys = filtered_lines[:5]
      values = filtered_lines[5:]
      
      value_chunks = [values[i:i+5] for i in range(0, len(values), 5)]

      # Create a dictionary
      data_dict = {key: list(vals) for key, vals in zip(keys, zip_longest(*value_chunks, fillvalue=""))}
      total_len = len(data_dict["SKU"])
      data_dict["purchase_order_no"] = [purchase_order_no.group(1).strip() for _ in range(total_len)]
      awb_value = awb.group(1)
      data_dict["AWB"] = [re.sub(r"[^\w]", "", awb_value)for _ in range(total_len)]
      return data_dict
    elif purchase_order_no:
      data_dict["purchase_order_no"] = [purchase_order_no.group(1).strip()]
      awb_value = awb.group(1)
      data_dict["AWB"] = [re.sub(r"[^\w]", "", awb_value)]
      return data_dict
    else:
      return {}

def extract_text_with_camelot(pdf_path, page_number):
    """ Try extracting table using Camelot (works for structured PDFs). """
    tables = camelot.read_pdf(pdf_path, pages=str(page_number))
    if tables.n > 0:
        digit_match = re.compile(r"\d_\d", re.IGNORECASE)
        only_digit_match = re.compile(r"^\d+$", re.IGNORECASE)
        df = tables[0].df
        filtered_df = df[df.apply(lambda row: row.astype(str).str.contains("Product Details", case=False, na=False).any(), axis=1)]
        if filtered_df.empty:
          return {}
        text = filtered_df.iloc[(0,0)]
        # Split the text by newline
        lines = text.split("\n")

        # Remove unwanted values
        remove_values = {"Product Details", "Original For Recipient", "TAX INVOICE"}
        filtered_lines = [line for line in lines if line not in remove_values]
        
        #place the key value in the proper position
        if filtered_lines[4] != "Order No.":
          filtered_lines.insert(4, "Order No.")
        order_matching_pos = [i for i, item in enumerate(filtered_lines) if digit_match.search(item)]
        qty_matching_pos = [i for i, item in enumerate(filtered_lines) if only_digit_match.search(item)]
        if order_matching_pos:
          match_index = order_matching_pos[0]  # Get first match

          if match_index != 9:  # If not already at position 10
              value = filtered_lines.pop(match_index)  # Remove it
              if len(filtered_lines) < 10:  # Ensure the list has enough length
                  filtered_lines.extend([""] * (10 - len(filtered_lines)))  # Fill with empty values if needed
              
              if "free size" in filtered_lines[5].lower():
                  filtered_lines[5] = filtered_lines[5].split("Free Size")[0].strip()
                  filtered_lines.insert(6, "Free Size")
                  filtered_lines.pop()
                  filtered_lines[9] = value  # Insert at position 10  
          if qty_matching_pos:
              qty_match_index = qty_matching_pos[0]
              if qty_match_index != 7:
                filtered_lines = filtered_lines[:qty_match_index] + [""] + filtered_lines[qty_match_index:-1]
                filtered_lines[9] = value
        keys = filtered_lines[:5]
        values = filtered_lines[5:]
        
        value_chunks = [values[i:i+5] for i in range(0, len(values), 5)]

        # Create a dictionary
        data_dict = {key: list(vals) for key, vals in zip(keys, zip_longest(*value_chunks, fillvalue=""))}
        return data_dict 
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
    order_details = {}

    for page_num, page in enumerate(doc):
        # if not page_num >= 1258:
        #   continue
        result_dict = extract_text_with_fitz(input_pdf, page_num)
            # if result_dict.get("Order No.", None):
            #     istext = bool(re.fullmatch(r"[a-zA-Z]+", result_dict.get("Order No.", [None])[0]))
            #     if istext:
            #       result_dict = extract_text_with_camelot(input_pdf, page_num+1)
            # else:
            #     result_dict = extract_text_with_camelot(input_pdf, page_num+1)
        if result_dict.get("purchase_order_no", None):
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
              orderid = i.get("purchase_order_no")
              # orderid = orderid.split("_")[0]
              order_details = {orderid: [{"sku": d["SKU"], "Qty": d["Qty."], "AWB": d["AWB"]} for d in final_output_dict if d["Sub Order No."].split("_")[0] == orderid]}
              if not order_details[orderid]:
                fitz_dict = extract_text_with_fitz(input_pdf, page_num, read_all=True)
                fitz_dict = clean_dict(fitz_dict)
                if not re.search(r"^\d+$", fitz_dict["Qty"][0]):
                  camelot_dict = extract_text_with_camelot(input_pdf, page_num+1)
                  camelot_dict = clean_dict(camelot_dict)
                  camelot_dict["purchase_order_no"] = result_dict.get("purchase_order_no", None)
                  camelot_dict["AWB"] = extract_text_with_fitz(input_pdf, page_num)["AWB"]
                  final_df = pd.DataFrame(camelot_dict)
                else:
                  final_df = pd.DataFrame(fitz_dict)
                # df_filtered = final_df[final_df['Order No.'].str.startswith(orderid)]
                for i in final_df.to_dict(orient="records"):
                  order_details[orderid].append({"sku":i["SKU"], "Qty":i["Qty"], "AWB":i["AWB"]})
              if str(order_details[orderid][0].get("AWB")) != "nan":
                order_pages[order_details[orderid][0]["AWB"]] = []
                order_pages[order_details[orderid][0]["AWB"]].append(order_details[orderid])
                prev_awb = order_details[orderid][0].get("AWB", None)
                order_details = {}
              else:
                order_pages[prev_awb][0].append(order_details[orderid][0])
                order_details = {} 
              with open("logs/logfile_meesho.txt", "a+", encoding="utf-8") as log_file:
                log_file.write(f"Order ID: {orderid}, SKU: {order_pages[prev_awb][0][0]["sku"]}, Qty: {order_pages[prev_awb][0][0]["Qty"]}\n")
            output_pdf_path = os.path.join(output_folder, f"Order_{prev_awb}.pdf")
            order_pages[prev_awb].append({"output_pdf_location" : output_pdf_path})
            print(prev_awb)
            # order_pages[orderid].append({"output_pdf_location" : output_pdf_path})
            new_doc.save(output_pdf_path)
            with open("logs/logfile_meesho.txt", "a+", encoding="utf-8") as log_file:
              log_file.write(f"✅ Split PDF saved as: {output_pdf_path}\n")
              log_file.write("-" * 50 + "\n")
        else:
            new_doc = fitz.open(output_pdf_path)
            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            new_doc.insert_page(-1) 
            with open("logs/logfile_meesho.txt", "a+", encoding="utf-8") as log_file:
              log_file.write(f"❌ Order ID not found in the page {page_num}. Hence concatenating it with previous pdf.\n")
            output_pdf_path_temp = os.path.join(output_folder, f"Order_{orderid_name}_temp.pdf")
            new_doc.save(output_pdf_path_temp)
            os.remove(output_pdf_path)
            os.rename(output_pdf_path_temp, output_pdf_path)
        new_doc.close()
        
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
    required_columns = ["Sub Order No.", "AWB", "SKU", "Qty."]  # Replace with actual column names
    filtered_data = [{col: row[col] for col in required_columns if col in row} for row in data]
    updated_data_list = data = [{**item, "Sub Order No.": item["Sub Order No."].replace("\n", "")} for item in filtered_data]
    return updated_data_list

# Example Usage (30% top, 70% bottom)
if __name__ == "__main__":
    file_path = "meesho_final_integrate/meesho.xlsx"  # Replace with the actual file path
    df = excel_to_dataframe(file_path)
    final_output_dict = grab_required_fields(df.to_dict(orient="records"))
    output_folder = "outputs/meesho_output_pdfs"  # Folder to save separated PDFs
    with open("logs/logfile_meesho.txt", "w+", encoding="utf-8") as log_file:
      log_file.write(f"Starting the log for mentioned time:{datetime.today().strftime("%Y-%m-%d %H:%M:%S")}\n")
    op = split_pdf_custom("meesho_final_integrate/meesho.pdf", output_folder, final_output_dict, top_ratio=0.345)