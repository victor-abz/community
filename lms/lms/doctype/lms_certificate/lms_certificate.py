# Copyright (c) 2021, FOSS United and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_years, nowdate
from lms.lms.utils import is_certified
from frappe.email.doctype.email_template.email_template import get_email_template


class LMSCertificate(Document):
	def validate(self):
		self.validate_duplicate_certificate()

	def after_insert(self):
		if not frappe.flags.in_test:
			outgoing_email_account = frappe.get_cached_value(
				"Email Account", {"default_outgoing": 1, "enable_outgoing": 1}, "name"
			)
			if outgoing_email_account or frappe.conf.get("mail_login"):
				self.send_mail()

	def send_mail(self):
		subject = _("Congratulations on getting certified!")
		template = "certification"
		custom_template = frappe.db.get_single_value("LMS Settings", "certification_template")

		args = {
			"student_name": self.member_name,
			"course_name": self.course,
			"course_title": frappe.db.get_value("LMS Course", self.course, "title"),
			"certificate_name": self.name,
			"template": self.template,
		}

		if custom_template:
			email_template = get_email_template(custom_template, args)
			subject = email_template.get("subject")
			content = email_template.get("message")
		frappe.sendmail(
			recipients=self.member,
			subject=subject,
			template=template if not custom_template else None,
			content=content if custom_template else None,
			args=args,
			header=[subject, "green"],
		)

	def validate_duplicate_certificate(self):
		certificates = frappe.get_all(
			"LMS Certificate",
			{"member": self.member, "course": self.course, "name": ["!=", self.name]},
		)
		if len(certificates):
			full_name = frappe.db.get_value("User", self.member, "full_name")
			course_name = frappe.db.get_value("LMS Course", self.course, "title")
			frappe.throw(
				_("{0} is already certified for the course {1}").format(full_name, course_name)
			)

	def on_update(self):
		frappe.share.add_docshare(
			self.doctype,
			self.name,
			self.member,
			write=1,
			share=1,
			flags={"ignore_share_permission": True},
		)


def has_website_permission(doc, ptype, user, verbose=False):
	if ptype in ["read", "print"]:
		return True
	if doc.member == user and ptype == "create":
		return True
	return False


@frappe.whitelist()
def create_certificate(course):
	certificate = is_certified(course)

	if certificate:
		return frappe.db.get_value(
			"LMS Certificate", certificate, ["name", "course", "template"], as_dict=True
		)

	else:
		expires_after_yrs = int(frappe.db.get_value("LMS Course", course, "expiry"))
		expiry_date = None
		if expires_after_yrs:
			expiry_date = add_years(nowdate(), expires_after_yrs)

		default_certificate_template = frappe.db.get_value(
			"Property Setter",
			{
				"doc_type": "LMS Certificate",
				"property": "default_print_format",
			},
			"value",
		)
		if not default_certificate_template:
			default_certificate_template = frappe.db.get_value(
				"Print Format",
				{
					"doc_type": "LMS Certificate",
				},
			)
		certificate = frappe.get_doc(
			{
				"doctype": "LMS Certificate",
				"member": frappe.session.user,
				"course": course,
				"issue_date": nowdate(),
				"expiry_date": expiry_date,
				"template": default_certificate_template,
			}
		)
		certificate.save(ignore_permissions=True)
		return certificate
