import frappe
from frappe.utils import flt

from gdl_custom_app.gdl_custom_app.doctype.btc_restriction import btc_restriction as br
from gdl_custom_app.tests import btc_test_utils as u
from gdl_custom_app.tests.test_btc_phase1 import BTCPhase1Base

REPORTS = "gdl_custom_app.gdl_custom_app.report.{0}.{0}.execute"


def run_report(slug, **filters):
	return frappe.get_attr(REPORTS.format(slug))({"company": u.COMPANY, "item_code": u.ITEM, **filters})


class TestSales(BTCPhase1Base):
	def setUp(self):
		super().setUp()
		u.make_receipt(qty=1, usd_rate=50800, date=u.D1)

	def test_g01_sales_order_defaults(self):
		so = u.make_sales_order(submit=False)
		self.assertEqual(so.custom_is_btc, 1)
		self.assertEqual((so.items[0].cost_center, so.items[0].warehouse), (u.CC_A, u.WAREHOUSE))

	def test_g01_sales_order_needs_bucket_and_usd(self):
		with self.assertRaises(frappe.ValidationError):
			u.make_sales_order(bucket=None, submit=False)

	def test_g02_g05_h06_sale_valuation_scenario5(self):
		so = u.make_sales_order(qty=0.399, rate=60000)
		dn = u.make_delivery(so, [(0.399, u.WALLET_A)])
		row = u.ledger(direction="Out")[0]
		self.assertEqual((row.transaction_type, row.transaction_doctype, row.transaction_name), ("Sale", "Delivery Note", dn.name))
		self.assertClose(row.usd_outgoing_value, 20269.20)
		self.assertClose(row.usd_market_value, 23940.00)
		self.assertClose(row.usd_market_difference, 3670.80)
		self.assertEqual(dn.items[0].zone, u.ZONE_A)  # inherited from the order
		self.assertClose(u.wallet_balance(u.WALLET_A), 1 - 0.399, 9)
		# BTN side is ERPNext's own moving-average valuation, untouched by USD amounts
		sle = frappe.get_all("Stock Ledger Entry", filters={"voucher_no": dn.name}, fields=["stock_value_difference"])[0]
		self.assertClose(sle.stock_value_difference, -0.399 * 50800 * 90)

	def test_g03_delivery_exceeds_available(self):
		so = u.make_sales_order(qty=2)
		with self.assertRaises(frappe.ValidationError):
			u.make_delivery(so, [(1.5, u.WALLET_A)])

	def test_g11_wallet_lacks_btc_even_if_warehouse_has(self):
		u.make_receipt(qty=1, wallet=u.WALLET_B, date=u.D1, time="11:00:00")
		so = u.make_sales_order(qty=1.5)
		with self.assertRaises(frappe.ValidationError):
			u.make_delivery(so, [(1.5, u.WALLET_A)])
		u.make_delivery(so, [(1.0, u.WALLET_A), (0.5, u.WALLET_B)])  # a valid two-wallet split

	def test_g04_restricted_btc_cannot_be_delivered_until_released(self):
		r = u.make_restriction(0.4, "Pledged")
		so = u.make_sales_order(qty=1)
		with self.assertRaises(frappe.ValidationError):
			u.make_delivery(so, [(1, u.WALLET_A)])
		u.make_delivery(so, [(0.6, u.WALLET_A)])  # unrestricted part is fine
		br.release_restriction(r.name, 0.4, "cleared")
		u.make_delivery(so, [(0.4, u.WALLET_A)], date=u.D4)

	def test_g06_g07_partial_then_remaining_delivery(self):
		so = u.make_sales_order(qty=1)
		u.make_delivery(so, [(0.4, u.WALLET_A)], date=u.D2)
		self.assertEqual(frappe.db.get_value("Sales Order", so.name, "per_delivered"), 40)
		u.make_delivery(so, [(0.6, u.WALLET_A)], date=u.D3)
		self.assertEqual(frappe.db.get_value("Sales Order", so.name, "per_delivered"), 100)
		out = u.ledger(direction="Out")
		self.assertClose(sum(r.qty_out for r in out), 1)
		self.assertEqual(u.pool()[:2], (0, 0))

	def test_g08_g09_invoice_does_not_duplicate_and_cancels_cleanly(self):
		so = u.make_sales_order(qty=0.399, rate=60000)
		dn = u.make_delivery(so, [(0.399, u.WALLET_A)])
		si = u.make_invoice(dn)
		self.assertEqual(si.update_stock, 0)
		self.assertEqual(len(u.ledger(direction="Out")), 1)
		self.assertEqual(frappe.get_all("Stock Ledger Entry", filters={"voucher_no": si.name}), [])
		gl = frappe.get_all("GL Entry", filters={"voucher_no": si.name, "is_cancelled": 0}, fields=["account", "debit", "credit"])
		self.assertClose(sum(g.credit for g in gl), 23940 * 91)  # BTN revenue at invoice-date rate
		si.cancel()
		self.assertEqual(len(u.ledger(direction="Out")), 1)  # stock belongs to the DN
		self.assertClose(u.wallet_balance(u.WALLET_A), 1 - 0.399, 9)

	def test_invoice_must_not_issue_stock_or_skip_delivery(self):
		so = u.make_sales_order(qty=0.1)
		dn = u.make_delivery(so, [(0.1, u.WALLET_A)])
		si = u.make_invoice(dn, submit=False)
		si.update_stock = 1
		with self.assertRaises(frappe.ValidationError):
			si.save()
		si.update_stock = 0
		si.items[0].delivery_note = None
		with self.assertRaises(frappe.ValidationError):
			si.save()

	def test_g10_h07_scenario5_settlement_exchange_gain(self):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		parent = frappe.db.get_value("Account", "11303 - Sundry Debtors-Others - GDL", "parent_account")
		usd_debtors = frappe.get_doc({"doctype": "Account", "account_name": "TEST BTC Debtors USD", "parent_account": parent,
			"company": u.COMPANY, "account_type": "Receivable", "account_currency": "USD"}).insert(ignore_permissions=True).name
		so = u.make_sales_order(qty=0.399, rate=60000)
		dn = u.make_delivery(so, [(0.399, u.WALLET_A)])
		si = u.make_invoice(dn, rate_btn=91, debit_to=usd_debtors)
		self.assertClose(si.grand_total, 23940)
		self.assertClose(si.base_grand_total, 2178540)
		pe = get_payment_entry("Sales Invoice", si.name, bank_account=u.USD_BANK)
		pe.update({"posting_date": u.D4, "reference_date": u.D4, "reference_no": "T1", "source_exchange_rate": 91.5,
			"target_exchange_rate": 91.5, "business_line": u.BUSINESS_LINE})
		pe.insert()
		pe.submit()
		fx = frappe.db.get_value("Company", u.COMPANY, "exchange_gain_loss_account")
		# ERPNext books the settlement difference in an "Exchange Gain Or Loss" Journal Entry tied to the payment.
		journals = frappe.get_all("Journal Entry Account", filters={"reference_type": "Payment Entry", "reference_name": pe.name}, pluck="parent")
		journals += frappe.get_all("Journal Entry", filters={"voucher_type": "Exchange Gain Or Loss", "docstatus": 1}, pluck="name")
		gl = frappe.get_all("GL Entry", filters={"voucher_no": ["in", list(set(journals)) or [""]], "account": fx, "is_cancelled": 0}, fields=["debit", "credit"])
		self.assertClose(sum(g.credit - g.debit for g in gl), 11970)
		self.assertEqual(sum(1 for g in gl if g.credit), 1)  # exactly once
		self.assertEqual(frappe.get_all("GL Entry", filters={"voucher_no": pe.name, "account": fx}), [])  # not duplicated on the PE
		# the inventory disposal gain is a separate, USD-only figure
		self.assertClose(u.ledger(direction="Out")[0].usd_market_difference, 3670.80)


class TestReports(BTCPhase1Base):
	def setUp(self):
		super().setUp()
		u.set_settings(fee_expense_account=u.DIFFERENCE_ACCOUNT, disposal_gain_loss_account=u.GAIN_LOSS_ACCOUNT)
		u.make_receipt("Mining", qty=1, usd_rate=50800, date=u.D1, zone=u.ZONE_A, wallet=u.WALLET_A)
		u.make_receipt("Purchase" if False else "Premium Received", qty=0.5, usd_rate=50800, date=u.D1, time="11:00:00",
			zone=u.ZONE_B, wallet=u.WALLET_B)

	def test_j01_inventory_balance(self):
		u.make_restriction(0.25, "Loan")
		_cols, rows = run_report("btc_inventory_balance", posting_date=u.D4)
		by = {(r.zone, r.wallet): r for r in rows}
		a, b = by[(u.ZONE_A, u.WALLET_A)], by[(u.ZONE_B, u.WALLET_B)]
		self.assertEqual((a.qty, a.restricted, a.available), (1, 0.25, 0.75))
		self.assertEqual((b.qty, b.available), (0.5, 0.5))
		self.assertEqual(a.cost_center, u.CC_A)
		self.assertClose(a.usd_value, 50800)
		self.assertClose(a.btn_value, 50800 * 90)  # standard BTN valuation, separate from USD

	def test_j02_usd_valuation_report(self):
		u.make_issue(0.5, date=u.D3)
		_c, data = run_report("btc_usd_valuation", from_date=u.D1, to_date=u.D4)
		closing = data[-1]
		self.assertEqual(data[0]["transaction_type"], "Opening")
		self.assertClose(closing["balance_qty"], 1.0)
		self.assertClose(closing["avg_rate"], 50800)
		self.assertClose(closing["usd_outgoing_value"], 25400)

	def test_j04_receipt_type_report(self):
		_c, rows = run_report("btc_receipt_type")
		self.assertEqual({r.transaction_type: r.qty for r in rows}, {"Mining": 1, "Premium Received": 0.5})

	def test_inventory_balance_total_and_cost_per_btc(self):
		_cols, rows = run_report("btc_inventory_balance", posting_date=u.D4)
		total = rows[-1]
		self.assertEqual(total.warehouse, "Total")
		self.assertClose(total.qty, 1.5, 9)
		self.assertClose(total.btn_value, sum(r.btn_value for r in rows[:-1]))
		self.assertClose(total.btn_rate, 50800 * 90, 2)  # BTN cost per BTC
		self.assertClose(total.usd_rate, 50800, 2)  # USD cost per BTC

	def test_j05_movement_history_with_fee(self):
		u.make_transfer(0.3, fee_qty=0.001, fee_rate=61000, date=u.D3)
		_c, rows = run_report("btc_movement_history", wallet=u.WALLET_A)
		fee = next(r for r in rows if r.fee_qty)
		self.assertEqual((fee.fee_qty, fee.market_usd_rate), (0.001, 61000))
		self.assertClose(fee.usd_cost, 50.80)
		self.assertClose(rows[-1].wallet_balance, 1 - 0.301, 9)

	def test_j06_restricted_holdings(self):
		for kind, qty in (("Trading", 0.1), ("Loan", 0.2), ("Pledged", 0.3)):
			u.make_restriction(qty, kind, expiry=u.D4 if kind != "Pledged" else "2026-12-01")
		_c, rows = run_report("btc_restricted_holdings")
		self.assertEqual({r.restriction_type: r.qty for r in rows}, {"Trading": 0.1, "Loan": 0.2, "Pledged": 0.3})
		release = br.release_restriction(rows[0].name, 0.05, "partial")
		_c, rows = run_report("btc_restricted_holdings", state="Active")
		self.assertIn("Early Release 0.05", " ".join(r.release_history for r in rows))

	def test_j07_disposal_report_sale_and_fee(self):
		so = u.make_sales_order(qty=0.399, rate=60000)
		u.make_delivery(so, [(0.399, u.WALLET_A)], date=u.D2)
		u.make_transfer(0.3, fee_qty=0.001, fee_rate=61000, date=u.D3, from_wallet=u.WALLET_A)
		_c, rows = run_report("btc_disposal_gain_loss")
		by = {r.disposal_type: r for r in rows}
		self.assertClose(by["Sale"].usd_gain_loss, 3670.80)
		self.assertClose(by["Network Fee"].usd_gain_loss, 10.20)

	def test_j08_reconciliation_flags_but_does_not_fix(self):
		_c, rows = run_report("btc_reconciliation")
		self.assertEqual(rows[0].status, "OK")
		frappe.db.set_value("BTC USD Valuation Ledger", u.ledger()[-1].name, "usd_balance_qty", 9, update_modified=False)
		_c, rows = run_report("btc_reconciliation")
		self.assertIn("USD pool differs", rows[0].status)
		self.assertEqual(u.pool()[0], 9)  # untouched by the report


class TestBackdating(BTCPhase1Base):
	def test_scenario6_backdated_receipt_and_cancel(self):
		sixty = u.make_receipt(qty=1, usd_rate=60000, date=u.D2)
		so = u.make_sales_order(qty=0.5, rate=65000)
		u.make_delivery(so, [(0.5, u.WALLET_A)], date=u.D4)
		forty = u.make_receipt(qty=1, usd_rate=40000, date=u.D1)  # backdated: average becomes 50,000
		sale = u.ledger(direction="Out")[0]
		self.assertClose(sale.usd_moving_average_rate, 50000)
		self.assertClose(sale.usd_market_difference, 0.5 * 65000 - 25000)
		self.assertEqual(u.pool()[:2], (1.5, 75000))

		sixty.cancel()  # earlier receipt cancelled: sale is re-costed at the remaining 40,000 lot
		sale = u.ledger(direction="Out")[0]
		self.assertClose(sale.usd_moving_average_rate, 40000)
		self.assertClose(sale.usd_market_difference, 0.5 * 65000 - 20000)
		self.assertEqual(u.pool()[:2], (0.5, 20000))
		self.assertEqual(len(u.ledger(is_cancelled=1)), 1)  # audit row kept

		with self.assertRaises(frappe.ValidationError):  # would leave the sale with no BTC
			forty.cancel()
		self.assertEqual(u.pool()[:2], (0.5, 20000))
