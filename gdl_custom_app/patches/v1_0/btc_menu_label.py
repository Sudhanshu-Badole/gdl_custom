"""Show the BTC Inventory menu as "Digital Asset Process".

The Workspace Sidebar and Desktop Icon are named after their title/label, so a re-import of the app
files does not change the text of a record that already exists. Set it directly. Idempotent.
"""

import frappe

LABEL = "Digital Asset Process"


def execute():
	for doctype, field in (("Workspace Sidebar", "title"), ("Desktop Icon", "label")):
		if frappe.db.exists(doctype, "BTC Inventory"):
			frappe.db.set_value(doctype, "BTC Inventory", field, LABEL, update_modified=False)
	frappe.clear_cache()
