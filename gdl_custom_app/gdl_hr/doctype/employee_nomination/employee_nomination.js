const HR_ROLES = ["System Manager", "HR Manager", "HR User"];

frappe.ui.form.on("Employee Nomination", {
	setup(frm) {
		// an employee sees and files only their own record; HR can pick anyone
		frm.set_query("employee", () =>
			HR_ROLES.some((role) => frappe.user.has_role(role)) ? {} : { filters: { user_id: frappe.session.user } }
		);
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.employee) {
			frappe.db
				.get_value("Employee", { user_id: frappe.session.user, status: "Active" }, "name")
				.then((r) => {
					if (r.message && r.message.name) frm.set_value("employee", r.message.name);
				});
		}
	},

	refresh(frm) {
		frm.dashboard.clear_headline();
		if (frm.doc.total_share && frm.doc.total_share !== 100) {
			frm.dashboard.set_headline_alert(
				__("The shares total {0}%. They must total exactly 100% before you submit.", [frm.doc.total_share]),
				"orange"
			);
		}
	},
});

frappe.ui.form.on("Employee Nominee", {
	share_percent(frm) {
		const total = (frm.doc.nominees || []).reduce((sum, row) => sum + (row.share_percent || 0), 0);
		frm.set_value("total_share", Math.round(total * 100) / 100);
	},
	nominees_remove(frm) {
		const total = (frm.doc.nominees || []).reduce((sum, row) => sum + (row.share_percent || 0), 0);
		frm.set_value("total_share", Math.round(total * 100) / 100);
	},
});
