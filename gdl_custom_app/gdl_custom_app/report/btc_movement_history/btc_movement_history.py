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
	for f, c in (("warehouse", "warehouse"), ("zone", "zone"), ("wallet", "wallet")):
		if filters.get(f):
			cond += f" and sle.{c} = %({f})s"
			params[f] = filters[f]

	# Wallet running balance is computed over the whole history, then the date window is applied.
	rows = frappe.db.sql(
		f"""select * from (
			select sle.posting_date, sle.posting_datetime, sle.creation, sle.voucher_type, sle.voucher_no, sle.warehouse, sle.zone,
			sle.wallet, sle.actual_qty, sle.company,
			sum(sle.actual_qty) over (partition by sle.warehouse, sle.zone, sle.wallet
				order by sle.posting_datetime, sle.creation) as wallet_balance,
			coalesce(se.stock_entry_type, sle.voucher_type) as transaction_type,
			coalesce(led.cost_center, sed.cost_center) as cost_center,
			led.usd_outgoing_value, led.usd_incoming_value, led.market_usd_rate, led.usd_moving_average_rate,
			if(se.custom_fee_charge_for is not null and se.custom_fee_charge_for != '', -sle.actual_qty, 0) as fee_qty
			from `tabStock Ledger Entry` sle
			left join `tabStock Entry` se on sle.voucher_type='Stock Entry' and se.name = sle.voucher_no
			left join `tabStock Entry Detail` sed on sed.name = sle.voucher_detail_no
			left join `tabBTC USD Valuation Ledger` led on led.transaction_detail_reference = sle.voucher_detail_no and led.is_cancelled=0
			where sle.company=%(company)s and sle.item_code=%(item)s and sle.is_cancelled=0{cond}
		) t where posting_date between %(from_date)s and %(to_date)s order by posting_datetime, creation""",
		params, as_dict=True,
	)
	for r in rows:
		r.qty_in = r.actual_qty if r.actual_qty > 0 else 0
		r.qty_out = -r.actual_qty if r.actual_qty < 0 else 0
		r.usd_cost = r.usd_outgoing_value or r.usd_incoming_value
	columns = [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 120},
		{"fieldname": "transaction_type", "label": _("Type"), "fieldtype": "Data", "width": 120},
		{"fieldname": "voucher_type", "label": _("DocType"), "fieldtype": "Link", "width": 120, "options": "DocType"},
		{"fieldname": "voucher_no", "label": _("Source"), "fieldtype": "Dynamic Link", "width": 160, "options": "voucher_type"},
		{"fieldname": "warehouse", "label": _("Warehouse"), "fieldtype": "Link", "width": 120, "options": "Warehouse"},
		{"fieldname": "zone", "label": _("Zone"), "fieldtype": "Link", "width": 120, "options": "Internal Zone"},
		{"fieldname": "wallet", "label": _("Wallet"), "fieldtype": "Link", "width": 120, "options": "BTC Wallet"},
		{"fieldname": "cost_center", "label": _("Cost Center"), "fieldtype": "Link", "width": 160, "options": "Cost Center"},
		{"fieldname": "qty_in", "label": _("Qty In"), "fieldtype": "Float", "precision": 8, "width": 120},
		{"fieldname": "qty_out", "label": _("Qty Out"), "fieldtype": "Float", "precision": 8, "width": 120},
		{"fieldname": "fee_qty", "label": _("Network Fee (BTC)"), "fieldtype": "Float", "precision": 8, "width": 120},
		{"fieldname": "usd_cost", "label": _("USD Cost"), "fieldtype": "Float", "width": 120},
		{"fieldname": "market_usd_rate", "label": _("Market USD Rate"), "fieldtype": "Float", "width": 120},
		{"fieldname": "wallet_balance", "label": _("Wallet Balance After"), "fieldtype": "Float", "precision": 8, "width": 120},
	]
	return columns, rows
