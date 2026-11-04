import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from gdl_custom_app.btc import usd_valuation
from gdl_custom_app.btc.balance import get_restricted_qty


def execute(filters=None):
	filters = frappe._dict(filters or {})
	as_of = getdate(filters.posting_date or nowdate())
	item = filters.item_code or frappe.db.get_single_value("GDL Setting", "btc_item")
	cond, params = "", {"company": filters.company, "item": item, "as_of": as_of}
	for f, c in (("warehouse", "warehouse"), ("zone", "zone"), ("wallet", "wallet")):
		if filters.get(f):
			cond += f" and {c} = %({f})s"
			params[f] = filters[f]

	rows = frappe.db.sql(
		f"""select warehouse, zone, wallet, sum(actual_qty) as qty,
		sum(stock_value_difference) as btn_value, max(posting_date) as last_date
		from `tabStock Ledger Entry`
		where company=%(company)s and item_code=%(item)s and is_cancelled=0 and posting_date <= %(as_of)s{cond}
		group by warehouse, zone, wallet having sum(actual_qty) != 0 or max(posting_date) is not null
		order by warehouse, zone, wallet""",
		params, as_dict=True,
	)
	_q, _v, avg = usd_valuation.get_usd_balance(filters.company, item, f"{as_of} 23:59:59")
	zone_cc = dict(frappe.get_all("Internal Zone", fields=["name", "default_cost_center"], as_list=True))
	wallet_info = {w.name: w for w in frappe.get_all("BTC Wallet", fields=["name", "custodian", "category"])}
	for r in rows:
		r.restricted = get_restricted_qty(item, r.warehouse, r.zone, r.wallet, as_of) if r.zone and r.wallet else 0
		r.available = flt(r.qty - r.restricted, 9)
		r.cost_center = zone_cc.get(r.zone)
		r.custodian = (wallet_info.get(r.wallet) or {}).get("custodian")
		r.usd_rate = avg
		r.usd_value = flt(r.qty * avg, 4)
	columns = [
		{"fieldname": "warehouse", "label": _("Warehouse"), "fieldtype": "Link", "width": 160, "options": "Warehouse"},
		{"fieldname": "zone", "label": _("Zone"), "fieldtype": "Link", "width": 120, "options": "Internal Zone"},
		{"fieldname": "cost_center", "label": _("Zone Cost Center (current)"), "fieldtype": "Link", "width": 160, "options": "Cost Center"},
		{"fieldname": "custodian", "label": _("Custodian"), "fieldtype": "Link", "width": 120, "options": "BTC Custodian"},
		{"fieldname": "wallet", "label": _("Wallet"), "fieldtype": "Link", "width": 120, "options": "BTC Wallet"},
		{"fieldname": "qty", "label": _("BTC Quantity"), "fieldtype": "Float", "width": 120},
		{"fieldname": "restricted", "label": _("Restricted Quantity"), "fieldtype": "Float", "width": 120},
		{"fieldname": "available", "label": _("Available Quantity"), "fieldtype": "Float", "width": 120},
		{"fieldname": "btn_value", "label": _("BTN Valuation (standard)"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "usd_value", "label": _("USD Valuation (qty x pool avg)"), "fieldtype": "Float", "width": 120},
		{"fieldname": "usd_rate", "label": _("USD Moving Average Rate"), "fieldtype": "Float", "width": 120},
		{"fieldname": "last_date", "label": _("Last Transaction"), "fieldtype": "Date", "width": 120},
	]
	return columns, rows
