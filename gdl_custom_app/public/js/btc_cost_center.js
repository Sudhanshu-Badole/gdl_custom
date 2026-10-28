// Live Cost Center auto-fill on stock rows. The rule lives in
// gdl_custom_app/utils/btc.py (get_row_cost_center) so the browser and the server
// resolve it identically; the server re-applies it on validate regardless.
//
// Loaded by hooks.py doctype_js for each parent doctype, so the guard stops
// the child handlers being registered once per parent opened in a session.
if (!frappe.gdl_btc_cost_center) {
	frappe.gdl_btc_cost_center = true;

	const set_cost_center = (frm, cdt, cdn) => {
		const row = locals[cdt][cdn];
		frappe.call({
			method: "gdl_custom_app.utils.btc.get_row_cost_center",
			args: {
				parent_doctype: frm.doc.doctype,
				purpose: frm.doc.purpose,
				row: {
					zone: row.zone,
					to_zone: row.to_zone,
					s_warehouse: row.s_warehouse,
					t_warehouse: row.t_warehouse,
					warehouse: row.warehouse,
				},
			},
			callback: (r) => {
				if (r.message && r.message !== row.cost_center) {
					frappe.model.set_value(cdt, cdn, "cost_center", r.message);
				}
			},
		});
	};

	const handlers = {};
	["zone", "to_zone", "s_warehouse", "t_warehouse", "warehouse"].forEach((field) => {
		handlers[field] = set_cost_center;
	});

	[
		"Stock Entry Detail",
		"Sales Invoice Item",
		"Delivery Note Item",
		"Purchase Receipt Item",
		"Stock Reconciliation Item",
	].forEach((child) => frappe.ui.form.on(child, handlers));
}
