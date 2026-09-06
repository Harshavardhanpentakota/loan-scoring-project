"""Generates result.pdf from ranking_results.json.

Produces an executive underwriting and portfolio ranking PDF report:
- Cover Banner & Portfolio KPI Cards
- Portfolio Ranking Leaderboard Table (Qualified 1..N & Ineligible Queue)
- Comprehensive Application Dossiers:
  * Key facts & decision
  * Mathematical Component Scoring Table (Raw, Weight, Contribution, Formula)
  * 6-Month Bank & Credit Card Statement Financial Rollups
  * LLM Underwriting Evaluation Summary (Pros & Cons by Criticality: HIGH, MED, LOW)
- Running Headers, Footers, and Page Numbering
"""

import os
import json
import fitz  # PyMuPDF


def build_result_pdf(json_path: str, output_pdf_path: str):
    with open(json_path, "r") as f:
        data = json.load(f)

    doc = fitz.open()

    page_width = 595.0
    page_height = 842.0
    margin_left = 36.0
    margin_right = page_width - margin_left
    margin_top = 40.0
    margin_bottom = page_height - 35.0

    # Color Palette
    c_navy = (0.10, 0.18, 0.32)       # #1A2E52
    c_slate = (0.22, 0.35, 0.52)      # #385985
    c_light_bg = (0.95, 0.96, 0.98)   # #F2F5FA
    c_card_bg = (0.98, 0.98, 0.99)
    c_text_dark = (0.12, 0.12, 0.14)
    c_text_muted = (0.40, 0.42, 0.48)
    c_border = (0.82, 0.85, 0.90)

    c_green = (0.10, 0.55, 0.25)      # Prime / Low Risk
    c_green_bg = (0.92, 0.98, 0.94)
    c_amber = (0.75, 0.48, 0.05)      # Med Risk
    c_amber_bg = (0.99, 0.97, 0.90)
    c_red = (0.75, 0.15, 0.15)        # High Risk
    c_red_bg = (0.99, 0.92, 0.92)

    def new_page():
        return doc.new_page(width=page_width, height=page_height)

    current_page = new_page()
    y = margin_top

    def check_page_break(needed_space: float):
        nonlocal current_page, y
        if y + needed_space > margin_bottom:
            current_page = new_page()
            y = margin_top
            draw_running_header(current_page)

    def draw_running_header(page):
        nonlocal y
        page.draw_rect(fitz.Rect(margin_left, 18, margin_right, 30), color=None, fill=(0.95, 0.96, 0.98))
        page.insert_text(
            (margin_left + 6, 26),
            f"LOAN UNDERWRITING & RANKING REPORT — MODEL: {data.get('model_version', 'personal_loan_v1').upper()}",
            fontsize=7.5,
            color=c_text_muted,
            fontname="helv",
        )
        page.draw_line(fitz.Point(margin_left, 32), fitz.Point(margin_right, 32), color=c_border, width=0.5)
        y = 48

    # =========================================================================
    # PAGE 1: TITLE BANNER & PORTFOLIO OVERVIEW
    # =========================================================================

    # Title Banner
    current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 68), color=None, fill=c_navy)
    current_page.insert_text((margin_left + 16, y + 26), "LOAN UNDERWRITING & RANKING REPORT", fontsize=16, color=(1, 1, 1), fontname="helv")
    current_page.insert_text((margin_left + 16, y + 44), "Deterministic Mathematical Scoring & Parallel LLM Underwriting Evaluation", fontsize=9.5, color=(0.82, 0.88, 0.98), fontname="helv")
    current_page.insert_text((margin_left + 16, y + 58), f"Model: {data.get('model_version')} | Audited & Verified Pipeline | Confidential Underwriting Dossier", fontsize=8, color=(0.65, 0.75, 0.90), fontname="helv")
    y += 82

    # KPI Metric Cards
    qualified_list = data.get("qualified_ranked", [])
    ineligible_list = data.get("ineligible_queue", [])
    review_list = data.get("manual_review_queue", [])
    total_apps = len(qualified_list) + len(ineligible_list) + len(review_list)
    avg_score = round(sum(q["final_score"] for q in qualified_list) / len(qualified_list), 2) if qualified_list else 0.0

    kpis = [
        ("Total Evaluated", str(total_apps), c_slate),
        ("Qualified (Eligible)", str(len(qualified_list)), c_green),
        ("Ineligible (Declined)", str(len(ineligible_list)), c_red),
        ("Avg Qualified Score", f"{avg_score} / 100", c_navy),
    ]

    card_w = (margin_right - margin_left - (len(kpis) - 1) * 10) / len(kpis)
    for i, (title, val, col) in enumerate(kpis):
        cx = margin_left + i * (card_w + 10)
        current_page.draw_rect(fitz.Rect(cx, y, cx + card_w, y + 42), color=c_border, fill=c_light_bg, width=0.6)
        current_page.insert_text((cx + 8, y + 15), title.upper(), fontsize=7.5, color=c_text_muted, fontname="helv")
        current_page.insert_text((cx + 8, y + 33), val, fontsize=13, color=col, fontname="helv")
    y += 54

    # Portfolio Leaderboard Table
    current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 22), color=None, fill=c_slate)
    current_page.insert_text((margin_left + 10, y + 15), "🏆 PORTFOLIO RANKING LEADERBOARD (QUALIFIED APPLICANTS)", fontsize=9.5, color=(1, 1, 1), fontname="helv")
    y += 24

    # Table Header
    current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 18), color=None, fill=(0.88, 0.91, 0.95))
    headers = [
        ("Rank", 35),
        ("App ID", 115),
        ("Applicant Name", 110),
        ("Score", 55),
        ("Criticality", 80),
        ("Credit", 45),
        ("DTI", 45),
        ("Monthly Net", 60),
    ]
    hx = margin_left + 5
    for htitle, hw in headers:
        current_page.insert_text((hx, y + 12), htitle, fontsize=8, color=c_navy, fontname="helv")
        hx += hw
    y += 20

    # Table Rows
    for q in qualified_list:
        crit = q.get("criticality", "MED")
        crit_color = c_green if crit == "LOW" else (c_amber if crit == "MED" else c_red)
        crit_badge = f"{crit} RISK"

        current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 17), color=None, fill=(0.98, 0.99, 1.0) if q["rank"] % 2 == 1 else (1, 1, 1))
        current_page.draw_line(fitz.Point(margin_left, y + 17), fitz.Point(margin_right, y + 17), color=c_border, width=0.4)

        rx = margin_left + 5
        # Rank
        current_page.insert_text((rx + 6, y + 12), str(q["rank"]), fontsize=8.5, color=c_text_dark, fontname="helv")
        rx += 35
        # App ID
        current_page.insert_text((rx, y + 12), q["application_id"][:19], fontsize=8, color=c_navy, fontname="helv")
        rx += 115
        # Name
        current_page.insert_text((rx, y + 12), q.get("applicant_name", "N/A")[:18], fontsize=8, color=c_text_dark, fontname="helv")
        rx += 110
        # Score
        current_page.insert_text((rx, y + 12), f"{q['final_score']:.2f}", fontsize=8.5, color=c_navy, fontname="helv")
        rx += 55
        # Criticality badge
        current_page.draw_rect(fitz.Rect(rx - 2, y + 3, rx + 62, y + 15), color=None, fill=c_green_bg if crit == "LOW" else c_amber_bg)
        current_page.insert_text((rx + 4, y + 12), crit_badge, fontsize=7.5, color=crit_color, fontname="helv")
        rx += 80
        # Credit
        current_page.insert_text((rx, y + 12), str(q.get("credit_score") or "N/A"), fontsize=8, color=c_text_dark, fontname="helv")
        rx += 45
        # DTI
        dti_str = f"{q['dti']*100:.1f}%" if q.get("dti") is not None else "N/A"
        current_page.insert_text((rx, y + 12), dti_str, fontsize=8, color=c_text_dark, fontname="helv")
        rx += 45
        # Monthly Net
        inc_str = f"₹{q.get('monthly_income', 0):,.0f}" if q.get("monthly_income") else "N/A"
        current_page.insert_text((rx, y + 12), inc_str, fontsize=8, color=c_text_dark, fontname="helv")

        y += 18

    # Ineligible Table Section
    y += 10
    current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 20), color=None, fill=(0.75, 0.20, 0.20))
    current_page.insert_text((margin_left + 10, y + 14), "❌ INELIGIBLE QUEUE (DECLINED / POLICY GATE FAILURES)", fontsize=9, color=(1, 1, 1), fontname="helv")
    y += 22

    current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 17), color=None, fill=(0.95, 0.90, 0.90))
    current_page.insert_text((margin_left + 10, y + 12), "App ID", fontsize=8, color=c_red, fontname="helv")
    current_page.insert_text((margin_left + 140, y + 12), "Applicant Name", fontsize=8, color=c_red, fontname="helv")
    current_page.insert_text((margin_left + 250, y + 12), "Score", fontsize=8, color=c_red, fontname="helv")
    current_page.insert_text((margin_left + 300, y + 12), "Risk", fontsize=8, color=c_red, fontname="helv")
    current_page.insert_text((margin_left + 360, y + 12), "Primary Rejection Reason", fontsize=8, color=c_red, fontname="helv")
    y += 18

    audit_traces = data.get("audit_traces", {})
    for inelig in ineligible_list:
        aid = inelig["application_id"]
        crit = inelig.get("criticality", "HIGH")
        failed = audit_traces.get(aid, {}).get("eligibility", {}).get("failed_rules", [])
        fail_str = "; ".join(failed) if failed else "Policy Threshold Failure"

        current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 17), color=None, fill=(0.99, 0.96, 0.96))
        current_page.draw_line(fitz.Point(margin_left, y + 17), fitz.Point(margin_right, y + 17), color=c_border, width=0.4)

        current_page.insert_text((margin_left + 10, y + 12), aid[:20], fontsize=8, color=c_text_dark, fontname="helv")
        current_page.insert_text((margin_left + 140, y + 12), inelig.get("applicant_name", "N/A")[:16], fontsize=8, color=c_text_dark, fontname="helv")
        current_page.insert_text((margin_left + 250, y + 12), f"{inelig['final_score']:.2f}", fontsize=8.5, color=c_red, fontname="helv")
        current_page.insert_text((margin_left + 300, y + 12), f"{crit} RISK", fontsize=7.5, color=c_red, fontname="helv")
        current_page.insert_text((margin_left + 360, y + 12), fail_str[:38], fontsize=7.5, color=c_text_dark, fontname="helv")
        y += 18

    # =========================================================================
    # APPLICATION DOSSIERS
    # =========================================================================
    all_applicants = qualified_list + review_list + ineligible_list

    for app in all_applicants:
        aid = app["application_id"]
        trace = audit_traces.get(aid, {})
        scoring_data = trace.get("scoring", {})
        components = scoring_data.get("components", {})
        features = trace.get("features", [])
        summary = app.get("evaluation_summary") or {}
        crit = app.get("criticality", "MED")
        is_eligible = app.get("eligibility_status") == "ELIGIBLE"

        # Each application starts on a clean fresh page
        current_page = new_page()
        y = margin_top
        draw_running_header(current_page)

        # Applicant Dossier Header Banner
        banner_bg = c_navy if is_eligible else (0.45, 0.15, 0.15)
        current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 46), color=None, fill=banner_bg)
        
        # Applicant Name & App ID
        current_page.insert_text((margin_left + 12, y + 20), f"APPLICATION DOSSIER: {app.get('applicant_name', 'N/A')}", fontsize=13, color=(1, 1, 1), fontname="helv")
        current_page.insert_text((margin_left + 12, y + 36), f"Docket: {aid} | Category: {app.get('applicant_type', 'salaried').title()} | Underwriting Decision: {app.get('eligibility_status')}", fontsize=8.5, color=(0.85, 0.90, 0.98), fontname="helv")

        # Score Box on Right
        current_page.draw_rect(fitz.Rect(margin_right - 105, y + 6, margin_right - 10, y + 40), color=None, fill=(1, 1, 1))
        current_page.insert_text((margin_right - 98, y + 19), "OVERALL SCORE", fontsize=7, color=c_text_muted, fontname="helv")
        current_page.insert_text((margin_right - 98, y + 34), f"{app['final_score']:.2f}", fontsize=13, color=banner_bg, fontname="helv")
        current_page.insert_text((margin_right - 54, y + 34), "/ 100", fontsize=8, color=c_text_muted, fontname="helv")
        y += 56

        # Risk Criticality Badge Bar
        crit_box_bg = c_green_bg if crit == "LOW" else (c_amber_bg if crit == "MED" else c_red_bg)
        crit_box_fg = c_green if crit == "LOW" else (c_amber if crit == "MED" else c_red)
        crit_icon = "🟢" if crit == "LOW" else ("🟡" if crit == "MED" else "🔴")
        crit_title = "LOW RISK (Prime Grade / Low Risk Profile)" if crit == "LOW" else ("MED RISK (Moderate Risk / Standard Standard Grade)" if crit == "MED" else "HIGH RISK (Subprime / Elevated Delinquency Risk)")

        current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 22), color=c_border, fill=crit_box_bg, width=0.5)
        current_page.insert_text((margin_left + 10, y + 15), f"RISK CRITICALITY CLASSIFICATION: {crit_icon} {crit_title}", fontsize=8.5, color=crit_box_fg, fontname="helv")
        y += 30

        # SECTION 1: Mathematical Scoring Breakdown Table
        current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 16), color=None, fill=c_slate)
        current_page.insert_text((margin_left + 8, y + 12), "1. MATHEMATICAL SCORING BREAKDOWN (Deterministic Functions)", fontsize=8.5, color=(1, 1, 1), fontname="helv")
        y += 18

        current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 16), color=None, fill=(0.92, 0.94, 0.97))
        current_page.insert_text((margin_left + 8, y + 11), "Component", fontsize=8, color=c_navy, fontname="helv")
        current_page.insert_text((margin_left + 140, y + 11), "Raw Score", fontsize=8, color=c_navy, fontname="helv")
        current_page.insert_text((margin_left + 210, y + 11), "Weight", fontsize=8, color=c_navy, fontname="helv")
        current_page.insert_text((margin_left + 265, y + 11), "Contribution", fontsize=8, color=c_navy, fontname="helv")
        current_page.insert_text((margin_left + 340, y + 11), "Component Underwriting Notes", fontsize=8, color=c_navy, fontname="helv")
        y += 16

        for comp_k, comp_v in components.items():
            comp_title = comp_k.replace("_", " ").title()
            raw = f"{comp_v.get('raw_score', 0):.1f}/100"
            wt = f"{comp_v.get('weight', 0)*100:.0f}%"
            contrib = f"{comp_v.get('contribution', 0):.2f} pts"
            notes = comp_v.get("notes") or ""

            current_page.draw_line(fitz.Point(margin_left, y + 15), fitz.Point(margin_right, y + 15), color=c_border, width=0.4)
            current_page.insert_text((margin_left + 8, y + 11), comp_title[:24], fontsize=8, color=c_text_dark, fontname="helv")
            current_page.insert_text((margin_left + 140, y + 11), raw, fontsize=8, color=c_navy, fontname="helv")
            current_page.insert_text((margin_left + 210, y + 11), wt, fontsize=8, color=c_text_muted, fontname="helv")
            current_page.insert_text((margin_left + 265, y + 11), contrib, fontsize=8, color=c_navy, fontname="helv")
            current_page.insert_text((margin_left + 340, y + 11), notes[:44], fontsize=7.5, color=c_text_dark, fontname="helv")
            y += 16

        # Score Sum Line
        current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 16), color=None, fill=c_light_bg)
        current_page.insert_text((margin_left + 8, y + 12), "FINAL DETERMINISTIC SCORE", fontsize=8.5, color=c_navy, fontname="helv")
        current_page.insert_text((margin_left + 210, y + 12), "100%", fontsize=8, color=c_text_muted, fontname="helv")
        current_page.insert_text((margin_left + 265, y + 12), f"{app['final_score']:.2f} pts", fontsize=8.5, color=c_navy, fontname="helv")
        current_page.insert_text((margin_left + 340, y + 12), "Calculated strictly via pure mathematical sum", fontsize=7.5, color=c_text_muted, fontname="helv")
        y += 24

        # SECTION 2: 6-Month Statement Transactions Rollups & Ratios
        current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 16), color=None, fill=c_slate)
        current_page.insert_text((margin_left + 8, y + 12), "2. 6-MONTH STATEMENT FINANCIAL ROLLUPS & TRANSACTION RATIOS", fontsize=8.5, color=(1, 1, 1), fontname="helv")
        y += 20

        tx_feats = [
            f for f in features
            if any(k in f.get("feature", "") for k in ["bank", "credit_card", "dti", "emi_ratio"]) and f.get("result") is not None
        ]

        if tx_feats:
            col_w = (margin_right - margin_left - 12) / 2
            for idx, f in enumerate(tx_feats):
                col_idx = idx % 2
                fx = margin_left + col_idx * (col_w + 12)
                fy = y + (idx // 2) * 22

                val = f["result"]
                val_str = f"₹{val:,.2f}" if any(k in f["feature"] for k in ["credits", "debits", "salary", "spends", "emi"]) else (f"{val*100:.1f}%" if any(k in f["feature"] for k in ["dti", "ratio", "utilization"]) else str(val))
                f_name = f["feature"].replace("_", " ").title()

                current_page.draw_rect(fitz.Rect(fx, fy, fx + col_w, fy + 19), color=c_border, fill=c_card_bg, width=0.4)
                current_page.insert_text((fx + 6, fy + 13), f_name[:24], fontsize=7.5, color=c_text_muted, fontname="helv")
                current_page.insert_text((fx + col_w - 75, fy + 13), val_str, fontsize=8, color=c_navy, fontname="helv")

            y += ((len(tx_feats) + 1) // 2) * 22 + 8
        else:
            y += 8

        # SECTION 3: LLM Executive Underwriting Evaluation Summary
        check_page_break(130)
        current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 16), color=None, fill=c_slate)
        current_page.insert_text((margin_left + 8, y + 12), "3. LLM UNDERWRITING EVALUATION SUMMARY (Pros & Cons by Criticality)", fontsize=8.5, color=(1, 1, 1), fontname="helv")
        y += 20

        # Executive Verdict Box
        verdict = summary.get("executive_verdict") or ""
        if verdict:
            current_page.draw_rect(fitz.Rect(margin_left, y, margin_right, y + 30), color=c_border, fill=(0.97, 0.98, 1.0), width=0.5)
            current_page.insert_text((margin_left + 8, y + 12), "EXECUTIVE UNDERWRITER VERDICT:", fontsize=7.5, color=c_navy, fontname="helv")
            # Word-wrap verdict into 2 lines
            words = verdict.split()
            line1, line2 = "", ""
            for w in words:
                if len(line1 + " " + w) < 95:
                    line1 += " " + w
                else:
                    line2 += " " + w
            current_page.insert_text((margin_left + 8, y + 23), line1.strip(), fontsize=7.5, color=c_text_dark, fontname="helv")
            if line2:
                current_page.insert_text((margin_left + 8, y + 33), line2.strip(), fontsize=7.5, color=c_text_dark, fontname="helv")
            y += 38

        # PROS Box
        pros = summary.get("pros", [])
        if pros:
            current_page.insert_text((margin_left, y + 10), "🟢 PROS (Application Strengths):", fontsize=8.5, color=c_green, fontname="helv")
            y += 14
            for p in pros:
                check_page_break(20)
                pcrit = p.get("criticality", "MED")
                p_text = f"[{pcrit} CRITICALITY] {p.get('point', '')}"
                ev_text = f" Evidence: {p.get('evidence')}" if p.get("evidence") else ""
                full_p = (p_text + ev_text)[:115]
                current_page.insert_text((margin_left + 12, y + 10), f"•  {full_p}", fontsize=7.5, color=c_text_dark, fontname="helv")
                y += 13
            y += 6

        # CONS Box
        cons = summary.get("cons", [])
        if cons:
            check_page_break(24)
            current_page.insert_text((margin_left, y + 10), "🔴 CONS (Risk Factors & Vulnerabilities):", fontsize=8.5, color=c_red, fontname="helv")
            y += 14
            for c in cons:
                check_page_break(20)
                ccrit = c.get("criticality", "MED")
                c_text = f"[{ccrit} CRITICALITY] {c.get('point', '')}"
                ev_text = f" Evidence: {c.get('evidence')}" if c.get("evidence") else ""
                full_c = (c_text + ev_text)[:115]
                current_page.insert_text((margin_left + 12, y + 10), f"•  {full_c}", fontsize=7.5, color=c_text_dark, fontname="helv")
                y += 13

    # Add Footers to all pages
    total_pages = len(doc)
    for idx, page in enumerate(doc, start=1):
        page.draw_line(fitz.Point(margin_left, page_height - 24), fitz.Point(margin_right, page_height - 24), color=c_border, width=0.5)
        page.insert_text((margin_left, page_height - 14), "LOAN RANKING AGENT — DETERMINISTIC UNDERWRITING SYSTEM", fontsize=7, color=c_text_muted, fontname="helv")
        page.insert_text((margin_right - 65, page_height - 14), f"Page {idx} of {total_pages}", fontsize=7, color=c_text_muted, fontname="helv")

    doc.save(output_pdf_path)
    doc.close()
    print(f"✅ Generated report PDF: {output_pdf_path} ({total_pages} pages)")


if __name__ == "__main__":
    json_path = os.path.join(os.path.dirname(__file__), "..", "ranking_results.json")
    out_pdf = os.path.join(os.path.dirname(__file__), "..", "result.pdf")
    build_result_pdf(json_path, out_pdf)
