"""Point every Wallet-dimension field at BTC Wallet.

On some sites the dimension-generated fields (e.g. Stock Ledger Entry-wallet) still
linked to BTC Custodian, so submitting a BTC Stock Entry failed with
"Could not find Wallet: <wallet>". The read-only custodian display fields
(custom_*_wallet_custodian) legitimately link to BTC Custodian and are left alone.
Idempotent.
"""

import frappe

WALLET_FIELDS = ("wallet", "to_wallet", "from_wallet", "rejected_wallet")


def execute():
	frappe.db.sql(
		"""update `tabCustom Field` set options='BTC Wallet'
		where fieldname in %(f)s and dt != 'BTC Wallet' and ifnull(options,'') != 'BTC Wallet'""",
		{"f": WALLET_FIELDS},
	)
	if frappe.db.exists("Inventory Dimension", "Wallet"):
		frappe.db.set_value("Inventory Dimension", "Wallet", "reference_document", "BTC Wallet", update_modified=False)
	frappe.clear_cache()
