"""BTC transfer rules on Stock Entry: no self-transfer, status/expiry, availability (incl. fee),
and creation of the destination-side restriction when a status is chosen."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from gdl_custom_app.btc.balance import validate_available
from gdl_custom_app.btc.receipts import get_settings, is_btc_row

RESTRICTED = ("Trading", "Loan", "Pledged")


def _btc_rows(doc):
	settings = get_settings()
	if not settings.enable_btc_rules:
		return []
	return [r for r in doc.get("items") or [] if is_btc_row(settings, r)]


def validate_transfer(doc, method=None):
	for row in _btc_rows(doc):
		status = row.get("custom_transfer_status")
		if status in RESTRICTED:
			if not row.t_warehouse:
				frappe.throw(_("Row #{0}: a restriction status needs a target warehouse.").format(row.idx))
			if not row.get("custom_expiry_date"):
				frappe.throw(_("Row #{0}: Expiry Date is required for status {1}.").format(row.idx, status))
			if getdate(row.custom_expiry_date) < getdate(doc.posting_date):
				frappe.throw(_("Row #{0}: Expiry Date cannot be before the posting date.").format(row.idx))
		elif row.get("custom_expiry_date"):
			frappe.throw(_("Row #{0}: Expiry Date applies only to Trading, Loan or Pledged.").format(row.idx))

		if row.s_warehouse and row.t_warehouse and row.zone == row.to_zone and row.wallet == row.to_wallet:
			frappe.throw(_("Row #{0}: source and destination wallet/zone are the same.").format(row.idx))


def validate_availability(doc, method=None):
	"""before_submit: unrestricted BTC must cover the transfer/issue plus any fee."""
	requests = {}
	for row in _btc_rows(doc):
		if row.s_warehouse:
			key = (row.zone, row.wallet)
			requests[key] = requests.get(key, 0) + flt(row.transfer_qty or row.qty) + flt(row.get("custom_fee_qty"))
	if requests:
		settings = get_settings()
		validate_available(settings.btc_item, settings.btc_warehouse, requests, doc.posting_date, doc.name)


def create_restrictions(doc, method=None):
	for row in _btc_rows(doc):
		status = row.get("custom_transfer_status")
		if status not in RESTRICTED or not row.t_warehouse:
			continue
		if frappe.db.exists("BTC Restriction", {"source_doctype": doc.doctype, "source_name": doc.name, "source_detail": row.name, "state": ["!=", "Cancelled"]}):
			continue
		frappe.get_doc(
			{
				"doctype": "BTC Restriction",
				"company": doc.company,
				"item_code": row.item_code,
				"warehouse": row.t_warehouse,
				"zone": row.to_zone,
				"wallet": row.to_wallet,
				"restriction_type": status,
				"qty": flt(row.transfer_qty or row.qty),
				"start_date": doc.posting_date,
				"expiry_date": row.custom_expiry_date,
				"source_doctype": doc.doctype,
				"source_name": doc.name,
				"source_detail": row.name,
			}
		).insert(ignore_permissions=True)


def cancel_restrictions(doc, method=None):
	for name in frappe.get_all(
		"BTC Restriction", filters={"source_doctype": doc.doctype, "source_name": doc.name, "state": ["!=", "Cancelled"]}, pluck="name"
	):
		r = frappe.get_doc("BTC Restriction", name)
		r.flags.via_service = True
		r.state = "Cancelled"
		r.save(ignore_permissions=True)
