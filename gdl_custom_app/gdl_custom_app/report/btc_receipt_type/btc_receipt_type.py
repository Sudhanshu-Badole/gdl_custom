import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from gdl_custom_app.btc import usd_valuation
from gdl_custom_app.btc.balance import get_restricted_qty


def execute(filters=None):
	filters = frappe._dict(filters or {})
	item = filters.item_code or frappe.db.get_single_value("GDL Setting", "btc_item")
	cond, params = "", {"company": filters.company, "item": item,
		"from_date": filters.from_date or "1900-01-01", "to_date": filters.to_date or nowdate()}
	for f in ("zone", "wallet", "cost_center"):
		if filters.get(f):
			cond += f" and {f} = %({f})s"
			params[f] = filters[f]
	rows = frappe.db.sql(
		f"""select transaction_type, count(*) as entries, sum(qty_in) as qty, sum(usd_incoming_value) as usd_value,
		sum(btn_value) as btn_value, sum(usd_incoming_value)/nullif(sum(qty_in), 0) as avg_usd_rate
		from `tabBTC USD Valuation Ledger`
		where company=%(company)s and item_code=%(item)s and is_cancelled=0 and direction='In'
		and transaction_type in ('Mining', 'Premium Received', 'Put Exercised', 'Purchase')
		and posting_date between %(from_date)s and %(to_date)s{cond}
		group by transaction_type order by transaction_type""",
		params, as_dict=True,
	)
	columns = [
		{"fieldname": "transaction_type", "label": _("Receipt Type"), "fieldtype": "Data", "width": 120},
		{"fieldname": "entries", "label": _("Entries"), "fieldtype": "Int", "width": 120},
		{"fieldname": "qty", "label": _("BTC Quantity"), "fieldtype": "Float", "precision": 8, "width": 120},
		{"fieldname": "avg_usd_rate", "label": _("Avg USD Rate"), "fieldtype": "Float", "width": 120},
		{"fieldname": "usd_value", "label": _("USD Value"), "fieldtype": "Float", "width": 120},
		{"fieldname": "btn_value", "label": _("BTN Value"), "fieldtype": "Float", "width": 120},
	]
	return columns, rows
