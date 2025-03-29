import pandas as pd

def csv_to_dataframe(file_path):
    """
    Reads a tab-delimited .txt file and converts it to a Pandas DataFrame.
    :param file_path: Path to the .txt file
    :return: Pandas DataFrame
    """
    df = pd.read_csv(file_path, delimiter=',')
    return df
  
def grab_required_fields(data):
    required_columns = ["ORDER ITEM ID", "SKU", "Quantity"]  # Replace with actual column names
    filtered_data = [{col: row[col] for col in required_columns if col in row} for row in data]
    return filtered_data


if __name__ == "__main__":
    file_path = "scrape_with_excel/flipkart_new/flipkart.csv"  # Replace with the actual file path
    df = csv_to_dataframe(file_path)
    final_output_dict = grab_required_fields(df.to_dict(orient="records"))
