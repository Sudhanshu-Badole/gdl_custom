"""Sales Invoice GL for BTC sales: disposal gain/loss split.

The Delivery Note books the BTC at weighted-average cost (Dr Revenue from BTC /
Cr BTC stock). ERPNext's invoice then credits the whole invoice value to the
income account. Here we move the difference out of revenue:

    cost = cost booked by the Delivery Note row (pro-rated for partial invoices)
    diff = invoice amount (BTN) - cost
    Dr Revenue from BTC  diff   (so revenue is credited at the delivered cost)
    Cr Disposal Gain/Loss diff  (sides swap when it is a loss)
"""

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from frappe import _
from frappe.utils import flt

from gdl_custom_app.btc.receipts import get_settings, is_btc_row


class CustomSalesInvoice(SalesInvoice):
	def get_gl_entries(self, inventory_account_map=None):
		gl_entries = super().get_gl_entries(inventory_account_map)
		gl_entries.extend(self.get_disposal_gain_loss_gl_entries())
		return gl_entries

	def get_disposal_gain_loss_gl_entries(self):
		settings = get_settings()
		if not settings.enable_btc_rules or self.is_return:
			return []
		gain_loss_account = settings.disposal_gain_loss_account
		if not gain_loss_account:
			return []

		precision = self.precision("base_net_amount", "items")
		entries = []
		for row in self.get("items"):
			if not is_btc_row(settings, row) or not row.get("dn_detail"):
				continue

			delivered = frappe.db.get_value(
				"Delivery Note Item", row.dn_detail, ["stock_qty", "parent"], as_dict=True
			)
			if not delivered or not flt(delivered.stock_qty):
				continue
			dn_cost = -flt(
				frappe.db.sql(
					"""select sum(stock_value_difference) from `tabStock Ledger Entry`
					where voucher_type='Delivery Note' and voucher_no=%s and voucher_detail_no=%s
					and is_cancelled=0""",
					(delivered.parent, row.dn_detail),
				)[0][0]
			)
			cost = flt(dn_cost * flt(row.stock_qty) / flt(delivered.stock_qty), precision)
			diff = flt(flt(row.base_net_amount) - cost, precision)
			if not diff:
				continue

			# gain: Dr revenue / Cr gain-loss; loss: the reverse
			debit_account, credit_account = (
				(row.income_account, gain_loss_account) if diff > 0 else (gain_loss_account, row.income_account)
			)
			amount = abs(diff)
			remarks = _("Disposal gain/loss: invoiced {0} vs delivered cost {1}").format(
				flt(row.base_net_amount, precision), cost
			)
			for account, against, field in (
				(debit_account, credit_account, "debit"),
				(credit_account, debit_account, "credit"),
			):
				entries.append(
					self.get_gl_dict(
						{
							"account": account,
							"against": against,
							"cost_center": row.cost_center,
							"remarks": remarks,
							field: amount,
							f"{field}_in_account_currency": amount,
						},
						item=row,
					)
				)
		return entries
