

def validate(doc, method):
    calculate_amount(doc, method)

def calculate_amount(doc, method):
    doc.custom_final_amount = doc.total - doc.custom_test_discount_amount_