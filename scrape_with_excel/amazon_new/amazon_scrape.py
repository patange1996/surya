import pandas as pd

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
    file_path = "scrape_with_excel/amazon_new/Waiting.txt"  # Replace with the actual file path
    df = txt_to_dataframe(file_path)
    final_output_dict = grab_required_fields(df.to_dict(orient="records"))
