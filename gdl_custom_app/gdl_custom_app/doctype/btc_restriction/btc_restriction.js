// Release and Extend go through server methods so every change is logged with user, time and reason.
frappe.ui.form.on("BTC Restriction", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.state !== "Active") return;

		frm.add_custom_button(__("Release"), () => {
			frappe.prompt(
				[
					{ fieldname: "qty", label: __("Quantity to Release"), fieldtype: "Float", precision: 9, default: frm.doc.remaining_qty, reqd: 1 },
					{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1 },
				],
				(v) => {
					frappe
						.call({ method: "gdl_custom_app.gdl_custom_app.doctype.btc_restriction.btc_restriction.release_restriction", args: { name: frm.doc.name, ...v } })
						.then(() => frm.reload_doc());
				},
				__("Early Release")
			);
		}, __("Actions"));

		frm.add_custom_button(__("Extend Expiry"), () => {
			frappe.prompt(
				[
					{ fieldname: "new_expiry", label: __("New Expiry Date"), fieldtype: "Date", reqd: 1 },
					{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text" },
				],
				(v) => {
					frappe
						.call({ method: "gdl_custom_app.gdl_custom_app.doctype.btc_restriction.btc_restriction.extend_restriction", args: { name: frm.doc.name, ...v } })
						.then(() => frm.reload_doc());
				},
				__("Extend Expiry")
			);
		}, __("Actions"));
	},
});
