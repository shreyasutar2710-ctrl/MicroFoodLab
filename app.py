import io
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db, init_db
from comparison import evaluate_sample
from reports_pdf import build_report_pdf

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "microfoodlab-dev-secret-key"  # TODO: change before deployment


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def get_owned_sample(conn, sample_id):
    """Fetch a sample, scoped to the logged-in user. Returns None if not found/owned."""
    return conn.execute(
        "SELECT * FROM food_samples WHERE id = ? AND user_id = ?",
        (sample_id, session["user_id"]),
    ).fetchone()


# ----------------------------------------------------------------------
# Public pages
# ----------------------------------------------------------------------

@app.route("/")
def home():
    return render_template("welcome.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please fill all the fields.", "error")
            return redirect(url_for("register"))
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return redirect(url_for("register"))

        conn = get_db()
        existing_user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing_user:
            conn.close()
            flash("An account with this email already exists. Please login.", "error")
            return redirect(url_for("login"))

        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
        conn.close()
        flash("Account created successfully. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name:
            flash("Name cannot be empty.", "error")
            conn.close()
            return redirect(url_for("profile"))

        conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, session["user_id"]))
        session["user_name"] = name

        if new_password or current_password or confirm_password:
            if not check_password_hash(user["password_hash"], current_password):
                conn.commit()
                conn.close()
                flash("Name updated, but current password was incorrect — password not changed.", "error")
                return redirect(url_for("profile"))
            if len(new_password) < 6:
                conn.commit()
                conn.close()
                flash("Name updated, but new password must be at least 6 characters.", "error")
                return redirect(url_for("profile"))
            if new_password != confirm_password:
                conn.commit()
                conn.close()
                flash("Name updated, but new passwords did not match.", "error")
                return redirect(url_for("profile"))
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (generate_password_hash(new_password), session["user_id"]))
            conn.commit()
            conn.close()
            flash("Profile and password updated successfully.", "success")
            return redirect(url_for("profile"))

        conn.commit()
        conn.close()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    sample_count = conn.execute(
        "SELECT COUNT(*) AS c FROM food_samples WHERE user_id = ?", (session["user_id"],)
    ).fetchone()["c"]
    conn.close()
    return render_template("profile.html", user=user, sample_count=sample_count, active="profile")


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    uid = session["user_id"]

    samples = conn.execute("""
        SELECT fs.*,
               (SELECT r.status FROM reports r
                WHERE r.sample_id = fs.id
                ORDER BY r.generated_at DESC LIMIT 1) AS report_status
        FROM food_samples fs
        WHERE fs.user_id = ?
        ORDER BY fs.created_at DESC
    """, (uid,)).fetchall()
    conn.close()

    total = len(samples)
    safe = sum(1 for s in samples if s["report_status"] == "Safe")
    unsafe = sum(1 for s in samples if s["report_status"] == "Not Safe")
    pending = sum(1 for s in samples if not s["report_status"] or s["report_status"] not in ("Safe", "Marginal", "Not Safe"))

    stats = {"total": total, "safe": safe, "unsafe": unsafe, "pending": pending}
    marginal = sum(1 for s in samples if s["report_status"] == "Marginal")
    stats["marginal"] = marginal
    recent_samples = samples[:5]

    category_counts = {}
    for s in samples:
        cat = s["food_category"] or "Uncategorized"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    chart_data = {
        "status_labels": ["Safe", "Marginal", "Not Safe", "Pending"],
        "status_values": [safe, marginal, unsafe, pending],
        "category_labels": list(category_counts.keys()),
        "category_values": list(category_counts.values()),
    }

    return render_template("dashboard.html", user_name=session.get("user_name"),
                            stats=stats, recent_samples=recent_samples, active="dashboard",
                            chart_data=chart_data)


# ----------------------------------------------------------------------
# Food Sample Registration
# ----------------------------------------------------------------------

@app.route("/samples")
@login_required
def samples_list():
    conn = get_db()
    samples = conn.execute("""
        SELECT fs.*,
               (SELECT r.status FROM reports r
                WHERE r.sample_id = fs.id
                ORDER BY r.generated_at DESC LIMIT 1) AS report_status
        FROM food_samples fs
        WHERE fs.user_id = ?
        ORDER BY fs.created_at DESC
    """, (session["user_id"],)).fetchall()
    conn.close()
    return render_template("samples_list.html", samples=samples, active="samples")


@app.route("/samples/new", methods=["GET", "POST"])
@login_required
def sample_new():
    if request.method == "POST":
        food_name = request.form.get("food_name", "").strip()
        food_category = request.form.get("food_category", "").strip()

        if not food_name or not food_category:
            flash("Food name and category are required.", "error")
            return redirect(url_for("sample_new"))

        conn = get_db()
        cur = conn.execute(
            """INSERT INTO food_samples
               (sample_code, food_name, food_category, sample_type, collection_date,
                collection_location, batch_number, analyst_name, sample_description, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("TEMP", food_name, food_category,
             request.form.get("sample_type", "").strip() or None,
             request.form.get("collection_date", "").strip() or None,
             request.form.get("collection_location", "").strip() or None,
             request.form.get("batch_number", "").strip() or None,
             request.form.get("analyst_name", "").strip() or None,
             request.form.get("sample_description", "").strip() or None,
             session["user_id"]),
        )
        new_id = cur.lastrowid
        sample_code = f"MFL-{new_id:05d}"
        conn.execute("UPDATE food_samples SET sample_code = ? WHERE id = ?", (sample_code, new_id))
        conn.commit()
        conn.close()

        flash(f"Sample {sample_code} registered successfully.", "success")
        return redirect(url_for("sample_detail", sample_id=new_id))

    return render_template("sample_new.html", active="samples")


@app.route("/samples/<int:sample_id>")
@login_required
def sample_detail(sample_id):
    conn = get_db()
    sample = get_owned_sample(conn, sample_id)
    if not sample:
        conn.close()
        flash("Sample not found.", "error")
        return redirect(url_for("samples_list"))

    micro = conn.execute("SELECT * FROM microbiological_results WHERE sample_id = ?", (sample_id,)).fetchone()
    biochem = conn.execute("SELECT * FROM biochemical_results WHERE sample_id = ?", (sample_id,)).fetchone()
    conn.close()

    return render_template("sample_detail.html", sample=sample, micro=micro, biochem=biochem, active="samples")


# ----------------------------------------------------------------------
# Microbiological Analysis Module
# ----------------------------------------------------------------------

@app.route("/samples/<int:sample_id>/microbiology", methods=["GET", "POST"])
@login_required
def microbiology_form(sample_id):
    conn = get_db()
    sample = get_owned_sample(conn, sample_id)
    if not sample:
        conn.close()
        flash("Sample not found.", "error")
        return redirect(url_for("samples_list"))

    existing = conn.execute("SELECT * FROM microbiological_results WHERE sample_id = ?", (sample_id,)).fetchone()

    if request.method == "POST":
        def num(field):
            val = request.form.get(field, "").strip()
            return float(val) if val else None

        values = (
            request.form.get("spc_dilution", "").strip() or None,
            int(num("spc_colony_count")) if num("spc_colony_count") is not None else None,
            num("spc_cfu"),
            num("total_viable_cfu"),
            int(num("coliform_colony_count")) if num("coliform_colony_count") is not None else None,
            num("coliform_cfu"),
            int(num("yeast_mold_colony_count")) if num("yeast_mold_colony_count") is not None else None,
            num("yeast_mold_cfu"),
            request.form.get("salmonella_detected", "").strip() or None,
            request.form.get("ecoli_detected", "").strip() or None,
            request.form.get("staph_aureus_detected", "").strip() or None,
            request.form.get("other_pathogens", "").strip() or None,
        )

        if existing:
            conn.execute("""
                UPDATE microbiological_results SET
                    spc_dilution=?, spc_colony_count=?, spc_cfu=?, total_viable_cfu=?,
                    coliform_colony_count=?, coliform_cfu=?,
                    yeast_mold_colony_count=?, yeast_mold_cfu=?,
                    salmonella_detected=?, ecoli_detected=?, staph_aureus_detected=?, other_pathogens=?
                WHERE sample_id=?
            """, values + (sample_id,))
        else:
            conn.execute("""
                INSERT INTO microbiological_results
                    (spc_dilution, spc_colony_count, spc_cfu, total_viable_cfu, coliform_colony_count, coliform_cfu,
                     yeast_mold_colony_count, yeast_mold_cfu, salmonella_detected, ecoli_detected,
                     staph_aureus_detected, other_pathogens, sample_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, values + (sample_id,))
        conn.commit()
        conn.close()
        flash("Microbiological results saved.", "success")
        return redirect(url_for("sample_detail", sample_id=sample_id))

    conn.close()
    return render_template("microbiology_form.html", sample=sample, micro=existing, active="samples")


# ----------------------------------------------------------------------
# Biochemical Identification Module
# ----------------------------------------------------------------------

@app.route("/samples/<int:sample_id>/biochemistry", methods=["GET", "POST"])
@login_required
def biochemistry_form(sample_id):
    conn = get_db()
    sample = get_owned_sample(conn, sample_id)
    if not sample:
        conn.close()
        flash("Sample not found.", "error")
        return redirect(url_for("samples_list"))

    existing = conn.execute("SELECT * FROM biochemical_results WHERE sample_id = ?", (sample_id,)).fetchone()

    fields = ["gram_staining", "catalase_test", "oxidase_test", "indole_test", "methyl_red_test",
              "voges_proskauer_test", "citrate_test", "urease_test", "tsi_test", "motility_test",
              "nitrate_reduction_test", "additional_notes"]

    if request.method == "POST":
        values = tuple(request.form.get(f, "").strip() or None for f in fields)
        if existing:
            set_clause = ", ".join(f"{f}=?" for f in fields)
            conn.execute(f"UPDATE biochemical_results SET {set_clause} WHERE sample_id=?",
                         values + (sample_id,))
        else:
            cols = ", ".join(fields + ["sample_id"])
            placeholders = ", ".join(["?"] * (len(fields) + 1))
            conn.execute(f"INSERT INTO biochemical_results ({cols}) VALUES ({placeholders})",
                         values + (sample_id,))
        conn.commit()
        conn.close()
        flash("Biochemical results saved.", "success")
        return redirect(url_for("sample_detail", sample_id=sample_id))

    conn.close()
    return render_template("biochemistry_form.html", sample=sample, biochem=existing, active="samples")


# ----------------------------------------------------------------------
# FSSAI / Reference Standards
# ----------------------------------------------------------------------

@app.route("/standards")
@login_required
def standards_list():
    conn = get_db()
    standards = conn.execute(
        "SELECT * FROM standards ORDER BY food_category, parameter"
    ).fetchall()
    conn.close()
    return render_template("standards_list.html", standards=standards, active="standards")


@app.route("/standards/new", methods=["GET", "POST"])
@login_required
def standard_new():
    if request.method == "POST":
        food_category = request.form.get("food_category", "").strip()
        parameter = request.form.get("parameter", "").strip()
        satisfactory_limit = request.form.get("satisfactory_limit", "").strip()
        unsatisfactory_limit = request.form.get("unsatisfactory_limit", "").strip()

        if not food_category or not parameter or not satisfactory_limit or not unsatisfactory_limit:
            flash("Please fill all required fields.", "error")
            return redirect(url_for("standard_new"))

        conn = get_db()
        conn.execute("""
            INSERT INTO standards (food_category, parameter, satisfactory_limit, unsatisfactory_limit, unit, source)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (food_category, parameter, float(satisfactory_limit), float(unsatisfactory_limit),
              request.form.get("unit", "").strip() or None,
              request.form.get("source", "").strip() or None))
        conn.commit()
        conn.close()
        flash("Standard added.", "success")
        return redirect(url_for("standards_list"))

    return render_template("standard_new.html", active="standards")


@app.route("/standards/<int:standard_id>/delete", methods=["POST"])
@login_required
def standard_delete(standard_id):
    conn = get_db()
    conn.execute("DELETE FROM standards WHERE id = ?", (standard_id,))
    conn.commit()
    conn.close()
    flash("Standard deleted.", "success")
    return redirect(url_for("standards_list"))


# ----------------------------------------------------------------------
# Standard Comparison + Automated Decision Support + Reports
# ----------------------------------------------------------------------

def _compute_report(conn, sample):
    micro = conn.execute("SELECT * FROM microbiological_results WHERE sample_id = ?", (sample["id"],)).fetchone()
    biochem = conn.execute("SELECT * FROM biochemical_results WHERE sample_id = ?", (sample["id"],)).fetchone()
    standards_rows = conn.execute(
        "SELECT * FROM standards WHERE food_category = ?", (sample["food_category"],)
    ).fetchall()
    status, recommendation, details, chart_rows = evaluate_sample(micro, standards_rows)
    return micro, biochem, status, recommendation, details, chart_rows


@app.route("/samples/<int:sample_id>/report")
@login_required
def generate_report(sample_id):
    conn = get_db()
    sample = get_owned_sample(conn, sample_id)
    if not sample:
        conn.close()
        flash("Sample not found.", "error")
        return redirect(url_for("samples_list"))

    micro, biochem, status, recommendation, details, chart_rows = _compute_report(conn, sample)

    if micro:
        # Keep exactly one up-to-date report row per sample
        conn.execute("DELETE FROM reports WHERE sample_id = ?", (sample_id,))
        conn.execute("""
            INSERT INTO reports (sample_id, status, recommendation, generated_at)
            VALUES (?, ?, ?, ?)
        """, (sample_id, status, recommendation, datetime.now().isoformat(timespec="seconds")))
        conn.commit()

    conn.close()
    return render_template("report_view.html", sample=sample, micro=micro, biochem=biochem,
                            status=status, recommendation=recommendation, details=details,
                            chart_rows=chart_rows, active="reports")


@app.route("/samples/<int:sample_id>/report/pdf")
@login_required
def report_pdf(sample_id):
    conn = get_db()
    sample = get_owned_sample(conn, sample_id)
    if not sample:
        conn.close()
        flash("Sample not found.", "error")
        return redirect(url_for("samples_list"))

    micro, biochem, status, recommendation, details, chart_rows = _compute_report(conn, sample)
    conn.close()

    buffer = io.BytesIO()
    build_report_pdf(buffer, sample, micro, biochem, status, recommendation, details)
    buffer.seek(0)

    return send_file(
        buffer, mimetype="application/pdf", as_attachment=True,
        download_name=f"{sample['sample_code']}_report.pdf",
    )


@app.route("/reports")
@login_required
def reports_list():
    conn = get_db()
    reports = conn.execute("""
        SELECT r.*, fs.sample_code, fs.food_name
        FROM reports r
        JOIN food_samples fs ON fs.id = r.sample_id
        WHERE fs.user_id = ?
        ORDER BY r.generated_at DESC
    """, (session["user_id"],)).fetchall()
    conn.close()

    summary = {
        "total": len(reports),
        "safe": sum(1 for r in reports if r["status"] == "Safe"),
        "marginal": sum(1 for r in reports if r["status"] == "Marginal"),
        "unsafe": sum(1 for r in reports if r["status"] == "Not Safe"),
    }
    return render_template("reports_list.html", reports=reports, summary=summary, active="reports")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
