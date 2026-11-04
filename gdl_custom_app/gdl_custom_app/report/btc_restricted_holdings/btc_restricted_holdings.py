import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from gdl_custom_app.btc import usd_valuation
from gdl_custom_app.btc.balance import get_restricted_qty


def execute(filters=None):
	filters = frappe._dict(filters or {})
	cond = {"company": filters.company}
	for f, c in (("zone", "zone"), ("wallet", "wallet"), ("status", "restriction_type"), ("state", "state")):
		if filters.get(f):
			cond[c] = filters[f]
	rows = frappe.get_all("BTC Restriction", filters=cond, fields=["name", "wallet", "zone", "restriction_type", "state",
		"qty", "released_qty", "remaining_qty", "start_date", "expiry_date", "original_expiry_date", "item_code", "warehouse"],
		order_by="expiry_date")
	today = getdate(nowdate())
	for r in rows:
		r.restricted_now = r.remaining_qty if r.state == "Active" and r.start_date <= today <= r.expiry_date else 0
		balance = flt(frappe.db.sql("select coalesce(sum(actual_qty),0) from `tabStock Ledger Entry` where item_code=%s and warehouse=%s and zone=%s and wallet=%s and is_cancelled=0",
			(r.item_code, r.warehouse, r.zone, r.wallet))[0][0], 9)
		r.available = flt(balance - get_restricted_qty(r.item_code, r.warehouse, r.zone, r.wallet, today), 9)
		releases = frappe.get_all("BTC Restriction Release", filters={"parent": r.name}, fields=["kind", "qty", "released_by", "released_on"], order_by="released_on")
		r.release_history = "; ".join(f"{x.kind} {x.qty} by {x.released_by} on {x.released_on:%Y-%m-%d}" for x in releases)
	columns = [
		{"fieldname": "name", "label": _("Restriction"), "fieldtype": "Link", "width": 120, "options": "BTC Restriction"},
		{"fieldname": "wallet", "label": _("Wallet"), "fieldtype": "Link", "width": 120, "options": "BTC Wallet"},
		{"fieldname": "zone", "label": _("Zone"), "fieldtype": "Link", "width": 120, "options": "Internal Zone"},
		{"fieldname": "restriction_type", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "state", "label": _("State"), "fieldtype": "Data", "width": 120},
		{"fieldname": "qty", "label": _("Restricted BTC"), "fieldtype": "Float", "width": 120},
		{"fieldname": "released_qty", "label": _("Released"), "fieldtype": "Float", "width": 120},
		{"fieldname": "remaining_qty", "label": _("Remaining Restricted"), "fieldtype": "Float", "width": 120},
		{"fieldname": "available", "label": _("Wallet Available Today"), "fieldtype": "Float", "width": 120},
		{"fieldname": "start_date", "label": _("Start"), "fieldtype": "Date", "width": 120},
		{"fieldname": "expiry_date", "label": _("Expiry"), "fieldtype": "Date", "width": 120},
		{"fieldname": "original_expiry_date", "label": _("Original Expiry"), "fieldtype": "Date", "width": 120},
		{"fieldname": "release_history", "label": _("Release History"), "fieldtype": "Data", "width": 300},
	]
	return columns, rows
