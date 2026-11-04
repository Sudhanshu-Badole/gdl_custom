"""Rename the "Custodian" Inventory Dimension to "Wallet" (it already points at BTC Wallet).

Renames, everywhere the dimension generated them, the columns/Custom Fields
custodian / to_custodian / from_custodian / rejected_custodian ->
wallet / to_wallet / from_wallet / rejected_wallet, keeping all data.
The BTC Wallet.custodian field (link to BTC Custodian) is NOT touched.
Idempotent.
"""

import frappe

RENAMES = {
	"custodian": "wallet",
	"to_custodian": "to_wallet",
	"from_custodian": "from_wallet",
	"rejected_custodian": "rejected_wallet",
}


def execute():
	rename_custom_fields()
	rename_dimension()
	rename_setting()
	frappe.clear_cache()


def rename_custom_fields():
	for cf in frappe.get_all("Custom Field", filters={"fieldname": ["in", list(RENAMES)]}, fields=["name", "dt", "fieldname"]):
		if cf.dt == "BTC Wallet":
			continue
		new = RENAMES[cf.fieldname]
		table = f"tab{cf.dt}"
		if frappe.db.table_exists(cf.dt):
			old_exists = frappe.db.has_column(cf.dt, cf.fieldname)
			if old_exists and not frappe.db.has_column(cf.dt, new):
				frappe.db.sql_ddl(f"alter table `{table}` change `{cf.fieldname}` `{new}` varchar(140)")
		new_name = f"{cf.dt}-{new}"
		if frappe.db.exists("Custom Field", new_name):
			continue
		frappe.db.set_value("Custom Field", cf.name, {"fieldname": new, "label": frappe.db.get_value("Custom Field", cf.name, "label").replace("Custodian", "Wallet")}, update_modified=False)
		frappe.rename_doc("Custom Field", cf.name, new_name, force=True)


def rename_dimension():
	if not frappe.db.exists("Inventory Dimension", "Custodian") or frappe.db.exists("Inventory Dimension", "Wallet"):
		return
	frappe.db.set_value(
		"Inventory Dimension",
		"Custodian",
		{"dimension_name": "Wallet", "source_fieldname": "wallet", "target_fieldname": "wallet"},
		update_modified=False,
	)
	frappe.rename_doc("Inventory Dimension", "Custodian", "Wallet", force=True)


def rename_setting():
	# Single doctype values live in tabSingles; carry the old toggle across.
	old, new = "require_zonecustodian_change_on_transfer", "require_zonewallet_change_on_transfer"
	if frappe.db.exists("Singles", {"doctype": "GDL Setting", "field": new}):
		return
	frappe.db.sql("update tabSingles set field=%s where doctype='GDL Setting' and field=%s", (new, old))
