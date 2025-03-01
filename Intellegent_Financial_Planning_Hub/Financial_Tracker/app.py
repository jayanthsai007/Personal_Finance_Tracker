from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from markupsafe import escape
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import io
from datetime import datetime
import pandas as pd
import os
import json

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Serve the JSON file


@app.route('/dashboard_data.json')
@login_required
def dashboard_data():
    records = FinancialRecord.query.filter_by(user_id=current_user.id).all()
    budget = Budget.query.filter_by(
        user_id=current_user.id).order_by(Budget.id.desc()).first()

    if budget:
        budget_limit = budget.budget_limit
        category_budgets = budget.category_budgets
    else:
        budget_limit = 600  # Default to 600 if not set
        category_budgets = {}

    records_dict = [
        {
            'category': record.category,
            'amount': record.amount,
            'date': record.date.strftime('%Y-%m-%d')
        }
        for record in records
    ]

    category_spending = {}
    for record in records_dict:
        category = record['category']
        amount = record['amount']
        if category in category_spending:
            category_spending[category] += amount
        else:
            category_spending[category] = amount

    json_data = {
        'budget_limit': budget_limit,
        'total_spent': sum(record['amount'] for record in records_dict),
        'category_spending': category_spending,
        'category_budgets': category_budgets
    }

    return jsonify(json_data)

# User and FinancialRecord Models


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)


class FinancialRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(150), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=db.func.current_timestamp())


class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    budget_limit = db.Column(db.Float, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    category_budgets = db.Column(db.JSON, nullable=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
        else:
            new_user = User(username=username, password=password)
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful')
            return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')


@app.route('/dashboard')
@login_required
def dashboard():
    records = FinancialRecord.query.filter_by(user_id=current_user.id).all()
    budget = Budget.query.filter_by(
        user_id=current_user.id).order_by(Budget.id.desc()).first()

    if budget:
        budget_limit = budget.budget_limit
        category_budgets = budget.category_budgets
    else:
        budget_limit = 600  # Default to 600 if not set
        category_budgets = {}

    total_spent = sum(record.amount for record in records)

    # Calculate category-wise spending
    category_spending = {}
    for record in records:
        if record.category in category_spending:
            category_spending[record.category] += record.amount
        else:
            category_spending[record.category] = record.amount

    records_dict = [
        {
            'category': record.category,
            'amount': record.amount,
            'date': record.date.strftime('%Y-%m-%d')
        }
        for record in records
    ]

    return render_template('dashboard.html', user=current_user, records=records_dict, budget_limit=budget_limit, total_spent=total_spent, category_budgets=category_budgets, category_spending=category_spending)


@app.route('/transactions', methods=['GET', 'POST'])
@login_required
def transactions():
    # Get filter parameters from the request
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category_filter = request.args.get('category')

    # Query records based on filters
    query = FinancialRecord.query.filter_by(user_id=current_user.id)
    if start_date:
        query = query.filter(FinancialRecord.date >=
                             datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(FinancialRecord.date <=
                             datetime.strptime(end_date, '%Y-%m-%d'))
    if category_filter:
        query = query.filter_by(category=category_filter)

    records = query.all()

    # Extract unique categories from records
    categories = set(record.category for record in records)
    records_dict = [
        {
            'id': record.id,
            'category': record.category,
            'amount': record.amount,
            'date': record.date.strftime('%Y-%m-%d')
        }
        for record in records
    ]

    # Fetch the latest budget details
    budget = Budget.query.filter_by(
        user_id=current_user.id).order_by(Budget.id.desc()).first()
    if budget:
        budget_limit = budget.budget_limit
        category_budgets = budget.category_budgets
    else:
        budget_limit = None
        category_budgets = {}

    # Calculate total spending and average daily spending
    total_spending = sum(record['amount'] for record in records_dict)
    if records:
        start_date = min(record.date for record in records)
        end_date = max(record.date for record in records)
        days_spent = (end_date - start_date).days + \
            1  # Include both start and end date
        average_daily_spending = total_spending / days_spent
    else:
        average_daily_spending = 0

    # Calculate average daily spending for each category
    category_spending = {}
    for record in records_dict:
        category = record['category']
        amount = record['amount']
        if category in category_spending:
            category_spending[category] += amount
        else:
            category_spending[category] = amount

    category_average_daily_spending = {}
    for category, total in category_spending.items():
        category_average_daily_spending[category] = total / \
            days_spent if days_spent > 0 else 0

    return render_template('transactions.html', records=records_dict, categories=categories, budget_limit=budget_limit, category_budgets=category_budgets, average_daily_spending=average_daily_spending, category_average_daily_spending=category_average_daily_spending, total_spending=total_spending)


@app.route('/set_category_budget_limit', methods=['POST'])
@login_required
def set_category_budget_limit():
    category = request.form['category']
    category_budget = request.form['category_budget']

    # Fetch the latest budget details
    budget = Budget.query.filter_by(
        user_id=current_user.id).order_by(Budget.id.desc()).first()
    if budget:
        # Update the category-wise budget
        if budget.category_budgets is None:
            budget.category_budgets = {}
        budget.category_budgets[category] = float(category_budget)
        db.session.commit()
        flash('Category-wise budget limit set successfully.', 'success')
    else:
        flash('No overall budget set. Please set an overall budget first.', 'danger')

    return redirect(url_for('transactions'))


@app.route('/budget_alerts')
@login_required
def budget_alerts():
    budget = Budget.query.filter_by(
        user_id=current_user.id).order_by(Budget.id.desc()).first()
    alerts = []
    category_analysis = []

    if budget:
        total_spent = sum(record.amount for record in FinancialRecord.query.filter_by(
            user_id=current_user.id).all())
        total_percentage = (total_spent / budget.budget_limit *
                            100) if budget.budget_limit > 0 else 0

        if total_percentage >= 70:
            alert_type = 'alert-danger'
        elif total_percentage >= 40:
            alert_type = 'alert-warning'
        else:
            alert_type = 'alert-success'

        alerts.append({
            'type': alert_type,
            'message': f'You have spent {total_percentage:.2f}% of your budget!'
        })

        for category, limit in budget.category_budgets.items():
            limit = int(limit)  # Convert limit to integer
            category_spent = sum(record.amount for record in FinancialRecord.query.filter_by(
                user_id=current_user.id, category=category).all())
            percentage = (category_spent / limit * 100) if limit > 0 else 0
            category_analysis.append({
                'category': category,
                'spent': category_spent,
                'budget': limit,
                'percentage': round(percentage, 2)
            })
            if percentage >= 70:
                alert_type = 'alert-danger'
            elif percentage >= 40:
                alert_type = 'alert-warning'
            else:
                alert_type = 'alert-success'

            alerts.append({
                'type': alert_type,
                'message': f'You have spent {percentage:.2f}% of your budget for {category}!'
            })
    else:
        alerts.append({
            'type': 'alert-success',
            'message': 'No budget set.'
        })

    return render_template('alerts.html', alerts=alerts, category_analysis=category_analysis)


@app.route('/budget_data.json')
@login_required
def budget_data():
    budget = Budget.query.filter_by(
        user_id=current_user.id).order_by(Budget.id.desc()).first()
    if not budget:
        return jsonify({
            'total_spent': 0,
            'budget_limit': 0,
            'category_analysis': []
        })

    total_spent = sum(record.amount for record in FinancialRecord.query.filter_by(
        user_id=current_user.id).all())
    category_analysis = []
    for category, limit in budget.category_budgets.items():
        category_spent = sum(record.amount for record in FinancialRecord.query.filter_by(
            user_id=current_user.id, category=category).all())
        percentage = (category_spent / int(limit) *
                      100) if int(limit) > 0 else 0
        category_analysis.append({
            'category': category,
            'spent': category_spent,
            'budget': int(limit),
            'percentage': round(percentage, 2)
        })

    return jsonify({
        'total_spent': total_spent,
        'budget_limit': budget.budget_limit,
        'category_analysis': category_analysis
    })


@app.route('/recent_transactions.json')
@login_required
def recent_transactions():
    recent_records = FinancialRecord.query.filter_by(
        user_id=current_user.id).order_by(FinancialRecord.date.desc()).limit(3).all()
    recent_transactions = [
        {
            'category': record.category,
            'amount': record.amount,
            'date': record.date.strftime('%Y-%m-%d')
        }
        for record in recent_records
    ]
    return jsonify(recent_transactions)


@app.route('/add_record', methods=['POST'])
@login_required
def add_record():
    category = request.form['category']
    amount = request.form['amount']
    date = request.form['date']
    new_record = FinancialRecord(
        user_id=current_user.id,
        category=category,
        amount=amount,
        date=datetime.strptime(date, '%Y-%m-%d')
    )
    db.session.add(new_record)
    db.session.commit()
    flash('Record added successfully')
    return redirect(url_for('transactions'))


@app.route('/edit_record/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_record(record_id):
    record = FinancialRecord.query.get_or_404(record_id)
    if request.method == 'POST':
        record.amount = request.form['amount']
        record.category = request.form['category']
        db.session.commit()
        flash('Record updated successfully')
        return redirect(url_for('transactions'))

    # Fetch distinct categories from the FinancialRecord table
    categories = db.session.query(FinancialRecord.category).distinct().all()
    categories = [category[0] for category in categories]

    return render_template('edit_record.html', record=record, categories=categories)


@app.route('/delete_record/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    record = FinancialRecord.query.get_or_404(record_id)
    db.session.delete(record)
    db.session.commit()
    flash('Record deleted successfully')
    return redirect(url_for('transactions'))


@app.route('/export_pdf')
@login_required
def export_pdf():
    records = FinancialRecord.query.filter_by(user_id=current_user.id).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    styles = getSampleStyleSheet()
    title = Paragraph("Transaction Details", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))

    data = [["Date", "Category", "Amount"]]
    for record in records:
        data.append([record.date.strftime("%Y-%m-%d"),
                    record.category, f"{record.amount:.2f}"])

    table = Table(data, colWidths=[100, 300, 100])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='transactions.pdf', mimetype='application/pdf')


@app.route('/export_excel')
@login_required
def export_excel():
    # Fetch transaction records
    records = FinancialRecord.query.filter_by(user_id=current_user.id).all()
    records_dict = [
        {
            'Date': record.date.strftime('%Y-%m-%d'),
            'Category': record.category,
            'Amount': record.amount
        }
        for record in records
    ]

    # Fetch budget details
    budget = Budget.query.filter_by(
        user_id=current_user.id).order_by(Budget.id.desc()).first()
    if budget:
        budget_limit = budget.budget_limit
        category_budgets = budget.category_budgets
    else:
        budget_limit = 600  # Default to 600 if not set
        category_budgets = {}

    # Calculate total spent
    total_spent = sum(record['Amount'] for record in records_dict)

    # Create a DataFrame for transactions
    df_transactions = pd.DataFrame(records_dict)

    # Create a DataFrame for overall budget details
    budget_data = {
        'Overall Budget Limit': [budget_limit],
        'Total Spent': [total_spent]
    }
    df_budget = pd.DataFrame(budget_data)

    # Create a DataFrame for category-wise budget details
    category_spending = {}
    for record in records_dict:
        category = record['Category']
        amount = record['Amount']
        if category in category_spending:
            category_spending[category] += amount
        else:
            category_spending[category] = amount

    category_budget_data = []
    for category, limit in category_budgets.items():
        spent = category_spending.get(category, 0)
        category_budget_data.append({
            'Category': category,
            'Budget Limit': limit,
            'Spent': spent,
            'Remaining': limit - spent
        })
    df_category_budget = pd.DataFrame(category_budget_data)

    # Create a BytesIO buffer to save the Excel file
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_transactions.to_excel(
            writer, sheet_name='Transactions', index=False)
        df_budget.to_excel(writer, sheet_name='Overall Budget', index=False)
        df_category_budget.to_excel(
            writer, sheet_name='Category-wise Budget', index=False)

    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='budget_details.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/set_budget_limit', methods=['POST'])
@login_required
def set_budget_limit():
    budget_limit = int(request.form['budget_limit'])
    start_date = request.form['start_date']
    end_date = request.form['end_date']
    category_budgets = {key.split('_')[2]: int(
        value) for key, value in request.form.items() if key.startswith('category_budget_')}

    # Update or create the budget
    budget = Budget.query.filter_by(
        user_id=current_user.id).order_by(Budget.id.desc()).first()
    if budget:
        budget.budget_limit = budget_limit
        budget.start_date = datetime.strptime(start_date, '%Y-%m-%d')
        budget.end_date = datetime.strptime(end_date, '%Y-%m-%d')
        budget.category_budgets = category_budgets
    else:
        budget = Budget(
            user_id=current_user.id,
            budget_limit=budget_limit,
            start_date=datetime.strptime(start_date, '%Y-%m-%d'),
            end_date=datetime.strptime(end_date, '%Y-%m-%d'),
            category_budgets=category_budgets
        )
        db.session.add(budget)
    db.session.commit()

    notification = "Budget limit set successfully!"

    # Recalculate the total spending and other details
    records = FinancialRecord.query.filter_by(user_id=current_user.id).all()
    categories = set(record.category for record in records)
    records_dict = [
        {
            'id': record.id,
            'category': record.category,
            'amount': record.amount,
            'date': record.date.strftime('%Y-%m-%d')
        }
        for record in records
    ]

    total_spending = sum(record['amount'] for record in records_dict)
    if records:
        start_date = min(record.date for record in records)
        end_date = max(record.date for record in records)
        days_spent = (end_date - start_date).days + 1
        average_daily_spending = total_spending / days_spent
    else:
        average_daily_spending = 0

    category_spending = {}
    for record in records_dict:
        category = record['category']
        amount = record['amount']
        if category in category_spending:
            category_spending[category] += amount
        else:
            category_spending[category] = amount

    category_average_daily_spending = {}
    for category, total in category_spending.items():
        category_average_daily_spending[category] = total / \
            days_spent if days_spent > 0 else 0

    return render_template('transactions.html', records=records_dict, categories=categories, budget_limit=budget_limit, category_budgets=category_budgets, average_daily_spending=average_daily_spending, category_average_daily_spending=category_average_daily_spending, total_spending=total_spending, notification=notification)


@app.route('/load_dataset')
@login_required
def load_dataset():
    dataset_path = 'path/to/transactions.csv'
    df = pd.read_csv(dataset_path)

    for index, row in df.iterrows():
        new_record = FinancialRecord(
            user_id=current_user.id,
            category=row['category'],
            amount=row['amount'],
            date=datetime.strptime(row['date'], '%Y-%m-%d')
        )
        db.session.add(new_record)

    db.session.commit()
    flash('Dataset loaded successfully')
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
