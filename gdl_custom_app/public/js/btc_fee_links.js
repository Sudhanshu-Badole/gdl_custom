// Connect a BTC transfer with the fee Material Issue created from it (and back).
// custom_fee_charge_for is plain text on purpose (a Link would block cancelling the pair), so the
// navigation is done here: "View > Fee Issue Entry" on the transfer, "View > Transfer Entry" on the issue.
frappe.ui.form.on("Stock Entry", {
	refresh: (frm) => {
		frm.remove_custom_button(__("Fee Issue Entry"), __("View"));
		frm.remove_custom_button(__("Transfer Entry"), __("View"));
		if (frm.is_new()) return;

		const open = (name) => frappe.set_route("Form", "Stock Entry", name);
		if (frm.doc.custom_fee_stock_entry) {
			frm.add_custom_button(__("Fee Issue Entry"), () => open(frm.doc.custom_fee_stock_entry), __("View"));
			frm.dashboard.add_comment(
				__("Transfer fee issued in {0}", [frappe.utils.get_form_link("Stock Entry", frm.doc.custom_fee_stock_entry, true)]),
				"blue",
				true
			);
		}
		if (frm.doc.custom_fee_charge_for) {
			frm.add_custom_button(__("Transfer Entry"), () => open(frm.doc.custom_fee_charge_for), __("View"));
			frm.dashboard.add_comment(
				__("Fee issue for transfer {0}", [frappe.utils.get_form_link("Stock Entry", frm.doc.custom_fee_charge_for, true)]),
				"blue",
				true
			);
		}
	},
});
