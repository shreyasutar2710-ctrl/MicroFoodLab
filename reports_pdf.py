import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

STATUS_COLORS = {
    "Safe": colors.HexColor("#2e7d32"),
    "Marginal": colors.HexColor("#f9a825"),
    "Not Safe": colors.HexColor("#c62828"),
    "Pending": colors.HexColor("#607d8b"),
}


def build_report_pdf(output_path, sample, micro, biochem, status, recommendation, details):
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm,
        leftMargin=18 * mm, rightMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleX", parent=styles["Title"], textColor=colors.HexColor("#0d47a1"))
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=colors.HexColor("#0d47a1"), spaceBefore=12)
    normal = styles["Normal"]

    story = []
    story.append(Paragraph("MicroFoodLab", title_style))
    story.append(Paragraph("Food Microbiology Laboratory Management System", normal))
    story.append(Paragraph("Laboratory Analysis Report", h2))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#0d47a1")))
    story.append(Spacer(1, 10))

    # Sample info table
    info_rows = [
        ["Sample ID", sample["sample_code"], "Food Name", sample["food_name"]],
        ["Food Category", sample["food_category"] or "-", "Sample Type", sample["sample_type"] or "-"],
        ["Collection Date", sample["collection_date"] or "-", "Collection Location", sample["collection_location"] or "-"],
        ["Batch Number", sample["batch_number"] or "-", "Analyst", sample["analyst_name"] or "-"],
    ]
    info_table = Table(info_rows, colWidths=[35 * mm, 55 * mm, 35 * mm, 55 * mm])
    info_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dbe2e8")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f7fb")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f4f7fb")),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 16))

    # Microbiological results
    story.append(Paragraph("Microbiological Results", h2))
    if micro:
        micro_rows = [
            ["Parameter", "Result"],
            ["Standard Plate Count (SPC)", f"{micro['spc_cfu']} CFU/g" if micro["spc_cfu"] is not None else "-"],
            ["Total Viable Count (TVC)", f"{micro['total_viable_cfu']} CFU/g" if micro["total_viable_cfu"] is not None else "-"],
            ["Coliform Count", f"{micro['coliform_cfu']} CFU/g" if micro["coliform_cfu"] is not None else "-"],
            ["Yeast & Mold Count", f"{micro['yeast_mold_cfu']} CFU/g" if micro["yeast_mold_cfu"] is not None else "-"],
            ["Salmonella spp.", micro["salmonella_detected"] or "Not Tested"],
            ["E. coli", micro["ecoli_detected"] or "Not Tested"],
            ["Staphylococcus aureus", micro["staph_aureus_detected"] or "Not Tested"],
        ]
        t = Table(micro_rows, colWidths=[85 * mm, 85 * mm])
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d47a1")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dbe2e8")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("Not entered.", normal))
    story.append(Spacer(1, 16))

    # Biochemical results
    story.append(Paragraph("Biochemical Identification", h2))
    if biochem:
        bio_pairs = [
            ("Gram Staining", biochem["gram_staining"]), ("Catalase", biochem["catalase_test"]),
            ("Oxidase", biochem["oxidase_test"]), ("Indole", biochem["indole_test"]),
            ("Methyl Red", biochem["methyl_red_test"]), ("Voges-Proskauer", biochem["voges_proskauer_test"]),
            ("Citrate", biochem["citrate_test"]), ("Urease", biochem["urease_test"]),
            ("TSI", biochem["tsi_test"]), ("Motility", biochem["motility_test"]),
            ("Nitrate Reduction", biochem["nitrate_reduction_test"]),
        ]
        bio_rows = [["Test", "Result"]] + [[k, v or "Not Tested"] for k, v in bio_pairs]
        t2 = Table(bio_rows, colWidths=[85 * mm, 85 * mm])
        t2.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d47a1")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dbe2e8")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t2)
    else:
        story.append(Paragraph("Not entered.", normal))
    story.append(Spacer(1, 16))

    # Standard comparison
    story.append(Paragraph("Standard Comparison", h2))
    if details:
        for d in details:
            story.append(Paragraph("• " + d, normal))
    else:
        story.append(Paragraph("No comparison details available.", normal))
    story.append(Spacer(1, 14))

    # Final verdict
    status_style = ParagraphStyle(
        "Status", parent=styles["Heading1"],
        textColor=STATUS_COLORS.get(status, colors.black),
        alignment=1,
    )
    story.append(HRFlowable(width="100%", color=colors.HexColor("#dbe2e8")))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Final Verdict: {status}", status_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph(recommendation, normal))
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"Analyst: {sample['analyst_name'] or '-'}", normal))

    doc.build(story)
    return output_path
