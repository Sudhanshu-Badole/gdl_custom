"""Show and store BTC quantities to 8 decimals (1 satoshi).

Precision is per field, so this applies to every item on these doctypes; whole
numbers still display without decimals. Idempotent.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

PRECISION = "8"

QTY_FIELDS = {
	"Stock Entry Detail": ("qty", "transfer_qty"),
	"Purchase Order Item": ("qty", "stock_qty"),
	"Purchase Receipt Item": ("qty", "stock_qty", "received_qty", "received_stock_qty"),
	"Sales Order Item": ("qty", "stock_qty"),
	"Delivery Note Item": ("qty", "stock_qty", "actual_qty"),
	"Sales Invoice Item": ("qty", "stock_qty"),
	"Stock Reconciliation Item": ("qty", "current_qty"),
	"Stock Ledger Entry": ("actual_qty", "qty_after_transaction"),
	"Bin": ("actual_qty",),
}


def execute():
	for doctype, fieldnames in QTY_FIELDS.items():
		meta = frappe.get_meta(doctype)
		for fieldname in fieldnames:
			df = meta.get_field(fieldname)
			if not df or df.fieldtype != "Float" or df.precision == PRECISION:
				continue
			make_property_setter(
				doctype, fieldname, "precision", PRECISION, "Select", validate_fields_for_doctype=False
			)
	frappe.db.set_value(
		"Custom Field", {"dt": "Stock Entry Detail", "fieldname": "custom_fee_qty"}, "precision", PRECISION
	)
	for doctype in QTY_FIELDS:
		frappe.clear_cache(doctype=doctype)
