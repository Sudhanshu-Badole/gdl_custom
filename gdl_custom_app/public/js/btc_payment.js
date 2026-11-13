// BTC invoice receipts: the USD amount received is the invoice's USD value for the BTN being cleared
// (rule in gdl_custom_app/btc/receipts.py get_btc_payment_split; the server re-applies it on save).
// Without this, ERPNext keeps the typed USD amount and re-prices paid_amount when the rate changes,
// which over-receives and leaves an unallocated debtor credit.
frappe.ui.form.on("Payment Entry", {
	refresh: (frm) => gdl_apply_btc_payment_amounts(frm),
	target_exchange_rate: (frm) => gdl_apply_btc_payment_amounts(frm),
	references_add: (frm) => gdl_apply_btc_payment_amounts(frm),
});

frappe.ui.form.on("Payment Entry Reference", {
	allocated_amount: (frm) => gdl_apply_btc_payment_amounts(frm),
});

function gdl_apply_btc_payment_amounts(frm) {
	if (frm.doc.docstatus !== 0 || frm.doc.payment_type !== "Receive" || !(frm.doc.references || []).length) {
		return;
	}
	frappe.call({
		method: "gdl_custom_app.btc.receipts.get_btc_payment_amounts",
		args: { doc: frm.doc },
		callback: (r) => {
			if (!r.message) return;
			const { paid_amount, received_amount } = r.message;
			if (frm.doc.paid_amount !== paid_amount) frm.set_value("paid_amount", paid_amount);
			if (frm.doc.received_amount !== received_amount) frm.set_value("received_amount", received_amount);
		},
	});
}
