import fitz  # PyMuPDF

# Open the PDF file
pdf_document = "MEESHO LABEL INVOICE.pdf"
doc = fitz.open(pdf_document)

# Extract text from each page
for page_num in range(len(doc)):
    page = doc[page_num]
    text = page.get_text("text")  # Extract text
    print(f"Page {page_num + 1}:\n{text}\n")
