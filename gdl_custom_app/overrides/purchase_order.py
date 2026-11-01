from frappe.utils import flt


def validate(doc, method):
    calculate_amount(doc, method)

def calculate_amount(doc, method):
    doc.custom_final_amount = flt(doc.total) - flt(doc.custom_test_discount_amount_)