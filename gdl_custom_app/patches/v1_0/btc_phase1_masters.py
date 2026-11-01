"""Phase 1 data setup. Idempotent: safe to re-run.

- Zones: backfill company / is_active (Head Office zone is left for the business to add).
- Custody -> BTC Wallet: each Custody becomes a BTC Wallet with the SAME name (so
  existing stock ledger / row values keep resolving); the custodian is the name
  without its trailing digits (BitGo1 -> BitGo). The business will supply the
  final list; this only preserves current data.
- Repoints the Custodian Inventory Dimension (and its Custom Fields) at BTC Wallet
  and turns on per-dimension negative stock validation for Zone and Custodian.
- Creates the Mining / Premium Received / Put Exercised Stock Entry Types.
"""

import re

import frappe


def execute():
	company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value("Company", {}, "name")
	if not company:
		return

	setup_zones(company)
	migrate_custody(company)
	repoint_dimension()
	create_stock_entry_types()
	frappe.clear_cache()


def setup_zones(company):
	frappe.db.sql("update `tabInternal Zone` set company=%s where ifnull(company,'')=''", company)
	frappe.db.sql("update `tabInternal Zone` set is_active=1 where is_active is null")
	# Head Office is NOT auto-created: the company's default cost center is disabled and
	# which Head Office cost center the business wants is a decision for them.


def migrate_custody(company):
	if not frappe.db.table_exists("Custody"):
		return
	for row in frappe.get_all("Custody", fields=["name", "custody_type"]):
		if frappe.db.exists("BTC Wallet", row.name):
			continue
		custodian = re.sub(r"\d+$", "", row.name).strip() or row.name
		if not frappe.db.exists("BTC Custodian", custodian):
			frappe.get_doc({"doctype": "BTC Custodian", "custodian_name": custodian}).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "BTC Wallet",
				"wallet_name": row.name,
				"category": row.custody_type,
				"custodian": custodian,
				"company": company,
			}
		).insert(ignore_permissions=True)


def repoint_dimension():
	if frappe.db.exists("Inventory Dimension", "Custodian"):
		frappe.db.set_value("Inventory Dimension", "Custodian", "reference_document", "BTC Wallet", update_modified=False)
	frappe.db.sql(
		"update `tabCustom Field` set options='BTC Wallet' where options='Custody' and fieldname in ('custodian','to_custodian','from_custodian','rejected_custodian')"
	)
	for name in ("Zone", "Custodian"):
		if frappe.db.exists("Inventory Dimension", name):
			frappe.db.set_value("Inventory Dimension", name, "validate_negative_stock", 1, update_modified=False)


def create_stock_entry_types():
	for name in ("Mining", "Premium Received", "Put Exercised"):
		if not frappe.db.exists("Stock Entry Type", name):
			frappe.get_doc({"doctype": "Stock Entry Type", "name": name, "purpose": "Material Receipt"}).insert(
				ignore_permissions=True
			)
