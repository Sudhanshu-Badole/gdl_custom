"""BTC transfer fee: a Material Transfer row carries a fee qty and rate; on
submit, one Material Issue Stock Entry is created that issues the fee qty of
the same item from the same source warehouse.

ERPNext values the issue at the warehouse's weighted-average cost and credits
stock with that. The fee itself is charged at market value (fee qty x Fee
Market Rate x the USD->BTN selling rate frozen on the issue), and the
difference goes to the Disposal Gain/Loss account; see
overrides/stock_entry.py:CustomStockEntry.get_gl_entries. Example:
Dr Fee 2,500.00 / Cr BTC stock 2,067.18 / Cr Disposal Gain 432.82.
"""

import frappe
from frappe import _
from frappe.utils import flt

from gdl_custom_app.btc.exchange import get_usd_rate
from gdl_custom_app.utils.btc import resolve_cost_center


def validate_fee(doc, method=None):
	rows = [r for r in doc.get("items") or [] if flt(r.get("custom_fee_qty")) or flt(r.get("custom_fee_rate"))]
	if not rows:
		return

	if doc.purpose != "Material Transfer":
		frappe.throw(_("Fee Charges can only be entered on a Material Transfer."))

	settings = frappe.get_single("GDL Setting")
	for row in rows:
		if flt(row.custom_fee_qty) <= 0 or flt(row.custom_fee_rate) <= 0:
			frappe.throw(_("Row #{0}: Fee Charges Qty and Rate must both be greater than zero.").format(row.idx))
		if not row.s_warehouse:
			frappe.throw(_("Row #{0}: Fee Charges need a Source Warehouse.").format(row.idx))
		if settings.btc_item and row.item_code != settings.btc_item:
			frappe.throw(_("Row #{0}: Fee Charges apply only to the BTC item {1}.").format(row.idx, settings.btc_item))

	if not settings.fee_expense_account:
		frappe.throw(_("Set the Fee Expense Account in GDL Setting before charging a transfer fee."))
	if not settings.disposal_gain_loss_account:
		frappe.throw(_("Set the Disposal Gain/Loss Account in GDL Setting before charging a transfer fee."))


def create_fee_issue(doc, method=None):
	rows = [r for r in doc.get("items") or [] if flt(r.get("custom_fee_qty")) > 0]
	if not rows or doc.get("custom_fee_stock_entry"):
		return

	settings = frappe.get_single("GDL Setting")
	issue = frappe.new_doc("Stock Entry")
	issue.update(
		{
			"stock_entry_type": "Material Issue",
			"purpose": "Material Issue",
			"company": doc.company,
			"posting_date": doc.posting_date,
			"posting_time": doc.posting_time,
			"set_posting_time": 1,
			"custom_fee_charge_for": doc.name,
			# frozen here so the fee's market value never changes on repost
			"custom_usd_btn_rate": get_usd_rate(doc.posting_date, "for_selling", doc.company),
			"business_line": doc.get("business_line"),
			"remarks": _("Transfer fee for {0}").format(doc.name),
		}
	)

	for row in rows:
		zone = row.get("zone")
		issue.append(
			"items",
			{
				"item_code": row.item_code,
				"s_warehouse": row.s_warehouse,
				"qty": flt(row.custom_fee_qty),
				"uom": row.uom,
				"conversion_factor": row.conversion_factor or 1,
				"expense_account": settings.fee_expense_account,
				"business_line": row.get("business_line") or doc.get("business_line"),
				"zone": zone,
				"wallet": row.get("wallet"),
				"custom_issue_fee_rate": flt(row.custom_fee_rate),
				"cost_center": resolve_cost_center({"cc_zone": zone, "cc_warehouse": row.s_warehouse})
				or row.cost_center,
			},
		)

	issue.insert()
	issue.submit()
	doc.db_set("custom_fee_stock_entry", issue.name, update_modified=False)


def cancel_fee_issue(doc, method=None):
	name = doc.get("custom_fee_stock_entry")
	if name and frappe.db.get_value("Stock Entry", name, "docstatus") == 1:
		frappe.get_doc("Stock Entry", name).cancel()
