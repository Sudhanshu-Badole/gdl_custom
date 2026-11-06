import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from gdl_custom_app.btc import usd_valuation
from gdl_custom_app.btc.balance import get_restricted_qty


def execute(filters=None):
	"""Compares the independent records and flags differences; never changes data."""
	filters = frappe._dict(filters or {})
	item = filters.item_code or frappe.db.get_single_value("GDL Setting", "btc_item")
	sle = frappe.db.sql(
		"""select warehouse, sum(actual_qty) as sle_qty, sum(stock_value_difference) as btn_value,
		sum(if(ifnull(zone,'')!='' and ifnull(wallet,'')!='', actual_qty, 0)) as wallet_qty
		from `tabStock Ledger Entry` where company=%s and item_code=%s and is_cancelled=0 group by warehouse""",
		(filters.company, item), as_dict=True,
	)
	pool_qty, pool_value, _avg = usd_valuation.get_usd_balance(filters.company, item)
	bins = dict(frappe.db.sql("select warehouse, actual_qty from tabBin where item_code=%s", item))
	rows = []
	for r in sle:
		r.bin_qty = flt(bins.get(r.warehouse), 9)
		r.unassigned_qty = flt(r.sle_qty - r.wallet_qty, 9)
		r.bin_diff = flt(r.sle_qty - r.bin_qty, 9)
		r.usd_pool_qty = pool_qty
		r.usd_pool_value = pool_value
		r.usd_diff = flt(r.sle_qty - pool_qty, 9)
		issues = []
		if r.bin_diff:
			issues.append(_("Bin differs from Stock Ledger"))
		if r.unassigned_qty:
			issues.append(_("{0} BTC has no zone/wallet").format(r.unassigned_qty))
		if r.usd_diff:
			issues.append(_("USD pool differs from Stock Ledger"))
		r.status = "; ".join(issues) or _("OK")
		rows.append(r)
	columns = [
		{"fieldname": "warehouse", "label": _("Warehouse"), "fieldtype": "Link", "width": 160, "options": "Warehouse"},
		{"fieldname": "sle_qty", "label": _("Stock Ledger Qty"), "fieldtype": "Float", "precision": 8, "width": 120},
		{"fieldname": "bin_qty", "label": _("Bin Qty"), "fieldtype": "Float", "precision": 8, "width": 120},
		{"fieldname": "bin_diff", "label": _("Bin Difference"), "fieldtype": "Float", "precision": 8, "width": 120},
		{"fieldname": "wallet_qty", "label": _("Wallet-level Qty"), "fieldtype": "Float", "precision": 8, "width": 120},
		{"fieldname": "unassigned_qty", "label": _("Unassigned Qty"), "fieldtype": "Float", "precision": 8, "width": 120},
		{"fieldname": "usd_pool_qty", "label": _("USD Pool Qty"), "fieldtype": "Float", "precision": 8, "width": 120},
		{"fieldname": "usd_diff", "label": _("USD Pool Difference"), "fieldtype": "Float", "width": 120},
		{"fieldname": "usd_pool_value", "label": _("USD Pool Value"), "fieldtype": "Float", "width": 120},
		{"fieldname": "btn_value", "label": _("BTN Stock Value"), "fieldtype": "Float", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 300},
	]
	return columns, rows
