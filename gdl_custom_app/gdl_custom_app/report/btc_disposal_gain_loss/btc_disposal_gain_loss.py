import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from gdl_custom_app.btc import usd_valuation
from gdl_custom_app.btc.balance import get_restricted_qty


def execute(filters=None):
	"""USD inventory-disposal gain/loss for sales and network fees.

	Settlement exchange differences (invoice rate vs payment rate) are posted by
	ERPNext's Payment Entry and are intentionally NOT part of this report.
	"""
	filters = frappe._dict(filters or {})
	item = filters.item_code or frappe.db.get_single_value("GDL Setting", "btc_item")
	cond, params = "", {"company": filters.company, "item": item,
		"from_date": filters.from_date or "1900-01-01", "to_date": filters.to_date or nowdate()}
	for f in ("zone", "wallet"):
		if filters.get(f):
			cond += f" and {f} = %({f})s"
			params[f] = filters[f]
	rows = frappe.db.sql(
		f"""select posting_date, if(transaction_doctype='Delivery Note', 'Sale', 'Network Fee') as disposal_type,
		transaction_doctype, transaction_name, zone, wallet, qty_out, usd_moving_average_rate as avg_rate,
		market_usd_rate, usd_outgoing_value as usd_cost, usd_market_value as usd_proceeds,
		usd_market_difference as usd_gain_loss, btn_exchange_rate, usd_market_difference * btn_exchange_rate as btn_gain_loss
		from `tabBTC USD Valuation Ledger`
		where company=%(company)s and item_code=%(item)s and is_cancelled=0 and direction='Out' and market_usd_rate > 0
		and posting_date between %(from_date)s and %(to_date)s{cond}
		order by posting_datetime, creation""",
		params, as_dict=True,
	)
	columns = [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 120},
		{"fieldname": "disposal_type", "label": _("Disposal"), "fieldtype": "Data", "width": 120},
		{"fieldname": "transaction_doctype", "label": _("DocType"), "fieldtype": "Link", "width": 120, "options": "DocType"},
		{"fieldname": "transaction_name", "label": _("Source"), "fieldtype": "Dynamic Link", "width": 160, "options": "transaction_doctype"},
		{"fieldname": "zone", "label": _("Zone"), "fieldtype": "Link", "width": 120, "options": "Internal Zone"},
		{"fieldname": "wallet", "label": _("Wallet"), "fieldtype": "Link", "width": 120, "options": "BTC Wallet"},
		{"fieldname": "qty_out", "label": _("BTC Disposed"), "fieldtype": "Float", "width": 120},
		{"fieldname": "avg_rate", "label": _("USD Moving Avg"), "fieldtype": "Float", "width": 120},
		{"fieldname": "market_usd_rate", "label": _("USD Sale/Market Rate"), "fieldtype": "Float", "width": 120},
		{"fieldname": "usd_cost", "label": _("USD Inventory Cost"), "fieldtype": "Float", "width": 120},
		{"fieldname": "usd_proceeds", "label": _("USD Proceeds / Market Value"), "fieldtype": "Float", "width": 120},
		{"fieldname": "usd_gain_loss", "label": _("USD Gain / (Loss)"), "fieldtype": "Float", "width": 120},
		{"fieldname": "btn_exchange_rate", "label": _("USD to BTN Rate"), "fieldtype": "Float", "width": 120},
		{"fieldname": "btn_gain_loss", "label": _("BTN Equivalent"), "fieldtype": "Float", "width": 120},
	]
	return columns, rows
