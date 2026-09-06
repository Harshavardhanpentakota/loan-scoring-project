"""Synthetic PDF Document Generator for Loan Underwriting Scenarios.

Features:
- Completely Unrealistic/Fantastical Bank Names:
  * Bank of Wonderland & Mars
  * Atlantis Subsea Crypto Bank
  * Intergalactic Bank of Andromeda
  * Gryffindor Magical Vault Bank
- 6 Full Months of Itemized Transactions (January 2026 to June 2026)
- Bank statements with salary/business receipts, EMIs, and random everyday transactions
- Credit card statements with 6 months of itemized card spends and payments
- Dynamically summed totals written to ground_truth.json for post-extraction evaluation
"""

import os
import json
import fitz  # PyMuPDF


def create_pdf(filepath: str, title: str, sections: list):
    """Create a styled PDF document with title, metadata headers, and formatted tables/sections."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # Standard A4 (points)

    margin_left = 40
    margin_top = 40
    y = margin_top

    # Header Banner
    page.draw_rect(fitz.Rect(margin_left, y, 555, y + 36), color=(0.12, 0.28, 0.55), fill=(0.12, 0.28, 0.55))
    page.insert_text((margin_left + 15, y + 23), title, fontsize=14, color=(1, 1, 1), fontname="helv")
    y += 50

    for sec_heading, sec_lines in sections:
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = margin_top

        # Section Heading
        page.draw_line(fitz.Point(margin_left, y), fitz.Point(555, y), color=(0.7, 0.7, 0.7), width=0.8)
        y += 14
        page.insert_text((margin_left, y), sec_heading, fontsize=11, color=(0.1, 0.25, 0.5), fontname="helv")
        y += 16

        # Section content
        for line in sec_lines:
            if y > 790:
                page = doc.new_page(width=595, height=842)
                y = margin_top

            if isinstance(line, tuple):
                if len(line) == 2:
                    # Two-column key-value display
                    k, v = line
                    page.insert_text((margin_left + 5, y), str(k), fontsize=9, color=(0.25, 0.25, 0.25), fontname="helv")
                    page.insert_text((margin_left + 230, y), str(v), fontsize=9, color=(0.0, 0.0, 0.0), fontname="helv")
                elif len(line) == 5:
                    # 5-Column Transaction Table: Date | Description | Debit | Credit | Balance
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


def generate_all_scenarios():
    base_dir = os.path.join(os.path.dirname(__file__), "..", "data", "pdf_scenarios")

    # =========================================================================
    # SCENARIO 1: SALARIED GOOD
    # Unrealistic Bank: Bank of Wonderland & Mars
    # =========================================================================
    s1_dir = os.path.join(base_dir, "test1_salaried_good")
    print("\n🔨 Generating Scenario 1: Salaried Good (Bank of Wonderland & Mars)...")

    create_pdf(
        os.path.join(s1_dir, "loan_application.pdf"),
        "PERSONAL LOAN APPLICATION FORM",
        [
            ("APPLICANT IDENTIFICATION", [
                ("Application Reference", "APP_S1_GOOD_SALARIED"),
                ("Full Name", "Rohan Sharma"),
                ("Date of Birth", "1994-08-12 (Age: 31)"),
                ("Employment Category", "Permanent Salaried"),
                ("Employer Organization", "Apex Cloud Systems Pvt Ltd"),
                ("Employment Tenure", "5.2 years (Joined 2021-03-15)"),
                ("Designation", "Lead Systems Architect"),
            ]),
            ("FACILITY REQUESTED", [
                ("Requested Loan Amount", "₹7,50,000 (INR)"),
                ("Loan Tenure", "36 months"),
                ("Loan Product", "Personal Loan"),
                ("Stated Purpose", "Home Renovation & Modernization"),
            ]),
            ("DOCUMENTATION ATTACHED", [
                ("Identity Document (KYC)", "Aadhaar & PAN Verified (Yes)"),
                ("Salary Slip Attached", "Yes (June 2026 attached)"),
                ("Bank Statement Attached", "Yes (Bank of Wonderland & Mars 6-Month attached)"),
                ("Form 16 Tax Certificate", "Yes (AY 2026-27 attached)"),
                ("Credit Card Statement", "Yes (Martian Orbit Titanium Card attached)"),
            ]),
        ],
    )

    create_pdf(
        os.path.join(s1_dir, "salary_slip.pdf"),
        "EMPLOYEE SALARY SLIP — JUNE 2026",
        [
            ("EMPLOYER DETAILS", [
                ("Company Name", "Apex Cloud Systems Pvt Ltd"),
                ("Corporate ID (CIN)", "U72200KA2018PTC112345"),
                ("Employee Name", "Rohan Sharma"),
                ("Employee Code", "EMP-9402"),
                ("Pay Period", "01-Jun-2026 to 30-Jun-2026"),
            ]),
            ("EARNINGS BREAKDOWN", [
                ("Basic Salary", "₹65,000.00"),
                ("House Rent Allowance (HRA)", "₹30,000.00"),
                ("Special Allowance", "₹20,000.00"),
                ("Performance Incentive", "₹10,000.00"),
                ("GROSS MONTHLY INCOME", "₹1,25,000.00"),
            ]),
            ("DEDUCTIONS", [
                ("Provident Fund (PF)", "₹7,800.00"),
                ("Professional Tax", "₹200.00"),
                ("TDS Income Tax Withholding", "₹12,500.00"),
                ("TOTAL MONTHLY DEDUCTIONS", "₹20,500.00"),
                ("NET SALARY DISBURSED", "₹1,04,500.00"),
            ]),
        ],
    )

    create_pdf(
        os.path.join(s1_dir, "form16_tax_certificate.pdf"),
        "CERTIFICATE OF TAX DEDUCTED AT SOURCE (FORM 16)",
        [
            ("ASSESSEE AND EMPLOYER PARTICULARS", [
                ("Employer Name", "Apex Cloud Systems Pvt Ltd"),
                ("Employee Name", "Rohan Sharma"),
                ("Assessment Year", "2026-27"),
                ("Financial Year", "2025-26"),
            ]),
            ("ANNUAL SALARY SUMMARY", [
                ("Gross Annual Salary", "₹15,00,000.00"),
                ("Total Tax Deducted (TDS)", "₹1,50,000.00"),
                ("Net Taxable Annual Income", "₹13,50,000.00"),
            ]),
        ],
    )

    create_pdf(
        os.path.join(s1_dir, "credit_report.pdf"),
        "CIBIL TRANSUNION CREDIT HEALTH REPORT",
        [
            ("BUREAU SCORE PROFILE", [
                ("Subject Name", "Rohan Sharma"),
                ("Credit Score", "784 (Rating: Excellent)"),
                ("Score Evaluation Date", "2026-06-30"),
                ("Active Credit Accounts", "2 Accounts"),
                ("Total Outstanding Debt", "₹4,50,000.00"),
                ("Existing Monthly EMI Obligation", "₹18,000.00"),
                ("Overdue Balance Amount", "₹0.00"),
                ("Past 24 Months Missed Payments", "0 missed payments (Impeccable)"),
                ("Delinquency Status", "Clean / Zero Default"),
            ]),
        ],
    )

    # 6-Month Bank Statement with Itemized Random Transactions (Jan 2026 to Jun 2026)
    bank_txs_s1 = [
        ("Date", "Description / Narration", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        # Month 1: Jan 2026
        ("2026-01-05", "SUPERMARKET ORGANIC GROCERY", "4500.00", "-", "45500.00"),
        ("2026-01-12", "FUEL FILL STATION MARTIAN EXPRESS", "2800.00", "-", "42700.00"),
        ("2026-01-20", "STREAMING & BROADBAND FIBER", "1600.00", "-", "41100.00"),
        ("2026-01-31", "NEFT SALARY - APEX CLOUD SYSTEMS", "-", "104500.00", "145600.00"),
        # Month 2: Feb 2026
        ("2026-02-05", "AUTO-DEBIT EMI LOAN A/C 9840", "18000.00", "-", "127600.00"),
        ("2026-02-12", "MUTUAL FUND SIP DEBIT", "10000.00", "-", "117600.00"),
        ("2026-02-18", "DINING & RESTAURANT OUTING", "3400.00", "-", "114200.00"),
        ("2026-02-28", "NEFT SALARY - APEX CLOUD SYSTEMS", "-", "104500.00", "218700.00"),
        # Month 3: Mar 2026
        ("2026-03-05", "AUTO-DEBIT EMI LOAN A/C 9840", "18000.00", "-", "200700.00"),
        ("2026-03-15", "GROCERY & UTILITY PAYMENT", "6500.00", "-", "194200.00"),
        ("2026-03-22", "PHARMACY HEALTH STORE", "1800.00", "-", "192400.00"),
        ("2026-03-31", "NEFT SALARY - APEX CLOUD SYSTEMS", "-", "104500.00", "296900.00"),
        # Month 4: Apr 2026
        ("2026-04-05", "AUTO-DEBIT EMI LOAN A/C 9840", "18000.00", "-", "278900.00"),
        ("2026-04-18", "ELECTRICITY & FIBER BROADBAND", "3200.00", "-", "275700.00"),
        ("2026-04-24", "BOOKSTORE & LEARNING SUBSCRIPTION", "2100.00", "-", "273600.00"),
        ("2026-04-30", "NEFT SALARY - APEX CLOUD SYSTEMS", "-", "104500.00", "378100.00"),
        # Month 5: May 2026
        ("2026-05-05", "AUTO-DEBIT EMI LOAN A/C 9840", "18000.00", "-", "360100.00"),
        ("2026-05-15", "FITNESS CLUB ANNUAL MEMBERSHIP", "8500.00", "-", "351600.00"),
        ("2026-05-20", "CARD AUTOPAY DEBIT", "22000.00", "-", "329600.00"),
        ("2026-05-31", "NEFT SALARY - APEX CLOUD SYSTEMS", "-", "104500.00", "434100.00"),
        # Month 6: Jun 2026
        ("2026-06-05", "AUTO-DEBIT EMI LOAN A/C 9840", "18000.00", "-", "416100.00"),
        ("2026-06-18", "DEPARTMENTAL SUPERSTORE", "4200.00", "-", "411900.00"),
        ("2026-06-30", "NEFT SALARY - APEX CLOUD SYSTEMS", "-", "104500.00", "516400.00"),
    ]

    bank_s1_metrics = sum_transactions(bank_txs_s1)

    create_pdf(
        os.path.join(s1_dir, "bank_statement.pdf"),
        "BANK OF WONDERLAND & MARS — 6-MONTH STATEMENT",
        [
            ("ACCOUNT PARTICULARS", [
                ("Bank Name", "Bank of Wonderland & Mars"),
                ("Account Holder", "Rohan Sharma"),
                ("Account Number", "BWM-9988221100"),
                ("Account Type", "Executive Salary Account"),
                ("Statement Period", "01-Jan-2026 to 30-Jun-2026 (6 Months)"),
                ("Opening Balance (01-Jan-2026)", "₹50,000.00"),
                ("Closing Balance (30-Jun-2026)", "₹5,16,400.00"),
            ]),
            ("ITEMIZED TRANSACTION RECORD", bank_txs_s1),
            ("6-MONTH AGGREGATE SUMMARY", [
                ("Total 6-Month Credits Deposited", f"₹{bank_s1_metrics['total_credits']:,.2f}"),
                ("Total 6-Month Debits Withdrawn", f"₹{bank_s1_metrics['total_debits']:,.2f}"),
                ("Total Verified Salary Credits (6 Months)", f"₹{bank_s1_metrics['total_credits']:,.2f} (6 Credits)"),
                ("Average Monthly Net Salary Derived", f"₹{bank_s1_metrics['avg_salary']:,.2f}"),
                ("Average Monthly Loan EMI Obligation", f"₹{bank_s1_metrics['avg_emi']:,.2f}"),
            ]),
        ],
    )

    # 6-Month Credit Card Statement with Itemized Purchases (Jan 2026 to Jun 2026)
    cc_txs_s1 = [
        ("Date", "Transaction Narration", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        # Jan 2026
        ("2026-01-14", "AMAZON ONLINE SHOPPING", "4200.00", "-", "4200.00"),
        ("2026-01-22", "CAFE & COFFEE ROASTERY", "950.00", "-", "5150.00"),
        # Feb 2026
        ("2026-02-10", "ELECTRONICS ACCESSORIES", "3500.00", "-", "8650.00"),
        ("2026-02-14", "AUTOPAY RECEIVED - THANK YOU", "-", "5150.00", "3500.00"),
        # Mar 2026
        ("2026-03-08", "PETROL AUTO FUEL STATION", "2800.00", "-", "6300.00"),
        ("2026-03-14", "AUTOPAY RECEIVED - THANK YOU", "-", "3500.00", "2800.00"),
        # Apr 2026
        ("2026-04-12", "AIRLINE TICKET BOOKING", "8500.00", "-", "11300.00"),
        ("2026-04-14", "AUTOPAY RECEIVED - THANK YOU", "-", "2800.00", "8500.00"),
        # May 2026
        ("2026-05-18", "AMAZON RETAIL ELECTRONICS", "6500.00", "-", "15000.00"),
        ("2026-05-24", "PETROL AUTO FUEL STATION", "3200.00", "-", "18200.00"),
        ("2026-05-28", "AUTOPAY RECEIVED - THANK YOU", "-", "8500.00", "9700.00"),
        # Jun 2026
        ("2026-06-02", "SUPERMARKET GROCERY STORE", "1800.00", "-", "11500.00"),
        ("2026-06-10", "HOME APPLIANCE STORE", "16500.00", "-", "28000.00"),
    ]

    cc_s1_metrics = sum_transactions(cc_txs_s1)

    create_pdf(
        os.path.join(s1_dir, "credit_card_statement.pdf"),
        "MARTIAN ORBIT TITANIUM CARD 6-MONTH STATEMENT",
        [
            ("CARD PARTICULARS", [
                ("Issuing Bank", "Bank of Wonderland & Mars"),
                ("Card Product", "Martian Orbit Titanium Card"),
                ("Cardholder Name", "Rohan Sharma"),
                ("Statement Billing Period", "01-Jan-2026 to 30-Jun-2026 (6 Months)"),
                ("Sanctioned Credit Limit", "₹3,00,000.00"),
                ("Statement Total Due", "₹28,000.00"),
                ("Minimum Amount Due", "₹1,500.00"),
                ("Card Utilization Ratio", "9.33%"),
            ]),
            ("6-MONTH RECENT CARD TRANSACTIONS", cc_txs_s1),
        ],
    )

    with open(os.path.join(s1_dir, "ground_truth.json"), "w") as f:
        json.dump({
            "application_id": "APP_S1_GOOD_SALARIED",
            "applicant_name": "Rohan Sharma",
            "applicant_type": "salaried",
            "employment_type": "permanent",
            "employer_or_business_name": "Apex Cloud Systems Pvt Ltd",
            "employment_duration_years": 5.2,
            "monthly_gross_income": 125000.0,
            "monthly_net_income": 104500.0,
            "annual_income": 1500000.0,
            "existing_monthly_emi": 18000.0,
            "outstanding_debt": 450000.0,
            "missed_payments": 0,
            "requested_loan_amount": 750000.0,
            "tenure_months": 36,
            "credit_score": 784,
            "credit_utilization_ratio": 0.0933,
            "credit_card_limit": 300000.0,
            "credit_card_total_balance": 28000.0,
            "credit_card_min_payment_due": 1500.0,
            "total_bank_credits_6m": bank_s1_metrics["total_credits"],
            "total_bank_debits_6m": bank_s1_metrics["total_debits"],
            "derived_monthly_salary_from_bank": bank_s1_metrics["avg_salary"],
            "derived_monthly_emi_from_bank": bank_s1_metrics["avg_emi"],
            "total_credit_card_spends_6m": cc_s1_metrics["total_spends"],
            "identity_verified": True,
            "income_document_available": True,
            "bank_statement_available": True,
            "tax_document_available": True,
            "loan_statement_available": True,
            "credit_card_statement_available": True,
            "expected_eligibility": "ELIGIBLE",
        }, f, indent=2)

    # =========================================================================
    # SCENARIO 2: SALARIED BAD
    # Unrealistic Bank: Atlantis Subsea Crypto Bank
    # =========================================================================
    s2_dir = os.path.join(base_dir, "test2_salaried_bad")
    print("\n🔨 Generating Scenario 2: Salaried Bad (Atlantis Subsea Crypto Bank)...")

    create_pdf(
        os.path.join(s2_dir, "loan_application.pdf"),
        "PERSONAL LOAN APPLICATION FORM",
        [
            ("APPLICANT IDENTIFICATION", [
                ("Application Reference", "APP_S2_BAD_SALARIED"),
                ("Applicant Name", "Karan Malhotra"),
                ("Date of Birth", "1997-11-04 (Age: 28)"),
                ("Employment Type", "Contract Staff"),
                ("Employer", "Zenith Retail Logistics"),
                ("Length of Employment", "1.2 years"),
            ]),
            ("LOAN FACILITY REQUESTED", [
                ("Requested Loan Amount", "₹4,00,000.00"),
                ("Tenure Required", "24 months"),
                ("Loan Purpose", "Debt Consolidation"),
            ]),
            ("SUBMITTED DOCUMENTS", [
                ("Identity Document Attached", "PAN Card (Yes)"),
                ("Salary Slip Attached", "Yes (Single Month)"),
                ("Bank Statement Attached", "Yes (Atlantis Subsea Crypto Bank attached)"),
                ("Credit Card Statement Attached", "Yes (Abyssal Coral Platinum Card)"),
            ]),
        ],
    )

    create_pdf(
        os.path.join(s2_dir, "salary_slip.pdf"),
        "MONTHLY PAY STATEMENT",
        [
            ("EMPLOYEE SUMMARY", [
                ("Employee Name", "Karan Malhotra"),
                ("Employer", "Zenith Retail Logistics"),
                ("Gross Monthly Salary", "₹45,000.00"),
                ("Net In-Hand Salary", "₹38,000.00"),
                ("Annual Stated Income", "₹5,40,000.00"),
            ]),
        ],
    )

    create_pdf(
        os.path.join(s2_dir, "credit_report.pdf"),
        "TRANSUNION BUREAU REPORT",
        [
            ("CREDIT RISK PROFILE", [
                ("Subject Name", "Karan Malhotra"),
                ("CIBIL Score", "550 (High Risk / Default Grade)"),
                ("Active Loan Accounts", "3 Accounts"),
                ("Total Outstanding Debt", "₹6,80,000.00"),
                ("Existing Monthly EMI", "₹22,000.00"),
                ("Overdue Balance Amount", "₹35,000.00"),
                ("Historical Missed Payments", "4 missed payments in last 12 months"),
                ("Delinquency Class", "Special Mention Account (SMA-2)"),
            ]),
        ],
    )

    # 6-Month Bank Statement with Itemized Random Transactions for Bad Salaried
    bank_txs_s2 = [
        ("Date", "Description / Narration", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        # Jan 2026
        ("2026-01-10", "FAST FOOD & DINING OUT", "2400.00", "-", "1200.00"),
        ("2026-01-31", "CONTRACT SALARY CREDIT", "-", "38000.00", "36800.00"),
        # Feb 2026
        ("2026-02-05", "AUTO-DEBIT LOAN EMI", "22000.00", "-", "14800.00"),
        ("2026-02-14", "MOBILE RECHARGE & OTT", "1200.00", "-", "13600.00"),
        ("2026-02-28", "CONTRACT SALARY CREDIT", "-", "38000.00", "51600.00"),
        # Mar 2026
        ("2026-03-05", "AUTO-DEBIT LOAN EMI", "22000.00", "-", "29600.00"),
        ("2026-03-18", "ONLINE GAMING & ENTERTAINMENT", "3500.00", "-", "26100.00"),
        ("2026-03-31", "CONTRACT SALARY CREDIT", "-", "38000.00", "64100.00"),
        # Apr 2026
        ("2026-04-05", "AUTO-DEBIT LOAN EMI", "22000.00", "-", "42100.00"),
        ("2026-04-20", "GROCERY STORE DEBIT", "4100.00", "-", "38000.00"),
        ("2026-04-30", "CONTRACT SALARY CREDIT", "-", "38000.00", "76000.00"),
        # May 2026
        ("2026-05-05", "AUTO-DEBIT LOAN EMI", "22000.00", "-", "54000.00"),
        ("2026-05-15", "OVERDRAFT LATE FEE CHARGE", "2500.00", "-", "51500.00"),
        ("2026-05-31", "CONTRACT SALARY CREDIT", "-", "38000.00", "89500.00"),
        # Jun 2026
        ("2026-06-05", "AUTO-DEBIT LOAN EMI", "22000.00", "-", "67500.00"),
        ("2026-06-20", "PETROL AUTO FUEL", "2800.00", "-", "64700.00"),
        ("2026-06-30", "CONTRACT SALARY CREDIT", "-", "38000.00", "102700.00"),
    ]

    bank_s2_metrics = sum_transactions(bank_txs_s2)

    create_pdf(
        os.path.join(s2_dir, "bank_statement.pdf"),
        "ATLANTIS SUBSEA CRYPTO BANK — 6-MONTH STATEMENT",
        [
            ("ACCOUNT OVERVIEW", [
                ("Bank Name", "Atlantis Subsea Crypto Bank"),
                ("Account Holder", "Karan Malhotra"),
                ("Statement Period", "01-Jan-2026 to 30-Jun-2026 (6 Months)"),
                ("Opening Balance", "₹3,600.00"),
                ("Closing Balance", "₹1,02,700.00"),
            ]),
            ("ITEMIZED TRANSACTIONS", bank_txs_s2),
            ("TRANSACTION SUMMARY", [
                ("Total 6-Month Salary Credits", f"₹{bank_s2_metrics['total_credits']:,.2f} (6 Credits)"),
                ("Average Derived Monthly Salary", f"₹{bank_s2_metrics['avg_salary']:,.2f}"),
                ("Total 6-Month EMI Debits", f"₹1,10,000.00 (5 Debits of ₹22,000.00)"),
                ("Average Monthly Loan EMI Obligation", f"₹{bank_s2_metrics['avg_emi']:,.2f}"),
            ]),
        ],
    )

    # 6-Month Credit Card Statement with Itemized Purchases for Bad Salaried
    cc_txs_s2 = [
        ("Date", "Transaction Narration", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        ("2026-01-15", "ONLINE FASHION SHOPPING", "12500.00", "-", "12500.00"),
        ("2026-02-18", "NIGHTCLUB & PUB DEBIT", "8500.00", "-", "21000.00"),
        ("2026-03-10", "SMARTPHONE EMI CONVERSION", "24000.00", "-", "45000.00"),
        ("2026-04-12", "RESTAURANT & FOOD DELIVERY", "6500.00", "-", "51500.00"),
        ("2026-05-14", "ELECTRONICS APPLIANCE PURCHASE", "28000.00", "-", "79500.00"),
        ("2026-06-08", "RETAIL MALL DEBIT", "19000.00", "-", "98500.00"),
    ]

    cc_s2_metrics = sum_transactions(cc_txs_s2)

    create_pdf(
        os.path.join(s2_dir, "credit_card_statement.pdf"),
        "ABYSSAL CORAL PLATINUM CARD 6-MONTH STATEMENT",
        [
            ("ACCOUNT SUMMARY", [
                ("Bank Name", "Atlantis Subsea Crypto Bank"),
                ("Cardholder Name", "Karan Malhotra"),
                ("Sanctioned Credit Limit", "₹1,00,000.00"),
                ("Current Total Balance / Dues", "₹98,500.00"),
                ("Minimum Amount Due", "₹15,000.00"),
                ("Credit Utilization Ratio", "98.5% (Maxed Out)"),
                ("Payment Status", "OVERDUE (30+ Days Past Due)"),
            ]),
            ("6-MONTH ITEMIZE TRANSACTIONS", cc_txs_s2),
            ("CARD CHARGES & INTEREST", [
                ("Finance & Interest Charges", "₹3,450.00"),
                ("Late Payment Penalty", "₹1,200.00"),
            ]),
        ],
    )

    with open(os.path.join(s2_dir, "ground_truth.json"), "w") as f:
        json.dump({
            "application_id": "APP_S2_BAD_SALARIED",
            "applicant_name": "Karan Malhotra",
            "applicant_type": "salaried",
            "employment_duration_years": 1.2,
            "monthly_gross_income": 45000.0,
            "monthly_net_income": 38000.0,
            "annual_income": 540000.0,
            "existing_monthly_emi": 22000.0,
            "outstanding_debt": 680000.0,
            "overdue_amount": 35000.0,
            "missed_payments": 4,
            "requested_loan_amount": 400000.0,
            "tenure_months": 24,
            "credit_score": 550,
            "credit_card_limit": 100000.0,
            "credit_card_total_balance": 98500.0,
            "credit_card_min_payment_due": 15000.0,
            "credit_utilization_ratio": 0.985,
            "total_bank_credits_6m": bank_s2_metrics["total_credits"],
            "total_bank_debits_6m": bank_s2_metrics["total_debits"],
            "derived_monthly_salary_from_bank": bank_s2_metrics["avg_salary"],
            "derived_monthly_emi_from_bank": bank_s2_metrics["avg_emi"],
            "total_credit_card_spends_6m": cc_s2_metrics["total_spends"],
            "identity_verified": True,
            "income_document_available": True,
            "bank_statement_available": True,
            "credit_card_statement_available": True,
            "expected_eligibility": "INELIGIBLE",
        }, f, indent=2)

    # =========================================================================
    # SCENARIO 3: BUSINESS GOOD
    # Unrealistic Bank: Intergalactic Bank of Andromeda
    # =========================================================================
    s3_dir = os.path.join(base_dir, "test3_business_good")
    print("\n🔨 Generating Scenario 3: Business Good (Intergalactic Bank of Andromeda)...")

    create_pdf(
        os.path.join(s3_dir, "loan_application.pdf"),
        "BUSINESS LOAN APPLICATION FORM",
        [
            ("ENTERPRISE PROFILE", [
                ("Application Reference", "APP_S3_GOOD_BUSINESS"),
                ("Promoter / Proprietor", "Meera Iyer"),
                ("Enterprise Name", "Iyer Precision Tools & Dies"),
                ("Business Constitution", "Sole Proprietorship"),
                ("Industry Domain", "Precision Tooling & CNC Engineering"),
                ("Years in Operation", "7.0 years (Established 2019)"),
            ]),
            ("CREDIT REQUIREMENT", [
                ("Requested Facility Amount", "₹15,00,000.00"),
                ("Tenure Requested", "48 months"),
                ("Facility Purpose", "Machinery Expansion & High-Precision CNC Lathe"),
            ]),
            ("SUBMITTED ATTACHMENTS", [
                ("Promoter Aadhaar & PAN", "Verified (Yes)"),
                ("GST Registration & Returns", "Yes (GSTIN 29ABCPI1234M1Z5)"),
                ("Audited P&L and Balance Sheet", "Yes (FY 2025-26 Attached)"),
                ("Bank Current Account Statement", "Yes (Intergalactic Bank of Andromeda attached)"),
                ("Commercial CIBIL Report", "Yes (CMR Score 2 / 770)"),
                ("Corporate Credit Card Statement", "Yes (Andromeda Celestial Fleet Card)"),
            ]),
        ],
    )

    create_pdf(
        os.path.join(s3_dir, "financial_statements.pdf"),
        "AUDITED BALANCE SHEET & PROFIT & LOSS ACCOUNT — FY 2025-26",
        [
            ("PROFIT & LOSS STATEMENT (FY 2025-26)", [
                ("Enterprise Legal Name", "Iyer Precision Tools & Dies"),
                ("Gross Annual Revenue / Turnover", "₹52,00,000.00"),
                ("Cost of Goods Sold (COGS)", "₹24,50,000.00"),
                ("Gross Operating Profit", "₹27,50,000.00"),
                ("Operating Expenses (Rent, Salaries, Power)", "₹8,00,000.00"),
                ("Depreciation & Interest", "₹1,50,000.00"),
                ("Net Profit Before Tax (Annual Income)", "₹18,00,000.00"),
                ("Effective Monthly Net Income", "₹1,50,000.00"),
            ]),
            ("BALANCE SHEET HIGHLIGHTS (AS ON 31-MAR-2026)", [
                ("Plant & Machinery Assets", "₹38,00,000.00"),
                ("Inventories & Raw Materials", "₹12,00,000.00"),
                ("Cash & Bank Balances", "₹8,20,000.00"),
                ("TOTAL ASSETS DECLARED", "₹50,00,000.00"),
                ("Total Secured Machinery Debt", "₹5,50,000.00"),
                ("Current Liabilities / Trade Payables", "₹3,50,000.00"),
                ("TOTAL LIABILITIES DECLARED", "₹5,50,000.00"),
            ]),
        ],
    )

    create_pdf(
        os.path.join(s3_dir, "gst_return.pdf"),
        "GSTR-3B ANNUAL FILING SUMMARY",
        [
            ("GSTIN SUMMARY", [
                ("GSTIN", "29ABCPI1234M1Z5"),
                ("Legal Name", "Meera Iyer"),
                ("Fiscal Period", "April 2025 to March 2026"),
                ("Total Taxable Value (Turnover)", "₹52,00,000.00"),
                ("Total IGST + CGST + SGST Paid", "₹9,36,000.00"),
                ("Compliance Rating", "100% On-Time Filing"),
            ]),
        ],
    )

    create_pdf(
        os.path.join(s3_dir, "commercial_credit_report.pdf"),
        "COMMERCIAL CREDIT BUREAU REPORT",
        [
            ("ENTERPRISE CREDIT HEALTH", [
                ("Enterprise Name", "Iyer Precision Tools & Dies"),
                ("Commercial CIBIL Score", "770 (Prime Grade)"),
                ("Active Commercial Facilities", "1 Secured Machinery Loan"),
                ("Existing Monthly EMI Obligation", "₹25,000.00"),
                ("Total Outstanding Business Debt", "₹5,50,000.00"),
                ("Delinquencies / Overdue", "₹0.00 (Zero default)"),
                ("Historical Missed Payments", "0 missed payments in 48 months"),
            ]),
        ],
    )

    # 6-Month Current Account Transactions with Random Vendor & Inward Receipts
    bank_txs_s3 = [
        ("Date", "Description / Narration", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        # Jan 2026
        ("2026-01-15", "INWARD RTGS - BHARAT HEAVY DIES", "-", "420000.00", "520000.00"),
        ("2026-01-20", "VENDOR RAW STEEL SUPPLIES", "180000.00", "-", "340000.00"),
        ("2026-01-25", "WORKSHOP ELECTRICAL POWER BILL", "18000.00", "-", "322000.00"),
        # Feb 2026
        ("2026-02-05", "AUTO-DEBIT MACHINERY EMI", "25000.00", "-", "297000.00"),
        ("2026-02-18", "INWARD RTGS - PRECISION MOULDS", "-", "460000.00", "757000.00"),
        ("2026-02-24", "CNC CUTTING OIL & LUBRICANTS", "14000.00", "-", "743000.00"),
        # Mar 2026
        ("2026-03-05", "AUTO-DEBIT MACHINERY EMI", "25000.00", "-", "718000.00"),
        ("2026-03-22", "INWARD NEFT - AUTOMOTIVE COMPONENTS", "-", "480000.00", "1198000.00"),
        ("2026-03-28", "STAFF WORKSHOP TEA & SNACKS", "4500.00", "-", "1193500.00"),
        # Apr 2026
        ("2026-04-05", "AUTO-DEBIT MACHINERY EMI", "25000.00", "-", "1168500.00"),
        ("2026-04-20", "GST TAX PAYMENT CHALLAN", "78000.00", "-", "1090500.00"),
        ("2026-04-26", "INWARD RTGS - AEROSPACE FIXTURES", "-", "390000.00", "1480500.00"),
        # May 2026
        ("2026-05-05", "AUTO-DEBIT MACHINERY EMI", "25000.00", "-", "1455500.00"),
        ("2026-05-25", "INWARD RTGS - AERO ENGINE PARTS", "-", "510000.00", "1965500.00"),
        ("2026-05-28", "OFFICE STATIONERY & PRINTER TONER", "6500.00", "-", "1959000.00"),
        # Jun 2026
        ("2026-06-05", "AUTO-DEBIT MACHINERY EMI", "25000.00", "-", "1934000.00"),
        ("2026-06-28", "INWARD RTGS - DEFENCE TOOLING", "-", "450000.00", "2384000.00"),
    ]

    bank_s3_metrics = sum_transactions(bank_txs_s3)

    create_pdf(
        os.path.join(s3_dir, "bank_statement.pdf"),
        "INTERGALACTIC BANK OF ANDROMEDA — CURRENT ACCOUNT STATEMENT",
        [
            ("CURRENT ACCOUNT DETAILS", [
                ("Bank Name", "Intergalactic Bank of Andromeda"),
                ("Account Holder", "Iyer Precision Tools & Dies"),
                ("Account Type", "Current Account - Enterprise Prime"),
                ("Total Annual Banking Credits", "₹54,20,000.00"),
                ("Average Monthly Balance (AMB)", "₹4,50,000.00"),
                ("Cheque Returns / Bounces", "0 (Impeccable Record)"),
            ]),
            ("SAMPLE BUSINESS TRANSACTIONS", bank_txs_s3),
        ],
    )

    # 6-Month Corporate Credit Card Statement with Random Expenses
    cc_txs_s3 = [
        ("Date", "Transaction Narration", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        ("2026-01-18", "INDUSTRIAL TOOLING SUPPLIES", "14500.00", "-", "14500.00"),
        ("2026-02-12", "AUTOPAY RECEIVED - THANK YOU", "-", "14500.00", "0.00"),
        ("2026-02-22", "CAD SOFTWARE ANNUAL LICENSE", "18000.00", "-", "18000.00"),
        ("2026-03-15", "EXHIBITION FLIGHT & HOTEL", "12500.00", "-", "30500.00"),
        ("2026-04-10", "AUTOPAY RECEIVED - THANK YOU", "-", "30500.00", "0.00"),
        ("2026-05-14", "CLIENT HOSPITALITY DINNER", "8500.00", "-", "8500.00"),
        ("2026-06-18", "SAFETY HELMETS & FACTORY GEAR", "36500.00", "-", "45000.00"),
    ]

    cc_s3_metrics = sum_transactions(cc_txs_s3)

    create_pdf(
        os.path.join(s3_dir, "credit_card_statement.pdf"),
        "ANDROMEDA CELESTIAL FLEET CORPORATE CARD STATEMENT",
        [
            ("CARD PARTICULARS", [
                ("Issuing Bank", "Intergalactic Bank of Andromeda"),
                ("Card Account", "Iyer Precision Tools & Dies"),
                ("Sanctioned Limit", "₹5,00,000.00"),
                ("Statement Total Due", "₹45,000.00"),
                ("Minimum Due", "₹2,500.00"),
                ("Utilization", "9.0%"),
                ("Payment History", "Auto-paid in full every month"),
            ]),
            ("6-MONTH CORPORATE CARD TRANSACTIONS", cc_txs_s3),
        ],
    )

    with open(os.path.join(s3_dir, "ground_truth.json"), "w") as f:
        json.dump({
            "application_id": "APP_S3_GOOD_BUSINESS",
            "applicant_name": "Meera Iyer",
            "applicant_type": "self_employed",
            "employment_type": "business_owner",
            "employer_or_business_name": "Iyer Precision Tools & Dies",
            "employment_duration_years": 7.0,
            "monthly_gross_income": 187500.0,
            "monthly_net_income": 150000.0,
            "annual_revenue": 5200000.0,
            "annual_income": 2250000.0,
            "existing_monthly_emi": 25000.0,
            "outstanding_debt": 550000.0,
            "missed_payments": 0,
            "requested_loan_amount": 1500000.0,
            "tenure_months": 48,
            "credit_score": 770,
            "credit_card_limit": 500000.0,
            "credit_card_total_balance": 45000.0,
            "credit_card_min_payment_due": 2500.0,
            "credit_utilization_ratio": 0.09,
            "assets": 5000000.0,
            "liabilities": 550000.0,
            "total_bank_credits_6m": bank_s3_metrics["total_credits"],
            "total_bank_debits_6m": bank_s3_metrics["total_debits"],
            "derived_monthly_emi_from_bank": bank_s3_metrics["avg_emi"],
            "total_credit_card_spends_6m": cc_s3_metrics["total_spends"],
            "identity_verified": True,
            "income_document_available": True,
            "bank_statement_available": True,
            "tax_document_available": True,
            "loan_statement_available": True,
            "credit_card_statement_available": True,
            "expected_eligibility": "ELIGIBLE",
        }, f, indent=2)

    # =========================================================================
    # SCENARIO 4: BUSINESS BAD
    # Unrealistic Bank: Gryffindor Magical Vault Bank
    # =========================================================================
    s4_dir = os.path.join(base_dir, "test4_business_bad")
    print("\n🔨 Generating Scenario 4: Business Bad (Gryffindor Magical Vault Bank)...")

    create_pdf(
        os.path.join(s4_dir, "loan_application.pdf"),
        "BUSINESS LOAN APPLICATION",
        [
            ("APPLICANT & BUSINESS PROFILE", [
                ("Application Reference", "APP_S4_BAD_BUSINESS"),
                ("Promoter Name", "Rajesh Gupta"),
                ("Enterprise Name", "Apex Fasteners & Hardware"),
                ("Years in Business", "3.0 years"),
                ("Requested Loan Facility", "₹25,00,000.00"),
                ("Tenure", "36 months"),
            ]),
        ],
    )

    create_pdf(
        os.path.join(s4_dir, "itr_computation.pdf"),
        "ITR STATEMENT OF INCOME",
        [
            ("TAX DECLARATION", [
                ("Assessee Name", "Rajesh Gupta"),
                ("Enterprise", "Apex Fasteners & Hardware"),
                ("Declared Annual Turnover", "₹18,00,000.00"),
                ("Net Taxable Profit", "₹2,40,000.00 (Monthly: ₹20,000.00)"),
            ]),
        ],
    )

    create_pdf(
        os.path.join(s4_dir, "commercial_credit_report.pdf"),
        "COMMERCIAL BUREAU REPORT",
        [
            ("BUREAU RECORD", [
                ("Enterprise", "Apex Fasteners & Hardware"),
                ("CIBIL Score", "580 (Sub-Standard)"),
                ("Total Outstanding Debt", "₹32,00,000.00 (Debt-to-Revenue > 1.7)"),
                ("Existing Monthly EMI Obligations", "₹58,000.00"),
                ("Current Overdue Amount", "₹80,000.00"),
                ("Missed Payments", "2 missed payments recorded in last 12 months"),
            ]),
        ],
    )

    # 6-Month Current Account Transactions with Random Overdrafts & Bounces
    bank_txs_s4 = [
        ("Date", "Description / Narration", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        ("2026-01-12", "HARDWARE RETAIL SALES CASH DEPOSIT", "-", "65000.00", "72000.00"),
        ("2026-01-20", "AUTO-DEBIT LOAN EMI OVERDUE", "58000.00", "-", "14000.00"),
        ("2026-02-14", "LOCAL VENDOR CASH PAYMENT", "8500.00", "-", "5500.00"),
        ("2026-02-28", "SCRAP METAL SALE INWARD", "-", "42000.00", "47500.00"),
        ("2026-03-05", "CHEQUE RETURN CHARGES - INSUFFICIENT FUNDS", "1500.00", "-", "46000.00"),
        ("2026-03-18", "AUTO-DEBIT LOAN EMI", "58000.00", "-", "-12000.00"),
        ("2026-04-10", "OVERDRAFT FACILITY INTEREST", "3200.00", "-", "-15200.00"),
        ("2026-04-25", "CASH COUNTER DEPOSIT", "-", "50000.00", "34800.00"),
        ("2026-05-15", "AUTO-DEBIT LOAN EMI", "58000.00", "-", "-23200.00"),
        ("2026-06-20", "STORE UTILITY BILL", "4500.00", "-", "-27700.00"),
    ]

    bank_s4_metrics = sum_transactions(bank_txs_s4)

    create_pdf(
        os.path.join(s4_dir, "bank_statement.pdf"),
        "GRYFFINDOR MAGICAL VAULT BANK — CURRENT ACCOUNT",
        [
            ("ACCOUNT PARTICULARS", [
                ("Bank Name", "Gryffindor Magical Vault Bank"),
                ("Account Holder", "Apex Fasteners & Hardware"),
                ("Average Monthly Balance", "₹12,000.00"),
                ("Inward Cheque Returns / Bounces", "3 Returns recorded"),
            ]),
            ("6-MONTH CURRENT ACCOUNT TRANSACTIONS", bank_txs_s4),
        ],
    )

    # Credit Card Statement with Random Expenses
    cc_txs_s4 = [
        ("Date", "Transaction Narration", "Debit (INR)", "Credit (INR)", "Balance (INR)"),
        ("2026-01-20", "FUEL TRUCK FILL UP", "6500.00", "-", "6500.00"),
        ("2026-02-15", "ONLINE WHOLESALE STORE", "18000.00", "-", "24500.00"),
        ("2026-03-12", "RESTAURANT MEETING", "4200.00", "-", "28700.00"),
        ("2026-04-18", "LATE PAYMENT FEE CHARGE", "1500.00", "-", "30200.00"),
        ("2026-05-10", "HARDWARE PARTS DELIVERY", "15000.00", "-", "45200.00"),
    ]

    cc_s4_metrics = sum_transactions(cc_txs_s4)

    create_pdf(
        os.path.join(s4_dir, "credit_card_statement.pdf"),
        "PHOENIX FEATHER RESERVE CARD STATEMENT",
        [
            ("CARD PROFILE", [
                ("Bank Name", "Gryffindor Magical Vault Bank"),
                ("Cardholder", "Apex Fasteners & Hardware"),
                ("Sanctioned Limit", "₹50,000.00"),
                ("Total Balance Due", "₹45,200.00"),
                ("Card Utilization", "90.4% (Critical)"),
            ]),
            ("TRANSACTION HISTORY", cc_txs_s4),
        ],
    )

    with open(os.path.join(s4_dir, "ground_truth.json"), "w") as f:
        json.dump({
            "application_id": "APP_S4_BAD_BUSINESS",
            "applicant_name": "Rajesh Gupta",
            "applicant_type": "self_employed",
            "employment_duration_years": 3.0,
            "monthly_gross_income": 20000.0,
            "monthly_net_income": 20000.0,
            "annual_revenue": 1800000.0,
            "annual_income": 240000.0,
            "existing_monthly_emi": 58000.0,
            "outstanding_debt": 3200000.0,
            "overdue_amount": 80000.0,
            "missed_payments": 2,
            "requested_loan_amount": 2500000.0,
            "credit_score": 580,
            "credit_card_limit": 50000.0,
            "credit_card_total_balance": 45200.0,
            "credit_utilization_ratio": 0.904,
            "total_bank_credits_6m": bank_s4_metrics["total_credits"],
            "total_bank_debits_6m": bank_s4_metrics["total_debits"],
            "derived_monthly_emi_from_bank": bank_s4_metrics["avg_emi"],
            "total_credit_card_spends_6m": cc_s4_metrics["total_spends"],
            "identity_verified": True,
            "income_document_available": True,
            "bank_statement_available": True,
            "tax_document_available": True,
            "loan_statement_available": True,
            "credit_card_statement_available": True,
            "expected_eligibility": "INELIGIBLE",
        }, f, indent=2)

    print("\n✅ All 4 realistic PDF scenarios with unrealistic bank names and 6-month random transactions regenerated!")


if __name__ == "__main__":
    generate_all_scenarios()
