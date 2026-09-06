"""Generator for 3 Mediocre / Moderate Risk Loan Underwriting Scenarios.

Produces scores strictly between 60.0 and 80.0 (MED CRITICALITY):
1. test5_salaried_moderate_dti: Salaried, CIBIL 710, 1 historical missed payment, moderate DTI 42.4% -> Target Score ~70
2. test6_salaried_fair_credit_high_cc: Salaried, CIBIL 670, 0 missed, high CC utilization 68% -> Target Score ~74
3. test7_business_moderate_margin: Business Proprietor, CIBIL 695, 3.5 yr vintage, moderate cashflow -> Target Score ~77

Features:
- Fantastical / Unrealistic Bank Names:
  * Mystic River International Bank
  * Valhalla Alpine Commercial Bank
  * Cybertron Sovereign NeoBank
- Full 6-Month Itemized Transactions (January 2026 to June 2026)
"""

import os
import json
import fitz  # PyMuPDF


def create_pdf(filepath: str, title: str, sections: list):
    """Create a styled PDF document with title, metadata headers, and formatted tables/sections."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    margin_left = 40
    margin_top = 40
    y = margin_top

    # Header Banner
    page.draw_rect(fitz.Rect(margin_left, y, 555, y + 36), color=(0.18, 0.32, 0.48), fill=(0.18, 0.32, 0.48))
    page.insert_text((margin_left + 15, y + 23), title, fontsize=13, color=(1, 1, 1), fontname="helv")
    y += 50

    for sec_heading, sec_lines in sections:
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = margin_top

        # Section Heading
        page.draw_line(fitz.Point(margin_left, y), fitz.Point(555, y), color=(0.7, 0.7, 0.7), width=0.8)
        y += 14
        page.insert_text((margin_left, y), sec_heading, fontsize=11, color=(0.15, 0.3, 0.45), fontname="helv")
        y += 16

        # Section content
        for line in sec_lines:
            if y > 790:
                page = doc.new_page(width=595, height=842)
                y = margin_top

            if isinstance(line, tuple):
                if len(line) == 2:
                    k, v = line
                    page.insert_text((margin_left + 5, y), str(k), fontsize=9, color=(0.25, 0.25, 0.25), fontname="helv")
                    page.insert_text((margin_left + 230, y), str(v), fontsize=9, color=(0.0, 0.0, 0.0), fontname="helv")
                elif len(line) == 5:
                    dt, desc, dr, cr, bal = line
                    is_header = (dt == "Date")
                    fn = "helv"
                    col = (0.1, 0.2, 0.4) if is_header else (0.15, 0.15, 0.15)
                    fs = 8.5
                    page.insert_text((margin_left + 5, y), str(dt), fontsize=fs, color=col, fontname=fn)
                    page.insert_text((margin_left + 75, y), str(desc)[:36], fontsize=fs, color=col, fontname=fn)
                    page.insert_text((margin_left + 280, y), str(dr), fontsize=fs, color=col, fontname=fn)
                    page.insert_text((margin_left + 355, y), str(cr), fontsize=fs, color=col, fontname=fn)
                    page.insert_text((margin_left + 435, y), str(bal), fontsize=fs, color=col, fontname=fn)
            elif isinstance(line, str):
                page.insert_text((margin_left + 5, y), line, fontsize=9, color=(0.2, 0.2, 0.2), fontname="helv")
            y += 14

        y += 10

    # Footer
    page.draw_line(fitz.Point(margin_left, 810), fitz.Point(555, 810), color=(0.8, 0.8, 0.8), width=0.5)
    page.insert_text((margin_left, 822), "AUTHENTICATED FINANCIAL AUDIT RECORD — UNREALISTIC SYNTHETIC TEST SUITE", fontsize=7.5, color=(0.5, 0.5, 0.5), fontname="helv")

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    doc.save(filepath)
    doc.close()
    print(f"  📄 Generated PDF: {filepath}")


def sum_transactions(tx_rows):
    """Calculate total credits, debits, salary credits avg, EMI debits avg, and spends."""
    total_credits = 0.0
    total_debits = 0.0
    salary_amounts = []
    emi_amounts = []
    spend_amounts = []

    for row in tx_rows:
        if row[0] == "Date":
            continue
        dt, desc, dr_str, cr_str = row[0], row[1], row[2], row[3]
        desc_lower = desc.lower()

        if cr_str != "-":
            try:
                amt = float(cr_str.replace(",", ""))
                total_credits += amt
                if any(k in desc_lower for k in ["salary", "payroll", "sal credit"]):
                    salary_amounts.append(amt)
            except ValueError:
                pass

        if dr_str != "-":
            try:
                amt = float(dr_str.replace(",", ""))
                total_debits += amt
                if any(k in desc_lower for k in ["emi", "loan debit", "nach", "auto-debit"]):
                    emi_amounts.append(amt)
                spend_amounts.append(amt)
            except ValueError:
                pass

    avg_salary = round(sum(salary_amounts) / len(salary_amounts), 2) if salary_amounts else None
    avg_emi = round(sum(emi_amounts) / len(emi_amounts), 2) if emi_amounts else None

    return {
        "total_credits": round(total_credits, 2),
        "total_debits": round(total_debits, 2),
        "avg_salary": avg_salary,
        "avg_emi": avg_emi,
        "total_spends": round(sum(spend_amounts), 2),
    }


def generate_scenario_5(base_dir: str):
    """Scenario 5: Salaried Moderate DTI (Target Score ~70, MED Criticality)."""
    s5_dir = os.path.join(base_dir, "test5_salaried_moderate_dti")
    print("\n🔨 Generating Scenario 5: Salaried Moderate DTI (Mystic River International Bank)...")

    # 1. Application Form
    create_pdf(
        os.path.join(s5_dir, "loan_application.pdf"),
        "PERSONAL LOAN APPLICATION FORM",
        [
            ("APPLICANT IDENTIFICATION", [
                ("Application Reference", "APP_S5_MODERATE_SALARIED"),
                ("Full Name", "Vikram Malhotra"),
                ("Date of Birth", "1992-11-04 (Age: 33)"),
                ("Employment Category", "Permanent Salaried"),
                ("Employer Organization", "TechNova Solutions Pvt Ltd"),
                ("Employment Tenure", "2.5 years (Joined 2024-01-10)"),
                ("Designation", "Senior Marketing Specialist"),
            ]),
            ("FACILITY REQUESTED", [
                ("Requested Loan Amount", "₹3,00,000 (INR)"),
                ("Loan Tenure", "24 months"),
                ("Loan Product", "Personal Loan"),
                ("Stated Purpose", "Vehicle Upgrade & Family Expense"),
            ]),
            ("DOCUMENTATION ATTACHED", [
                ("Identity Document (KYC)", "Aadhaar & PAN Verified (Yes)"),
                ("Salary Slip Attached", "Yes (June 2026 attached)"),
                ("Bank Statement Attached", "Yes (Mystic River International Bank 6-Month attached)"),
                ("Form 16 Tax Certificate", "Yes (AY 2026-27 attached)"),
                ("Credit Card Statement", "Yes (Mystic River Platinum Rewards Card attached)"),
            ]),
        ],
    )

    # 2. Salary Slip
    create_pdf(
        os.path.join(s5_dir, "salary_slip.pdf"),
        "EMPLOYEE SALARY SLIP — JUNE 2026",
        [
            ("EMPLOYER DETAILS", [
                ("Company Name", "TechNova Solutions Pvt Ltd"),
                ("Corporate ID (CIN)", "U74999MH2019PTC324150"),
                ("Employee Name", "Vikram Malhotra"),
                ("Employee Code", "TN-5521"),
                ("Pay Period", "01-Jun-2026 to 30-Jun-2026"),
            ]),
            ("EARNINGS BREAKDOWN", [
                ("Basic Pay", "₹38,000.00"),
                ("House Rent Allowance (HRA)", "₹19,000.00"),
                ("Special Allowance", "₹11,000.00"),
                ("Performance Bonus", "₹4,000.00"),
                ("Monthly Gross Income", "₹72,000.00"),
            ]),
            ("DEDUCTIONS", [
                ("Provident Fund (PF)", "₹4,560.00"),
                ("Professional Tax", "₹200.00"),
                ("Tax Deducted at Source (TDS)", "₹2,240.00"),
                ("Total Deductions", "₹7,000.00"),
            ]),
            ("NET DISBURSEMENT", [
                ("Monthly Net Income", "₹65,000.00"),
                ("Payment Mode", "Direct NEFT to Mystic River International Bank"),
            ]),
        ],
    )

    # 3. Form 16 Tax Certificate
    create_pdf(
        os.path.join(s5_dir, "form16_tax.pdf"),
        "FORM NO. 16 — CERTIFICATE OF TAX DEDUCTION AT SOURCE",
        [
            ("EMPLOYER & EMPLOYEE DETAILS", [
                ("Employer Name", "TechNova Solutions Pvt Ltd"),
                ("Employer TAN", "MUMB12345C"),
                ("Employee Name", "Vikram Malhotra"),
                ("Employee PAN", "BMRPM4120L"),
                ("Assessment Year", "2026-27 (Financial Year 2025-26)"),
            ]),
            ("SALARY & TAX SUMMARY", [
                ("Annual Gross Salary (Sec 17(1))", "₹8,64,000.00"),
                ("Standard Deduction (Sec 16(ia))", "₹50,000.00"),
                ("Net Taxable Income", "₹8,14,000.00"),
                ("Total TDS Deducted & Deposited", "₹26,880.00"),
            ]),
        ],
    )

    # 4. Bank Statement (6 Months, Jan-Jun 2026)
    bank_txs_s5 = [
        ("Date", "Description", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        ("01-Jan-2026", "SALARY CREDIT - TECHNOVA SOLUTIONS", "-", "65,000.00", "82,500.00"),
        ("05-Jan-2026", "NACH AUTO-DEBIT - CAR LOAN EMI", "16,000.00", "-", "66,500.00"),
        ("14-Jan-2026", "UPI/Swiggy-Instamart Groceries", "3,400.00", "-", "63,100.00"),
        ("01-Feb-2026", "SALARY CREDIT - TECHNOVA SOLUTIONS", "-", "65,000.00", "1,28,100.00"),
        ("05-Feb-2026", "NACH AUTO-DEBIT - CAR LOAN EMI", "16,000.00", "-", "1,12,100.00"),
        ("18-Feb-2026", "Utility Bill Electricity & Gas", "4,200.00", "-", "1,07,900.00"),
        ("01-Mar-2026", "SALARY CREDIT - TECHNOVA SOLUTIONS", "-", "65,000.00", "1,72,900.00"),
        ("05-Mar-2026", "NACH AUTO-DEBIT - CAR LOAN EMI", "16,000.00", "-", "1,56,900.00"),
        ("20-Mar-2026", "Quarterly Insurance Premium", "8,500.00", "-", "1,48,400.00"),
        ("01-Apr-2026", "SALARY CREDIT - TECHNOVA SOLUTIONS", "-", "65,000.00", "2,13,400.00"),
        ("05-Apr-2026", "NACH AUTO-DEBIT - CAR LOAN EMI", "16,000.00", "-", "1,97,400.00"),
        ("12-Apr-2026", "Credit Card Bill Auto Payment", "15,200.00", "-", "1,82,200.00"),
        ("01-May-2026", "SALARY CREDIT - TECHNOVA SOLUTIONS", "-", "65,000.00", "2,47,200.00"),
        ("05-May-2026", "NACH AUTO-DEBIT - CAR LOAN EMI", "16,000.00", "-", "2,31,200.00"),
        ("22-May-2026", "Family Weekend Dining & Outing", "6,800.00", "-", "2,24,400.00"),
        ("01-Jun-2026", "SALARY CREDIT - TECHNOVA SOLUTIONS", "-", "65,000.00", "2,89,400.00"),
        ("05-Jun-2026", "NACH AUTO-DEBIT - CAR LOAN EMI", "16,000.00", "-", "2,73,400.00"),
        ("26-Jun-2026", "Annual Vehicle Maintenance", "9,400.00", "-", "2,64,000.00"),
    ]
    bank_s5_metrics = sum_transactions(bank_txs_s5)

    create_pdf(
        os.path.join(s5_dir, "bank_statement.pdf"),
        "MYSTIC RIVER INTERNATIONAL BANK — ACCOUNT STATEMENT",
        [
            ("ACCOUNT PROFILE", [
                ("Bank Name", "Mystic River International Bank"),
                ("Account Holder", "Vikram Malhotra"),
                ("Account Number", "MRIB-SAV-8839021"),
                ("Account Type", "Resident Salary Savings"),
                ("Statement Period", "01-Jan-2026 to 30-Jun-2026 (6 Months)"),
            ]),
            ("TRANSACTION HISTORY", bank_txs_s5),
        ],
    )

    # 5. Credit Bureau Report (Score 710, 1 missed payment, 0 overdue)
    create_pdf(
        os.path.join(s5_dir, "credit_report.pdf"),
        "CIBIL CREDIT INFORMATION REPORT (CIR)",
        [
            ("CONSUMER IDENTIFICATION", [
                ("Consumer Name", "Vikram Malhotra"),
                ("PAN", "BMRPM4120L"),
                ("Date of Report", "30-Jun-2026"),
                ("Credit Bureau Score", "710 (Fair / Moderate Grade)"),
                ("Scoring Model", "CIBIL TransUnion v3.0"),
            ]),
            ("CREDIT ACCOUNT SUMMARY", [
                ("Total Credit Accounts", "3"),
                ("Active Loan Accounts", "1 (Auto Loan)"),
                ("Existing Monthly EMI", "₹16,000.00"),
                ("Total Outstanding Debt", "₹4,50,000.00"),
                ("Active Overdue Amount", "₹0.00"),
                ("Missed Payments (Past 24 Months)", "1 (30 Days Past Due in Feb 2025)"),
                ("Repayment Track Record", "Standard with 1 isolated delay"),
            ]),
        ],
    )

    # 6. Credit Card Statement (Limit 1,50,000, Balance 48,000, Util 32%)
    cc_txs_s5 = [
        ("Date", "Description", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        ("08-Jan-2026", "Fuel Station HPCL", "4,200.00", "-", "4,200.00"),
        ("18-Jan-2026", "Amazon India Electronics", "8,500.00", "-", "12,700.00"),
        ("04-Feb-2026", "Payment Received - Thank You", "-", "12,700.00", "0.00"),
        ("15-Feb-2026", "Flight Booking Indigo", "12,400.00", "-", "12,400.00"),
        ("03-Mar-2026", "Payment Received - Thank You", "-", "12,400.00", "0.00"),
        ("19-Mar-2026", "Apparel & Retail Lifestyle", "7,800.00", "-", "7,800.00"),
        ("06-Apr-2026", "Payment Received - Thank You", "-", "7,800.00", "0.00"),
        ("24-Apr-2026", "Smartphone Purchase Croma", "24,000.00", "-", "24,000.00"),
        ("05-May-2026", "Payment Received - Thank You", "-", "15,000.00", "9,000.00"),
        ("18-May-2026", "Supermarket & Home Supplies", "14,000.00", "-", "23,000.00"),
        ("06-Jun-2026", "Travel Booking MakeMyTrip", "25,000.00", "-", "48,000.00"),
    ]
    cc_s5_metrics = sum_transactions(cc_txs_s5)

    create_pdf(
        os.path.join(s5_dir, "credit_card_statement.pdf"),
        "MYSTIC RIVER PLATINUM REWARDS CARD STATEMENT",
        [
            ("CARD PROFILE", [
                ("Bank Name", "Mystic River International Bank"),
                ("Cardholder", "Vikram Malhotra"),
                ("Sanctioned Limit", "₹1,50,000.00"),
                ("Total Balance Due", "₹48,000.00"),
                ("Card Utilization", "32.0% (Moderate)"),
            ]),
            ("TRANSACTION HISTORY", cc_txs_s5),
        ],
    )

    with open(os.path.join(s5_dir, "ground_truth.json"), "w") as f:
        json.dump({
            "application_id": "APP_S5_MODERATE_SALARIED",
            "applicant_name": "Vikram Malhotra",
            "applicant_type": "salaried",
            "employment_duration_years": 2.5,
            "monthly_gross_income": 72000.0,
            "monthly_net_income": 65000.0,
            "annual_income": 864000.0,
            "existing_monthly_emi": 16000.0,
            "outstanding_debt": 450000.0,
            "overdue_amount": 0.0,
            "missed_payments": 1,
            "requested_loan_amount": 300000.0,
            "credit_score": 710,
            "credit_card_limit": 150000.0,
            "credit_card_total_balance": 48000.0,
            "credit_utilization_ratio": 0.32,
            "total_bank_credits_6m": bank_s5_metrics["total_credits"],
            "total_bank_debits_6m": bank_s5_metrics["total_debits"],
            "derived_monthly_salary_from_bank": bank_s5_metrics["avg_salary"],
            "derived_monthly_emi_from_bank": bank_s5_metrics["avg_emi"],
            "total_credit_card_spends_6m": cc_s5_metrics["total_spends"],
            "identity_verified": True,
            "income_document_available": True,
            "bank_statement_available": True,
            "tax_document_available": True,
            "loan_statement_available": True,
            "credit_card_statement_available": True,
            "expected_eligibility": "ELIGIBLE",
        }, f, indent=2)


def generate_scenario_6(base_dir: str):
    """Scenario 6: Salaried Fair Credit & High CC Utilization (Target Score ~74, MED Criticality)."""
    s6_dir = os.path.join(base_dir, "test6_salaried_fair_credit_high_cc")
    print("\n🔨 Generating Scenario 6: Salaried Fair Credit High CC (Valhalla Alpine Commercial Bank)...")

    # 1. Application Form
    create_pdf(
        os.path.join(s6_dir, "loan_application.pdf"),
        "PERSONAL LOAN APPLICATION FORM",
        [
            ("APPLICANT IDENTIFICATION", [
                ("Application Reference", "APP_S6_FAIR_SALARIED"),
                ("Full Name", "Priya Nambiar"),
                ("Date of Birth", "1996-03-22 (Age: 30)"),
                ("Employment Category", "Permanent Salaried"),
                ("Employer Organization", "Apex Global Logistics Ltd"),
                ("Employment Tenure", "1.5 years (Joined 2025-01-15)"),
                ("Designation", "Operations Supply Planner"),
            ]),
            ("FACILITY REQUESTED", [
                ("Requested Loan Amount", "₹2,50,000 (INR)"),
                ("Loan Tenure", "24 months"),
                ("Loan Product", "Personal Loan"),
                ("Stated Purpose", "Professional Certification & Relocation"),
            ]),
            ("DOCUMENTATION ATTACHED", [
                ("Identity Document (KYC)", "Aadhaar & PAN Verified (Yes)"),
                ("Salary Slip Attached", "Yes (June 2026 attached)"),
                ("Bank Statement Attached", "Yes (Valhalla Alpine Commercial Bank 6-Month attached)"),
                ("Form 16 Tax Certificate", "Yes (AY 2026-27 attached)"),
                ("Credit Card Statement", "Yes (Valhalla Titanium Advantage Card attached)"),
            ]),
        ],
    )

    # 2. Salary Slip
    create_pdf(
        os.path.join(s6_dir, "salary_slip.pdf"),
        "EMPLOYEE SALARY SLIP — JUNE 2026",
        [
            ("EMPLOYER DETAILS", [
                ("Company Name", "Apex Global Logistics Ltd"),
                ("Corporate ID (CIN)", "U63090KA2020PTC138800"),
                ("Employee Name", "Priya Nambiar"),
                ("Employee Code", "AGL-3041"),
                ("Pay Period", "01-Jun-2026 to 30-Jun-2026"),
            ]),
            ("EARNINGS BREAKDOWN", [
                ("Basic Pay", "₹32,000.00"),
                ("House Rent Allowance (HRA)", "₹16,000.00"),
                ("Transport Allowance", "₹8,000.00"),
                ("Special Allowance", "₹6,000.00"),
                ("Monthly Gross Income", "₹62,000.00"),
            ]),
            ("DEDUCTIONS", [
                ("Provident Fund (PF)", "₹3,840.00"),
                ("Professional Tax", "₹200.00"),
                ("Tax Deducted at Source (TDS)", "₹2,960.00"),
                ("Total Deductions", "₹7,000.00"),
            ]),
            ("NET DISBURSEMENT", [
                ("Monthly Net Income", "₹55,000.00"),
                ("Payment Mode", "Direct NEFT to Valhalla Alpine Commercial Bank"),
            ]),
        ],
    )

    # 3. Form 16 Tax Certificate
    create_pdf(
        os.path.join(s6_dir, "form16_tax.pdf"),
        "FORM NO. 16 — CERTIFICATE OF TAX DEDUCTION AT SOURCE",
        [
            ("EMPLOYER & EMPLOYEE DETAILS", [
                ("Employer Name", "Apex Global Logistics Ltd"),
                ("Employer TAN", "BLRA99887D"),
                ("Employee Name", "Priya Nambiar"),
                ("Employee PAN", "CNVPN7811M"),
                ("Assessment Year", "2026-27 (Financial Year 2025-26)"),
            ]),
            ("SALARY & TAX SUMMARY", [
                ("Annual Gross Salary (Sec 17(1))", "₹7,44,000.00"),
                ("Standard Deduction (Sec 16(ia))", "₹50,000.00"),
                ("Net Taxable Income", "₹6,94,000.00"),
                ("Total TDS Deducted & Deposited", "₹35,520.00"),
            ]),
        ],
    )

    # 4. Bank Statement (6 Months, Jan-Jun 2026)
    bank_txs_s6 = [
        ("Date", "Description", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        ("01-Jan-2026", "SALARY CREDIT - APEX LOGISTICS", "-", "55,000.00", "64,200.00"),
        ("05-Jan-2026", "NACH AUTO-DEBIT - TWO WHEELER LOAN", "8,000.00", "-", "56,200.00"),
        ("12-Jan-2026", "UPI/BigBasket Daily Supplies", "2,800.00", "-", "53,400.00"),
        ("01-Feb-2026", "SALARY CREDIT - APEX LOGISTICS", "-", "55,000.00", "1,08,400.00"),
        ("05-Feb-2026", "NACH AUTO-DEBIT - TWO WHEELER LOAN", "8,000.00", "-", "1,00,400.00"),
        ("14-Feb-2026", "Broadband & Mobile Recharge", "1,500.00", "-", "98,900.00"),
        ("01-Mar-2026", "SALARY CREDIT - APEX LOGISTICS", "-", "55,000.00", "1,53,900.00"),
        ("05-Mar-2026", "NACH AUTO-DEBIT - TWO WHEELER LOAN", "8,000.00", "-", "1,45,900.00"),
        ("16-Mar-2026", "Credit Card Minimum Due Payment", "10,000.00", "-", "1,35,900.00"),
        ("01-Apr-2026", "SALARY CREDIT - APEX LOGISTICS", "-", "55,000.00", "1,90,900.00"),
        ("05-Apr-2026", "NACH AUTO-DEBIT - TWO WHEELER LOAN", "8,000.00", "-", "1,82,900.00"),
        ("19-Apr-2026", "Medical Health Checkup Labs", "4,200.00", "-", "1,78,700.00"),
        ("01-May-2026", "SALARY CREDIT - APEX LOGISTICS", "-", "55,000.00", "2,33,700.00"),
        ("05-May-2026", "NACH AUTO-DEBIT - TWO WHEELER LOAN", "8,000.00", "-", "2,25,700.00"),
        ("21-May-2026", "Credit Card Payment", "12,000.00", "-", "2,13,700.00"),
        ("01-Jun-2026", "SALARY CREDIT - APEX LOGISTICS", "-", "55,000.00", "2,68,700.00"),
        ("05-Jun-2026", "NACH AUTO-DEBIT - TWO WHEELER LOAN", "8,000.00", "-", "2,60,700.00"),
        ("20-Jun-2026", "Weekend Apparel Shopping", "5,500.00", "-", "2,55,200.00"),
    ]
    bank_s6_metrics = sum_transactions(bank_txs_s6)

    create_pdf(
        os.path.join(s6_dir, "bank_statement.pdf"),
        "VALHALLA ALPINE COMMERCIAL BANK — STATEMENT OF ACCOUNT",
        [
            ("ACCOUNT PROFILE", [
                ("Bank Name", "Valhalla Alpine Commercial Bank"),
                ("Account Holder", "Priya Nambiar"),
                ("Account Number", "VAL-SAL-4100982"),
                ("Account Type", "Resident Salary Savings"),
                ("Statement Period", "01-Jan-2026 to 30-Jun-2026 (6 Months)"),
            ]),
            ("TRANSACTION HISTORY", bank_txs_s6),
        ],
    )

    # 5. Credit Bureau Report (Score 670, 0 missed, 0 overdue, revolving card debt)
    create_pdf(
        os.path.join(s6_dir, "credit_report.pdf"),
        "CIBIL CREDIT INFORMATION REPORT (CIR)",
        [
            ("CONSUMER IDENTIFICATION", [
                ("Consumer Name", "Priya Nambiar"),
                ("PAN", "CNVPN7811M"),
                ("Date of Report", "30-Jun-2026"),
                ("Credit Bureau Score", "670 (Fair / Moderate Grade)"),
                ("Scoring Model", "CIBIL TransUnion v3.0"),
            ]),
            ("CREDIT ACCOUNT SUMMARY", [
                ("Total Credit Accounts", "2"),
                ("Active Loan Accounts", "1 (Two-Wheeler Loan)"),
                ("Existing Monthly EMI", "₹8,000.00"),
                ("Total Outstanding Debt", "₹1,80,000.00"),
                ("Active Overdue Amount", "₹0.00"),
                ("Missed Payments (Past 24 Months)", "0"),
                ("Repayment Track Record", "Clean repayment, modest credit depth"),
            ]),
        ],
    )

    # 6. Credit Card Statement (Limit 1,00,000, Balance 68,000, Util 68%)
    cc_txs_s6 = [
        ("Date", "Description", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        ("04-Jan-2026", "Amazon Electronic Gadgets", "18,000.00", "-", "18,000.00"),
        ("15-Jan-2026", "Urban Ladder Furniture Item", "14,500.00", "-", "32,500.00"),
        ("02-Feb-2026", "Payment Received - Thank You", "-", "10,000.00", "22,500.00"),
        ("18-Feb-2026", "Flight Tickets Vacation", "16,000.00", "-", "38,500.00"),
        ("03-Mar-2026", "Payment Received - Thank You", "-", "10,000.00", "28,500.00"),
        ("22-Mar-2026", "Apparel & Accessories", "12,000.00", "-", "40,500.00"),
        ("05-Apr-2026", "Payment Received - Thank You", "-", "8,000.00", "32,500.00"),
        ("20-Apr-2026", "Home Appliances Croma", "22,000.00", "-", "54,500.00"),
        ("04-May-2026", "Payment Received - Thank You", "-", "12,000.00", "42,500.00"),
        ("19-May-2026", "Laptop Repair & Accessories", "11,500.00", "-", "54,000.00"),
        ("12-Jun-2026", "Lifestyle & Grocery Spends", "14,000.00", "-", "68,000.00"),
    ]
    cc_s6_metrics = sum_transactions(cc_txs_s6)

    create_pdf(
        os.path.join(s6_dir, "credit_card_statement.pdf"),
        "VALHALLA TITANIUM ADVANTAGE CARD STATEMENT",
        [
            ("CARD PROFILE", [
                ("Bank Name", "Valhalla Alpine Commercial Bank"),
                ("Cardholder", "Priya Nambiar"),
                ("Sanctioned Limit", "₹1,00,000.00"),
                ("Total Balance Due", "₹68,000.00"),
                ("Card Utilization", "68.0% (High Revolving)"),
            ]),
            ("TRANSACTION HISTORY", cc_txs_s6),
        ],
    )

    with open(os.path.join(s6_dir, "ground_truth.json"), "w") as f:
        json.dump({
            "application_id": "APP_S6_FAIR_SALARIED",
            "applicant_name": "Priya Nambiar",
            "applicant_type": "salaried",
            "employment_duration_years": 1.5,
            "monthly_gross_income": 62000.0,
            "monthly_net_income": 55000.0,
            "annual_income": 744000.0,
            "existing_monthly_emi": 8000.0,
            "outstanding_debt": 180000.0,
            "overdue_amount": 0.0,
            "missed_payments": 0,
            "requested_loan_amount": 250000.0,
            "credit_score": 670,
            "credit_card_limit": 100000.0,
            "credit_card_total_balance": 68000.0,
            "credit_utilization_ratio": 0.68,
            "total_bank_credits_6m": bank_s6_metrics["total_credits"],
            "total_bank_debits_6m": bank_s6_metrics["total_debits"],
            "derived_monthly_salary_from_bank": bank_s6_metrics["avg_salary"],
            "derived_monthly_emi_from_bank": bank_s6_metrics["avg_emi"],
            "total_credit_card_spends_6m": cc_s6_metrics["total_spends"],
            "identity_verified": True,
            "income_document_available": True,
            "bank_statement_available": True,
            "tax_document_available": True,
            "loan_statement_available": True,
            "credit_card_statement_available": True,
            "expected_eligibility": "ELIGIBLE",
        }, f, indent=2)


def generate_scenario_7(base_dir: str):
    """Scenario 7: Business Proprietor with Moderate Margin (Target Score ~77, MED Criticality)."""
    s7_dir = os.path.join(base_dir, "test7_business_moderate_margin")
    print("\n🔨 Generating Scenario 7: Business Moderate Margin (Cybertron Sovereign NeoBank)...")

    # 1. Application Form
    create_pdf(
        os.path.join(s7_dir, "loan_application.pdf"),
        "BUSINESS / PROFESSIONAL LOAN APPLICATION FORM",
        [
            ("APPLICANT IDENTIFICATION", [
                ("Application Reference", "APP_S7_MODERATE_BUSINESS"),
                ("Full Name", "Amitav Sen"),
                ("Date of Birth", "1988-06-15 (Age: 38)"),
                ("Employment Category", "Self Employed / Business"),
                ("Business / Enterprise Name", "Sen Craft Furnishings"),
                ("Business Vintage", "3.2 years (Established 2023-04-01)"),
                ("Designation", "Sole Proprietor"),
            ]),
            ("FACILITY REQUESTED", [
                ("Requested Loan Amount", "₹4,50,000 (INR)"),
                ("Loan Tenure", "36 months"),
                ("Loan Product", "Personal Loan"),
                ("Stated Purpose", "Showroom Expansion & Inventory Stocking"),
            ]),
            ("DOCUMENTATION ATTACHED", [
                ("Identity Document (KYC)", "Aadhaar & PAN Verified (Yes)"),
                ("Business Registration / GST", "Yes (GST Registration Certificate attached)"),
                ("Bank Statement Attached", "Yes (Cybertron Sovereign NeoBank Current A/c attached)"),
                ("ITR / Financial Statement", "Yes (AY 2026-27 ITR-4 attached)"),
                ("Credit Card Statement", "Yes (Cybertron Commercial Business Card attached)"),
            ]),
        ],
    )


    # 2. Income & Financial Statement / Tax Return
    create_pdf(
        os.path.join(s7_dir, "tax_financial_statement.pdf"),
        "ITR-4 SUGAM & STATEMENT OF BUSINESS INCOME — AY 2026-27",
        [
            ("ENTERPRISE PROFILE", [
                ("Business Name", "Sen Craft Furnishings"),
                ("Proprietor Name", "Amitav Sen"),
                ("PAN", "AMTPS9912K"),
                ("GSTIN", "19AMTPS9912K1Z4"),
                ("Nature of Business", "Manufacturing & Retail of Wooden Furniture"),
            ]),
            ("REVENUE & INCOME SUMMARY", [
                ("Annual Turnover / Gross Revenue", "₹36,00,000.00"),
                ("Presumptive Net Business Income (Sec 44AD)", "₹9,00,000.00"),
                ("Monthly Net Income", "₹75,000.00"),
                ("Monthly Gross Income", "₹85,000.00"),
                ("Income Tax Deposited", "₹42,500.00"),
            ]),
        ],
    )

    # 3. Bank Statement (6 Months Current Account, Jan-Jun 2026)
    bank_txs_s7 = [
        ("Date", "Description", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        ("04-Jan-2026", "Customer Order Payment NEFT", "-", "95,000.00", "1,45,000.00"),
        ("08-Jan-2026", "NACH AUTO-DEBIT - BUSINESS TERM LOAN", "18,000.00", "-", "1,27,000.00"),
        ("15-Jan-2026", "Timber Supplier Raw Material", "42,000.00", "-", "85,000.00"),
        ("03-Feb-2026", "Retail Showroom Sales Inflow", "-", "88,000.00", "1,73,000.00"),
        ("08-Feb-2026", "NACH AUTO-DEBIT - BUSINESS TERM LOAN", "18,000.00", "-", "1,55,000.00"),
        ("20-Feb-2026", "Store Rent & Commercial Electric", "28,000.00", "-", "1,27,000.00"),
        ("05-Mar-2026", "Wholesale Interior Project Contract", "-", "1,10,000.00", "2,37,000.00"),
        ("08-Mar-2026", "NACH AUTO-DEBIT - BUSINESS TERM LOAN", "18,000.00", "-", "2,19,000.00"),
        ("22-Mar-2026", "Hardware & Polish Supplies", "35,000.00", "-", "1,84,000.00"),
        ("06-Apr-2026", "Customer Order Payment UPI/NEFT", "-", "78,000.00", "2,62,000.00"),
        ("08-Apr-2026", "NACH AUTO-DEBIT - BUSINESS TERM LOAN", "18,000.00", "-", "2,44,000.00"),
        ("18-Apr-2026", "Commercial Delivery Logistics", "12,000.00", "-", "2,32,000.00"),
        ("04-May-2026", "Client Advance Custom Modular Kitchen", "-", "92,000.00", "3,24,000.00"),
        ("08-May-2026", "NACH AUTO-DEBIT - BUSINESS TERM LOAN", "18,000.00", "-", "3,06,000.00"),
        ("25-May-2026", "Workshop Labor & Wages", "38,000.00", "-", "2,68,000.00"),
        ("05-Jun-2026", "Showroom Walk-in Furniture Sales", "-", "84,000.00", "3,52,000.00"),
        ("08-Jun-2026", "NACH AUTO-DEBIT - BUSINESS TERM LOAN", "18,000.00", "-", "3,34,000.00"),
        ("24-Jun-2026", "Inventory Replenishment Fittings", "26,000.00", "-", "3,08,000.00"),
    ]
    bank_s7_metrics = sum_transactions(bank_txs_s7)

    create_pdf(
        os.path.join(s7_dir, "bank_statement.pdf"),
        "CYBERTRON SOVEREIGN NEOBANK — CURRENT ACCOUNT STATEMENT",
        [
            ("ACCOUNT PROFILE", [
                ("Bank Name", "Cybertron Sovereign NeoBank"),
                ("Account Name", "Sen Craft Furnishings - Prop. Amitav Sen"),
                ("Account Number", "CSNB-CA-9921003"),
                ("Account Type", "Commercial Business Current Account"),
                ("Statement Period", "01-Jan-2026 to 30-Jun-2026 (6 Months)"),
            ]),
            ("TRANSACTION HISTORY", bank_txs_s7),
        ],
    )

    # 4. Credit Bureau Report (Score 680, 0 missed, 0 overdue, 1 business loan)
    create_pdf(
        os.path.join(s7_dir, "credit_report.pdf"),
        "CIBIL COMMERCIAL & CONSUMER CREDIT INFORMATION REPORT",
        [
            ("APPLICANT IDENTIFICATION", [
                ("Applicant Name", "Amitav Sen"),
                ("PAN", "AMTPS9912K"),
                ("Date of Report", "30-Jun-2026"),
                ("Credit Bureau Score", "680 (Standard / Moderate Grade)"),
                ("Scoring Model", "CIBIL TransUnion v3.0"),
            ]),
            ("CREDIT ACCOUNT SUMMARY", [
                ("Total Credit Accounts", "2"),
                ("Active Loan Accounts", "1 (Business Equipment Loan)"),
                ("Existing Monthly EMI Obligation", "₹20,000.00"),
                ("Total Outstanding Debt", "₹6,80,000.00"),
                ("Overdue Balance Amount", "₹0.00"),
                ("Missed Payments (Past 24 Months)", "0"),
                ("Repayment Track Record", "Consistent and clean commercial repayment"),
            ]),
        ],
    )


    # 5. Credit Card Statement (Limit 2,00,000, Balance 82,000, Util 41.0%)
    cc_txs_s7 = [
        ("Date", "Description", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        ("06-Jan-2026", "Digital Marketing Ads Google & FB", "18,000.00", "-", "18,000.00"),
        ("20-Jan-2026", "Office Supplies & Paperwork", "8,500.00", "-", "26,500.00"),
        ("05-Feb-2026", "Payment Received - Thank You", "-", "20,000.00", "6,500.00"),
        ("17-Feb-2026", "Industrial Hardware Tools Bosch", "24,000.00", "-", "30,500.00"),
        ("05-Mar-2026", "Payment Received - Thank You", "-", "20,000.00", "10,500.00"),
        ("22-Mar-2026", "Software ERP Subscription Tally", "15,000.00", "-", "25,500.00"),
        ("05-Apr-2026", "Payment Received - Thank You", "-", "15,000.00", "10,500.00"),
        ("19-Apr-2026", "Client Hospitality & Trade Expo", "32,000.00", "-", "42,500.00"),
        ("06-May-2026", "Payment Received - Thank You", "-", "20,000.00", "22,500.00"),
        ("22-May-2026", "Workshop Machinery Spares", "28,500.00", "-", "51,000.00"),
        ("15-Jun-2026", "Commercial Delivery Vehicle Fuel", "31,000.00", "-", "82,000.00"),
    ]
    cc_s7_metrics = sum_transactions(cc_txs_s7)

    create_pdf(
        os.path.join(s7_dir, "credit_card_statement.pdf"),
        "CYBERTRON COMMERCIAL BUSINESS CARD STATEMENT",
        [
            ("CARD PROFILE", [
                ("Bank Name", "Cybertron Sovereign NeoBank"),
                ("Cardholder", "Sen Craft Furnishings / Amitav Sen"),
                ("Sanctioned Limit", "₹2,00,000.00"),
                ("Total Balance Due", "₹82,000.00"),
                ("Card Utilization", "41.0% (Moderate)"),
            ]),
            ("TRANSACTION HISTORY", cc_txs_s7),
        ],
    )

    with open(os.path.join(s7_dir, "ground_truth.json"), "w") as f:
        json.dump({
            "application_id": "APP_S7_MODERATE_BUSINESS",
            "applicant_name": "Amitav Sen",
            "applicant_type": "self_employed",
            "employment_duration_years": 3.2,
            "monthly_gross_income": 85000.0,
            "monthly_net_income": 75000.0,
            "annual_revenue": 3600000.0,
            "annual_income": 900000.0,
            "existing_monthly_emi": 20000.0,
            "outstanding_debt": 680000.0,
            "overdue_amount": 0.0,
            "missed_payments": 0,
            "requested_loan_amount": 450000.0,
            "credit_score": 680,
            "credit_card_limit": 200000.0,
            "credit_card_total_balance": 82000.0,
            "credit_utilization_ratio": 0.41,
            "total_bank_credits_6m": bank_s7_metrics["total_credits"],
            "total_bank_debits_6m": bank_s7_metrics["total_debits"],
            "derived_monthly_emi_from_bank": bank_s7_metrics["avg_emi"],
            "total_credit_card_spends_6m": cc_s7_metrics["total_spends"],
            "identity_verified": True,
            "income_document_available": True,
            "bank_statement_available": True,
            "tax_document_available": True,
            "loan_statement_available": True,
            "credit_card_statement_available": True,
            "expected_eligibility": "ELIGIBLE",
        }, f, indent=2)



def main():
    base_dir = os.path.join(os.path.dirname(__file__), "..", "data", "pdf_scenarios")
    print("🚀 Generating 3 Mediocre / Moderate Risk Profiles (Scores 60 - 80)...")
    generate_scenario_5(base_dir)
    generate_scenario_6(base_dir)
    generate_scenario_7(base_dir)
    print("\n✅ All 3 Mediocre Scenarios successfully generated in data/pdf_scenarios/!")


if __name__ == "__main__":
    main()
