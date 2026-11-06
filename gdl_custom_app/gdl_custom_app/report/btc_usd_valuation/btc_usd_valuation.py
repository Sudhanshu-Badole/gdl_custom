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
	for f in ("zone", "wallet"):
		if filters.get(f):
			cond += f" and {f} = %({f})s"
			params[f] = filters[f]
	if filters.warehouse:
		cond += " and warehouse = %(warehouse)s"
		params["warehouse"] = filters.warehouse

	opening = usd_valuation.get_usd_balance(filters.company, item, f"{params['from_date']} 00:00:00")
	rows = frappe.db.sql(
		f"""select posting_date, transaction_type, transaction_doctype, transaction_name, zone, wallet, warehouse,
		qty_in, qty_out, usd_rate, usd_incoming_value, usd_outgoing_value, usd_balance_qty as balance_qty,
		usd_balance_value as balance_value, usd_moving_average_rate as avg_rate, btn_exchange_rate, btn_value
		from `tabBTC USD Valuation Ledger`
		where company=%(company)s and item_code=%(item)s and is_cancelled=0
		and posting_date between %(from_date)s and %(to_date)s{cond}
		order by posting_datetime, creation""",
		params, as_dict=True,
	)
	data = [{"transaction_type": _("Opening"), "balance_qty": opening[0], "balance_value": opening[1], "avg_rate": opening[2]}]
	data += rows
	closing = rows[-1] if rows else {"balance_qty": opening[0], "balance_value": opening[1], "avg_rate": opening[2]}
	data.append({"transaction_type": _("Closing"), "qty_in": sum(flt(r.qty_in) for r in rows), "qty_out": sum(flt(r.qty_out) for r in rows),
		"usd_incoming_value": sum(flt(r.usd_incoming_value) for r in rows), "usd_outgoing_value": sum(flt(r.usd_outgoing_value) for r in rows),
		"balance_qty": closing["balance_qty"], "balance_value": closing["balance_value"], "avg_rate": closing["avg_rate"],
		"btn_value": sum(flt(r.btn_value) for r in rows)})
	columns = [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 120},
		{"fieldname": "transaction_type", "label": _("Type"), "fieldtype": "Data", "width": 120},
		{"fieldname": "transaction_doctype", "label": _("DocType"), "fieldtype": "Link", "width": 120, "options": "DocType"},
		{"fieldname": "transaction_name", "label": _("Source"), "fieldtype": "Dynamic Link", "width": 160, "options": "transaction_doctype"},
		{"fieldname": "zone", "label": _("Zone"), "fieldtype": "Link", "width": 120, "options": "Internal Zone"},
		{"fieldname": "wallet", "label": _("Wallet"), "fieldtype": "Link", "width": 120, "options": "BTC Wallet"},
		{"fieldname": "qty_in", "label": _("Qty In"), "fieldtype": "Float", "precision": 8, "width": 120},
		{"fieldname": "qty_out", "label": _("Qty Out"), "fieldtype": "Float", "precision": 8, "width": 120},
		{"fieldname": "usd_rate", "label": _("USD Rate"), "fieldtype": "Float", "width": 120},
		{"fieldname": "usd_incoming_value", "label": _("USD In"), "fieldtype": "Float", "width": 120},
		{"fieldname": "usd_outgoing_value", "label": _("USD Out"), "fieldtype": "Float", "width": 120},
		{"fieldname": "balance_qty", "label": _("Closing Qty"), "fieldtype": "Float", "precision": 8, "width": 120},
		{"fieldname": "balance_value", "label": _("Closing USD Value"), "fieldtype": "Float", "width": 120},
		{"fieldname": "avg_rate", "label": _("USD Avg Rate"), "fieldtype": "Float", "width": 120},
		{"fieldname": "btn_exchange_rate", "label": _("USD to BTN Rate"), "fieldtype": "Float", "width": 120},
		{"fieldname": "btn_value", "label": _("BTN Equivalent"), "fieldtype": "Float", "width": 120},
	]
	return columns, data
