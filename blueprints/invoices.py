import hashlib
import hmac
from datetime import datetime, UTC
from io import BytesIO

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user
from flask_mail import Message
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from extensions import csrf, db, mail
from models import FINANCE_ROLES, Invoice, Setting, Shift, Site

invoices_bp = Blueprint("invoices", __name__, url_prefix="/invoices")

# Payment webhooks are called by external gateways with no user session; they
# are authenticated by signature instead of role and so bypass the guard below.
_WEBHOOK_ENDPOINTS = {"invoices.stripe_webhook", "invoices.paypal_webhook"}


@invoices_bp.before_request
def _restrict_to_finance_roles():
    """Shift-to-Invoice: Owners and Ops Managers only.

    HR/Compliance and all frontline roles are explicitly excluded from
    corporate financial/billing data per GDPR data-isolation requirements.
    Payment webhooks are exempt (unauthenticated, signature-verified callers).
    """
    if request.endpoint in _WEBHOOK_ENDPOINTS:
        return None
    # Unauthenticated requests are already redirected by the app-wide session
    # policy; this is defence-in-depth for the financial blueprint.
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    if current_user.role not in FINANCE_ROLES:
        abort(403)


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


def _next_invoice_number(site):
    count = Invoice.query.filter_by(site_id=site.id).count() + 1
    return f"INV-{site.id:03d}-{datetime.now(UTC):%Y%m}-{count:03d}"


@invoices_bp.route("/")
def list_invoices():
    invoices = Invoice.query.order_by(Invoice.issue_date.desc()).all()
    return render_template("invoices/list.html", invoices=invoices)


@invoices_bp.route("/generate", methods=["GET", "POST"])
def generate():
    sites = Site.query.filter_by(is_active=True).order_by(Site.name.asc()).all()

    if request.method == "POST":
        site = Site.query.get_or_404(int(request.form["site_id"]))
        period_start = _parse_date(request.form["period_start"])
        period_end = _parse_date(request.form["period_end"])

        if not period_start or not period_end or period_start > period_end:
            flash("Please choose a valid invoice period.", "error")
            return render_template("invoices/generate.html", sites=sites, form_data=request.form)

        eligible_shifts = (
            Shift.query.filter(
                Shift.site_id == site.id,
                Shift.guard_id.isnot(None),
                Shift.status == "completed",
                Shift.approved_by_manager.is_(True),
                Shift.invoice_id.is_(None),
                Shift.shift_date >= period_start,
                Shift.shift_date <= period_end,
            )
            .order_by(Shift.shift_date.asc())
            .all()
        )

        if not eligible_shifts:
            flash("No completed, un-invoiced shifts found for that site and period.", "error")
            return render_template("invoices/generate.html", sites=sites, form_data=request.form)

        invoice = Invoice(
            invoice_number=_next_invoice_number(site),
            site_id=site.id,
            period_start=period_start,
            period_end=period_end,
            total_amount=0,
        )
        db.session.add(invoice)
        db.session.flush()  # assign invoice.id before linking shifts

        total = 0
        for shift in eligible_shifts:
            role_override = request.form.get(f"role_{shift.id}")
            if role_override is not None:
                shift.role = role_override.strip()

            rate_override = request.form.get(f"rate_{shift.id}")
            if rate_override:
                try:
                    new_rate = float(rate_override)
                    if new_rate >= 0:
                        shift.bill_rate = new_rate
                except ValueError:
                    pass

            hours_override = request.form.get(f"hours_{shift.id}")
            if hours_override:
                try:
                    new_hours = float(hours_override)
                    if new_hours >= 0:
                        shift.total_hours = new_hours
                except ValueError:
                    pass

            shift.invoice_id = invoice.id
            shift.status = "invoiced"
            total += shift.bill_amount

        invoice.total_amount = round(total, 2)
        db.session.commit()

        flash(f"Invoice {invoice.invoice_number} generated from {len(eligible_shifts)} shift(s).", "success")
        return redirect(url_for("invoices.detail", invoice_id=invoice.id))

    return render_template("invoices/generate.html", sites=sites, form_data={})


@invoices_bp.route("/preview")
def preview():
    """JSON endpoint: un-invoiced, approved shift hours/total for a site & period."""
    site_id = request.args.get("site_id", type=int)
    period_start = _parse_date(request.args.get("period_start", ""))
    period_end = _parse_date(request.args.get("period_end", ""))

    site = Site.query.get_or_404(site_id) if site_id else None

    if not site or not period_start or not period_end or period_start > period_end:
        return jsonify(hours=0, billing_rate=0, amount=0, shift_count=0, shifts=[])

    eligible_shifts = Shift.query.filter(
        Shift.site_id == site.id,
        Shift.guard_id.isnot(None),
        Shift.status == "completed",
        Shift.approved_by_manager.is_(True),
        Shift.invoice_id.is_(None),
        Shift.shift_date >= period_start,
        Shift.shift_date <= period_end,
    ).order_by(Shift.shift_date.asc(), Shift.start_time.asc()).all()

    hours = round(sum(s.hours for s in eligible_shifts), 2)
    billing_rate = float(site.billing_rate)

    return jsonify(
        hours=hours,
        billing_rate=billing_rate,
        amount=round(hours * billing_rate, 2),
        shift_count=len(eligible_shifts),
        shifts=[
            {
                "id": shift.id,
                "shift_date": shift.shift_date.strftime("%d %b %Y"),
                "start_time": shift.start_time.strftime("%H:%M"),
                "end_time": shift.end_time.strftime("%H:%M"),
                "hours": shift.hours,
                "guard_name": shift.guard.full_name,
                "role": shift.role or "",
                "bill_rate": float(shift.bill_rate),
                "amount": shift.bill_amount,
            }
            for shift in eligible_shifts
        ],
    )


@invoices_bp.route("/<int:invoice_id>")
def detail(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    shifts = sorted(invoice.shifts, key=lambda s: (s.shift_date, s.start_time))
    return render_template("invoices/detail.html", invoice=invoice, shifts=shifts)


@invoices_bp.route("/<int:invoice_id>/print-preview")
def print_preview(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    shifts = sorted(invoice.shifts, key=lambda s: (s.shift_date, s.start_time))
    return render_template("invoices/print_preview.html", invoice=invoice, shifts=shifts)


@invoices_bp.route("/<int:invoice_id>/mark-approved", methods=["POST"])
def mark_approved(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    invoice.status = "approved"
    db.session.commit()
    flash(f"Invoice {invoice.invoice_number} approved.", "success")
    return redirect(url_for("invoices.detail", invoice_id=invoice.id))


@invoices_bp.route("/<int:invoice_id>/mark-sent", methods=["POST"])
def mark_sent(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    invoice.status = "sent"
    db.session.commit()
    flash(f"Invoice {invoice.invoice_number} marked as sent.", "success")
    return redirect(url_for("invoices.detail", invoice_id=invoice.id))


@invoices_bp.route("/<int:invoice_id>/mark-paid", methods=["POST"])
def mark_paid(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    invoice.status = "paid"
    db.session.commit()
    flash(f"Invoice {invoice.invoice_number} marked as paid.", "success")
    return redirect(url_for("invoices.detail", invoice_id=invoice.id))


# ---------------------------------------------------------------------------
# Brand colours (mirror CSS tokens so the PDF matches the web UI)
# ---------------------------------------------------------------------------
_GREEN_DARK = colors.HexColor("#14532D")
_GREEN_SOFT = colors.HexColor("#DCFCE7")
_SLATE = colors.HexColor("#0F172A")
_MUTED = colors.HexColor("#334155")
_BORDER = colors.HexColor("#E2E8F0")
_WHITE = colors.white


def _build_invoice_pdf(invoice):
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    base = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=base["Normal"], fontSize=20, leading=26,
                         textColor=_SLATE, fontName="Helvetica-Bold")
    h2 = ParagraphStyle("h2", parent=base["Normal"], fontSize=11, leading=15,
                         textColor=_GREEN_DARK, fontName="Helvetica-Bold",
                         spaceBefore=10)
    meta = ParagraphStyle("meta", parent=base["Normal"], fontSize=9, leading=13,
                           textColor=_MUTED)
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=10, leading=14,
                           textColor=_SLATE)

    shifts = sorted(invoice.shifts, key=lambda s: (s.shift_date, s.start_time))
    story = []

    # --- Header band ---
    header_data = [[
        Paragraph(invoice.invoice_number, h1),
        Paragraph(
            f"{invoice.site.name}<br/><font color='#{_MUTED.hexval()[2:]}' size=9>"
            f"{invoice.site.client_name}</font>",
            body,
        ),
    ]]
    header_table = Table(header_data, colWidths=["55%", "45%"])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=2, color=_GREEN_DARK))
    story.append(Spacer(1, 5 * mm))

    # --- Meta grid (period / issue date / status) ---
    period = (f"{invoice.period_start.strftime('%d %b %Y')} "
              f"– {invoice.period_end.strftime('%d %b %Y')}")
    meta_data = [
        [Paragraph("Billing period", meta), Paragraph(period, body),
         Paragraph("Issue date", meta),
         Paragraph(invoice.issue_date.strftime("%d %b %Y"), body)],
        [Paragraph("Client", meta), Paragraph(invoice.site.client_name, body),
         Paragraph("Status", meta), Paragraph(invoice.status.capitalize(), body)],
        [Paragraph("Site", meta), Paragraph(invoice.site.name, body), "", ""],
    ]
    meta_table = Table(meta_data, colWidths=["18%", "32%", "18%", "32%"])
    meta_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 6 * mm))

    # --- Line items table ---
    story.append(Paragraph("Shift line items", h2))
    story.append(Spacer(1, 3 * mm))

    col_headers = ["Date", "Guard", "Role", "Start", "Finish", "Hours", "Rate (£/hr)", "Amount"]
    rows = [col_headers]
    for s in shifts:
        rows.append([
            s.shift_date.strftime("%d %b %Y"),
            s.guard.full_name,
            s.role or "—",
            s.start_time.strftime("%H:%M"),
            s.end_time.strftime("%H:%M"),
            f"{s.hours:.2f}",
            f"£{float(s.bill_rate):.2f}",
            f"£{s.bill_amount:.2f}",
        ])
    # Totals footer
    total_hours = sum(s.hours for s in shifts)
    rows.append(["", "", "", "", "", f"{total_hours:.2f}", "Total",
                 f"£{float(invoice.total_amount):.2f}"])

    col_w = [25 * mm, 32 * mm, 22 * mm, 14 * mm, 14 * mm, 14 * mm, 21 * mm, 21 * mm]
    items_table = Table(rows, colWidths=col_w, repeatRows=1)
    n = len(rows)
    items_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), _GREEN_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        # Body rows
        ("FONTNAME", (0, 1), (-1, n - 2), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, n - 2), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, n - 2), [_WHITE, _GREEN_SOFT]),
        ("BOTTOMPADDING", (0, 1), (-1, n - 2), 5),
        ("TOPPADDING", (0, 1), (-1, n - 2), 5),
        # Totals row
        ("BACKGROUND", (0, n - 1), (-1, n - 1), _GREEN_SOFT),
        ("FONTNAME", (0, n - 1), (-1, n - 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, n - 1), (-1, n - 1), 9),
        ("TOPPADDING", (0, n - 1), (-1, n - 1), 6),
        ("BOTTOMPADDING", (0, n - 1), (-1, n - 1), 6),
        # Right-align numeric columns
        ("ALIGN", (5, 0), (-1, -1), "RIGHT"),
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.5, _BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 8 * mm))

    # --- Amount due callout ---
    amount_data = [[
        Paragraph("Total amount due", meta),
        Paragraph(f"£{float(invoice.total_amount):.2f}",
                  ParagraphStyle("amt", parent=base["Normal"], fontSize=18,
                                 leading=22, fontName="Helvetica-Bold",
                                 textColor=_GREEN_DARK, alignment=2)),
    ]]
    amount_table = Table(amount_data, colWidths=["60%", "40%"])
    amount_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, -1), _GREEN_SOFT),
        ("ROUNDEDCORNERS", (0, 0), (-1, -1), [6, 6, 6, 6]),
    ]))
    story.append(amount_table)

    doc.build(story)
    buf.seek(0)
    return buf


def _load_mail_config_from_db():
    """Apply stored mail settings to the live app config before sending."""
    rows = Setting.query.filter(
        Setting.key.in_([
            "MAIL_SERVER", "MAIL_PORT", "MAIL_USE_TLS",
            "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_DEFAULT_SENDER",
        ])
    ).all()
    for row in rows:
        if not row.value:
            continue
        if row.key == "MAIL_PORT":
            try:
                current_app.config[row.key] = int(row.value)
            except (ValueError, TypeError):
                pass
        elif row.key == "MAIL_USE_TLS":
            current_app.config[row.key] = str(row.value).lower() in {"1", "true", "yes", "on"}
        else:
            current_app.config[row.key] = row.value


def _invoice_pdf_attachment(invoice):
    pdf_buf = _build_invoice_pdf(invoice)
    pdf_buf.seek(0)
    return pdf_buf, f"INV-{invoice.invoice_number}.pdf"


@invoices_bp.route("/<int:invoice_id>/download")
@invoices_bp.route("/<int:invoice_id>/download/")
def download(invoice_id):
    invoice = db.session.get(Invoice, invoice_id)
    if invoice is None:
        flash("The requested invoice could not be found.", "error")
        return redirect(url_for("invoices.list_invoices"))

    pdf_buf, filename = _invoice_pdf_attachment(invoice)

    return send_file(
        pdf_buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
        conditional=False,
    )


@invoices_bp.route("/<int:invoice_id>/email", methods=["POST"])
def email_invoice(invoice_id):
    invoice = db.session.get(Invoice, invoice_id)
    if invoice is None:
        flash("The requested invoice could not be found.", "error")
        return redirect(url_for("invoices.list_invoices"))

    recipient = request.form.get("recipient") or current_app.config.get("INVOICE_EMAIL_RECIPIENT")
    if not recipient:
        flash("No invoice email recipient configured.", "error")
        return redirect(url_for("invoices.detail", invoice_id=invoice.id))

    pdf_buf, filename = _invoice_pdf_attachment(invoice)
    msg = Message(
        subject=f"Invoice {invoice.invoice_number} from {invoice.site.name}",
        recipients=[recipient],
        body=(
            f"Hello,\n\n"
            f"Please find attached invoice {invoice.invoice_number} for {invoice.site.name}.\n"
            f"Total amount due: £{float(invoice.total_amount):.2f}\n"
        ),
    )
    msg.attach(filename, "application/pdf", pdf_buf.getvalue())
    _load_mail_config_from_db()
    _mail_settings = {
        row.key: row.value
        for row in Setting.query.filter(
            Setting.key.in_(["MAIL_SERVER", "MAIL_PORT", "MAIL_USE_TLS", "MAIL_USERNAME", "MAIL_PASSWORD"])
        ).all()
    }
    if _mail_settings:
        _ms = current_app.extensions["mail"]
        _ms.server = _mail_settings.get("MAIL_SERVER", _ms.server)
        _ms.port = int(_mail_settings.get("MAIL_PORT", _ms.port))
        _ms.use_tls = str(_mail_settings.get("MAIL_USE_TLS", "false")).lower() in {"1", "true", "yes", "on"}
        _ms.username = _mail_settings.get("MAIL_USERNAME", _ms.username)
        _ms.password = _mail_settings.get("MAIL_PASSWORD", _ms.password)
    print(f"Connecting to {current_app.extensions['mail'].server}:{current_app.extensions['mail'].port}")
    mail.send(msg)

    invoice.status = "sent"
    db.session.commit()
    flash(f"Invoice {invoice.invoice_number} emailed to {recipient}.", "success")
    return redirect(url_for("invoices.detail", invoice_id=invoice.id))


# ===========================================================================
# Payment gateway (Stripe / PayPal-style stubs)
# ---------------------------------------------------------------------------
# These endpoints model the shape of a real integration: an authenticated
# route to open a checkout/payment session, and unauthenticated webhook
# receivers that clear invoices when the gateway confirms payment. The actual
# network/SDK calls are stubbed; swap _create_gateway_session() and the
# signature check for the real provider SDK in production.
# ===========================================================================

# Gateway events that mean "money received" -> clear the invoice.
_PAID_EVENT_TYPES = {
    "checkout.session.completed",
    "payment_intent.succeeded",
    "invoice.paid",
    "invoice.payment_succeeded",
    "PAYMENT.CAPTURE.COMPLETED",  # PayPal
}


def _verify_webhook_signature(provider, payload, signature, secret):
    """Verify a webhook signature (HMAC-SHA256 stub).

    With a configured secret we compare an HMAC of the raw body. With no
    secret we are in local/mock mode and accept the call so the flow can be
    exercised without real gateway credentials -- except in production, where
    a missing secret is a misconfiguration and the call is rejected.
    """
    if not secret:
        if current_app.config.get("IS_PRODUCTION"):
            current_app.logger.error("%s webhook secret missing in production; rejecting", provider)
            return False
        current_app.logger.warning("%s webhook signature skipped (mock mode, no secret)", provider)
        return True
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    # Stripe sends "t=...,v1=<sig>"; accept either the raw hex or that form.
    provided = signature.split("v1=")[-1] if "v1=" in signature else signature
    return hmac.compare_digest(expected, provided.strip())


def _create_gateway_session(invoice, provider):
    """Return a mock checkout/payment-session payload for an invoice.

    A real implementation would call e.g. stripe.checkout.Session.create(...)
    or PayPal order creation with secret API keys from the environment and
    return the gateway's hosted checkout URL.
    """
    return {
        "provider": provider,
        "session_id": f"mock_{provider}_{invoice.invoice_number}",
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "amount": float(invoice.total_amount or 0),
        "currency": "gbp",
        "status": "created",
        # In production this is the gateway-hosted checkout URL.
        "checkout_url": url_for("invoices.detail", invoice_id=invoice.id, _external=True),
        "metadata": {"invoice_number": invoice.invoice_number},
    }


def _clear_invoice_from_event(provider, event):
    """Mark the referenced invoice paid when the event signals success."""
    event_type = event.get("type") or event.get("event_type", "")
    if event_type not in _PAID_EVENT_TYPES:
        current_app.logger.info("%s webhook ignored (event=%s)", provider, event_type)
        return {"received": True, "handled": False, "reason": "ignored_event_type"}

    # Stripe nests the object under data.object; PayPal under resource.
    obj = (event.get("data") or {}).get("object") or event.get("resource") or {}
    invoice_number = (obj.get("metadata") or {}).get("invoice_number") or obj.get("invoice_number")
    if not invoice_number:
        current_app.logger.warning("%s webhook missing invoice_number reference", provider)
        return {"received": True, "handled": False, "reason": "no_invoice_reference"}

    invoice = Invoice.query.filter_by(invoice_number=invoice_number).first()
    if invoice is None:
        current_app.logger.warning("%s webhook for unknown invoice %s", provider, invoice_number)
        return {"received": True, "handled": False, "reason": "unknown_invoice"}

    if invoice.status != "paid":
        invoice.status = "paid"
        db.session.commit()
        current_app.logger.info("Invoice %s cleared (paid) via %s webhook", invoice_number, provider)
    return {"received": True, "handled": True, "invoice_number": invoice_number, "status": invoice.status}


@invoices_bp.route("/<int:invoice_id>/pay", methods=["POST"])
def create_payment_session(invoice_id):
    """Open a checkout/payment session for an invoice (gateway stub)."""
    invoice = db.session.get(Invoice, invoice_id)
    if invoice is None:
        abort(404)
    provider = (request.form.get("provider") or request.args.get("provider") or "stripe").lower()
    if provider not in {"stripe", "paypal"}:
        abort(400, "Unsupported payment provider")
    return jsonify(_create_gateway_session(invoice, provider))


@invoices_bp.route("/webhooks/stripe", methods=["POST"])
@csrf.exempt
def stripe_webhook():
    payload = request.get_data()
    signature = request.headers.get("Stripe-Signature", "")
    secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
    if not _verify_webhook_signature("stripe", payload, signature, secret):
        abort(400, "Invalid signature")
    event = request.get_json(silent=True) or {}
    return jsonify(_clear_invoice_from_event("stripe", event))


@invoices_bp.route("/webhooks/paypal", methods=["POST"])
@csrf.exempt
def paypal_webhook():
    payload = request.get_data()
    signature = request.headers.get("Paypal-Transmission-Sig", "")
    secret = current_app.config.get("PAYPAL_WEBHOOK_SECRET")
    if not _verify_webhook_signature("paypal", payload, signature, secret):
        abort(400, "Invalid signature")
    event = request.get_json(silent=True) or {}
    return jsonify(_clear_invoice_from_event("paypal", event))
