// Employee Separation (GDL): quick links to the exit interview answers for HR roles.
frappe.ui.form.on("Employee Separation", {
	refresh(frm) {
		const is_hr = ['HR Manager', 'HR User', 'System Manager'].some((r) => frappe.user.has_role(r));
		if (!frm.doc.custom_exit_interview || !is_hr) return;
		frappe.db.get_value("Exit Interview", frm.doc.custom_exit_interview, "custom_response").then((r) => {
			const response = r.message && r.message.custom_response;
			if (response) {
				frm.add_custom_button(
					__("Exit Interview Answers"),
					() => frappe.set_route("Form", "Exit Interview Response", response),
					__("View")
				);
			}
		});
	},
});
