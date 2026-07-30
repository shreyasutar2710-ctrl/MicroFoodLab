"""
Standard Comparison Module + Automated Decision Support System.

Uses the ICMSF 3-class sampling-plan interpretation (the same approach used
by FSSAI / Codex):
    value <= m           -> Satisfactory
    m  <  value <= M      -> Marginal / Borderline
    value  >  M           -> Unsatisfactory (Not Safe)

Presence of a tested pathogen always forces a "Not Safe" verdict, regardless
of the CFU-based parameters, since food safety practice treats pathogen
presence in a ready-to-eat sample as zero-tolerance.
"""

SEVERITY = {"Safe": 0, "Marginal": 1, "Not Safe": 2}


def evaluate_sample(micro_row, standards_rows):
    """
    micro_row: sqlite3.Row from microbiological_results (or None)
    standards_rows: list of sqlite3.Row from standards, pre-filtered by food_category

    Returns: (status:str, recommendation:str, details:list[str])
    """
    if not micro_row:
        return "Pending", "Microbiological results have not been entered yet.", [], []

    pathogen_fields = {
        "Salmonella spp.": micro_row["salmonella_detected"],
        "E. coli": micro_row["ecoli_detected"],
        "Staphylococcus aureus": micro_row["staph_aureus_detected"],
    }
    detected = [name for name, val in pathogen_fields.items() if val == "Detected"]
    if detected:
        return (
            "Not Safe",
            f"Pathogen(s) detected: {', '.join(detected)}. Presence of a pathogen in the "
            f"sample makes it unfit for consumption regardless of other microbial counts.",
            [f"{name}: Detected" for name in detected],
            [],
        )

    std_map = {s["parameter"]: s for s in standards_rows}

    checks = [
        ("SPC", micro_row["spc_cfu"], "Standard Plate Count"),
        ("Coliform", micro_row["coliform_cfu"], "Coliform Count"),
        ("Yeast_Mold", micro_row["yeast_mold_cfu"], "Yeast & Mold Count"),
    ]

    details = []
    chart_rows = []
    worst = "Safe"
    matched_any = False

    for key, value, label in checks:
        std = std_map.get(key)
        if std is None or value is None:
            continue
        matched_any = True
        m = std["satisfactory_limit"]
        big_m = std["unsatisfactory_limit"]
        if value <= m:
            verdict = "Safe"
        elif value <= big_m:
            verdict = "Marginal"
        else:
            verdict = "Not Safe"
        unit = std["unit"] or ""
        details.append(f"{label}: {value} {unit} (limit m={m}, M={big_m}) → {verdict}")
        chart_rows.append({"label": label, "value": value, "m": m, "M": big_m, "unit": unit, "verdict": verdict})
        if SEVERITY[verdict] > SEVERITY[worst]:
            worst = verdict

    if not matched_any:
        return (
            "Marginal",
            "No matching reference standards were found for this food category. "
            "Add the relevant limits under FSSAI Standards to get a complete verdict.",
            details,
            chart_rows,
        )

    recommendation = {
        "Safe": "All tested microbiological parameters are within satisfactory limits and "
                "no pathogens were detected. The sample is considered safe for consumption.",
        "Marginal": "One or more parameters fall between the satisfactory and unsatisfactory "
                    "limits. Re-testing and a review of handling/storage practices is advised.",
        "Not Safe": "One or more parameters exceed the unsatisfactory limit. The sample is "
                    "not safe for consumption.",
    }[worst]

    return worst, recommendation, details, chart_rows
