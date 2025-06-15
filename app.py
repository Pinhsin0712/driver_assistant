from flask import Flask, render_template, request
from datetime import datetime, timedelta
from flask import redirect, url_for
import mysql.connector

app = Flask(__name__)

db_config = {
    'host': '104.199.167.226',
    'user': 'pin',
    'password': 'S10490032',
    'database': 'myDB'
}
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/add', methods=['GET', 'POST'])
def scheduler():
    if request.method == 'POST':
        data = request.form
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        # 查找可用司機
        cursor.execute("SELECT * FROM drivers")
        drivers = cursor.fetchall()

        if not drivers:
            return render_template('scheduler.html', result=None, error="無可用司機")

        # 查詢每位司機目前的訂單數
        cursor.execute("""
            SELECT assigned_driver_name, COUNT(*) as order_count
            FROM schedule_results
            GROUP BY assigned_driver_name
        """)
        orders = cursor.fetchall()
        order_count = {o['assigned_driver_name']: o['order_count'] for o in orders}

       # 新增：過濾掉當天有與新訂單時間小於2小時的司機
        schedule_date = data['schedule_date']
        pickup_time = data['pickup_time']
        new_dt = datetime.strptime(f"{schedule_date} {pickup_time}", "%Y-%m-%d %H:%M")

        eligible_drivers = []
        for driver in drivers:
            cursor.execute("""
                SELECT pickup_time FROM schedule_results
                WHERE assigned_driver_name=%s AND schedule_date=%s
            """, (driver['name'], schedule_date))
            times = cursor.fetchall()
            conflict = False
            for t in times:
                exist_dt = datetime.strptime(f"{schedule_date} {t['pickup_time']}", "%Y-%m-%d %H:%M")
                if abs((exist_dt - new_dt).total_seconds()) < 2 * 3600:
                    conflict = True
                    break
            if not conflict:
                eligible_drivers.append(driver)

        if not eligible_drivers:
            return render_template('scheduler.html', result=None, error="無符合時間間隔的司機")

        # 在 eligible_drivers 中選訂單數最少的
        min_count = None
        selected_driver = None
        for driver in eligible_drivers:
            count = order_count.get(driver['name'], 0)
            if min_count is None or count < min_count:
                min_count = count
                selected_driver = driver

        driver = selected_driver

        # 將排班資訊寫入 schedule_results 資料表
        cursor.execute("""
            INSERT INTO schedule_results (
                schedule_date, passenger_name, passenger_phone, 
                pickup_time, pickup_location, dropoff_location,
                luggage_count, flight_number, terminal,
                assigned_driver_name, note
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data['schedule_date'],
            data['passenger_name'],
            data['passenger_phone'],
            data['pickup_time'],
            data['pickup_location'],
            data['dropoff_location'],
            int(data['luggage_count']) if data['luggage_count'] else 0,
            data['flight_number'],
            data['terminal'],
            driver['name'],
            data['note']
        ))

        conn.commit()
        cursor.close()
        conn.close()

        result = {
            'driver_name': driver['name'],
            'schedule_date': data['schedule_date'],
            'pickup_time': data['pickup_time'],
            'pickup_location': data['pickup_location'],
            'dropoff_location': data['dropoff_location'],
            'passenger_name': data['passenger_name']
        }
        return render_template('scheduler.html', result=result)
    return render_template('scheduler.html')

#查看訂單
@app.route('/orders')
def view_orders():
    year = request.args.get('year')
    month = request.args.get('month')
    driver = request.args.get('driver')

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)

    # 取得所有年份、月份、司機選單
    cursor.execute("SELECT DISTINCT YEAR(schedule_date) as y FROM schedule_results ORDER BY y DESC")
    years = [str(row['y']) for row in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT MONTH(schedule_date) as m FROM schedule_results ORDER BY m")
    months = [str(row['m']).zfill(2) for row in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT assigned_driver_name as d FROM schedule_results ORDER BY d")
    drivers = [row['d'] for row in cursor.fetchall()]

    # 組合查詢條件
    query = "SELECT * FROM schedule_results WHERE 1=1"
    params = []
    if year:
        query += " AND YEAR(schedule_date) = %s"
        params.append(year)
    if month:
        query += " AND MONTH(schedule_date) = %s"
        params.append(month)
    if driver:
        query += " AND assigned_driver_name = %s"
        params.append(driver)
    query += " ORDER BY schedule_date DESC, pickup_time DESC"

    cursor.execute(query, params)
    orders = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template(
        'orders.html',
        orders=orders,
        years=years,
        months=months,
        drivers=drivers,
        selected_year=year,
        selected_month=month,
        selected_driver=driver
    )
#*******************************
# 刪除訂單
@app.route('/delete_orders', methods=['GET', 'POST'])
def delete_orders():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)

    # 篩選條件
    year = request.args.get('year')
    month = request.args.get('month')
    day = request.args.get('day')

    # 取得所有年份、月份、日期
    cursor.execute("SELECT DISTINCT YEAR(schedule_date) as y FROM schedule_results ORDER BY y DESC")
    years = [str(row['y']) for row in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT MONTH(schedule_date) as m FROM schedule_results ORDER BY m")
    months = [str(row['m']).zfill(2) for row in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT DAY(schedule_date) as d FROM schedule_results ORDER BY d")
    days = [str(row['d']).zfill(2) for row in cursor.fetchall()]

    # 查詢訂單
    query = "SELECT * FROM schedule_results WHERE 1=1"
    params = []
    if year:
        query += " AND YEAR(schedule_date) = %s"
        params.append(year)
    if month:
        query += " AND MONTH(schedule_date) = %s"
        params.append(month)
    if day:
        query += " AND DAY(schedule_date) = %s"
        params.append(day)
    query += " ORDER BY schedule_date DESC, pickup_time DESC"
    cursor.execute(query, params)
    orders = cursor.fetchall()

    # 處理刪除
    if request.method == 'POST':
        ids = request.form.getlist('delete_ids')
        if ids:
            format_strings = ','.join(['%s'] * len(ids))
            cursor.execute(f"DELETE FROM schedule_results WHERE id IN ({format_strings})", ids)
            conn.commit()
            return redirect(url_for('delete_orders', year=year, month=month, day=day))

    cursor.close()
    conn.close()
    return render_template(
        'delete_orders.html',
        orders=orders,
        years=years,
        months=months,
        days=days,
        selected_year=year,
        selected_month=month,
        selected_day=day
    )

# 編輯訂單列表
@app.route('/edit_orders', methods=['GET'])
def edit_orders():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)

    year = request.args.get('year')
    month = request.args.get('month')
    day = request.args.get('day')

    cursor.execute("SELECT DISTINCT YEAR(schedule_date) as y FROM schedule_results ORDER BY y DESC")
    years = [str(row['y']) for row in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT MONTH(schedule_date) as m FROM schedule_results ORDER BY m")
    months = [str(row['m']).zfill(2) for row in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT DAY(schedule_date) as d FROM schedule_results ORDER BY d")
    days = [str(row['d']).zfill(2) for row in cursor.fetchall()]

    query = "SELECT * FROM schedule_results WHERE 1=1"
    params = []
    if year:
        query += " AND YEAR(schedule_date) = %s"
        params.append(year)
    if month:
        query += " AND MONTH(schedule_date) = %s"
        params.append(month)
    if day:
        query += " AND DAY(schedule_date) = %s"
        params.append(day)
    query += " ORDER BY schedule_date DESC, pickup_time DESC"
    cursor.execute(query, params)
    orders = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template(
        'edit_orders.html',
        orders=orders,
        years=years,
        months=months,
        days=days,
        selected_year=year,
        selected_month=month,
        selected_day=day
    )

# 單筆編輯
@app.route('/edit_order/<int:order_id>', methods=['GET', 'POST'])
def edit_order(order_id):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)

    # 取得所有司機
    cursor.execute("SELECT name FROM drivers")
    drivers = [row['name'] for row in cursor.fetchall()]

    # 取得訂單
    cursor.execute("SELECT * FROM schedule_results WHERE id=%s", (order_id,))
    order = cursor.fetchone()

    if not order:
        cursor.close()
        conn.close()
        return "找不到訂單", 404

    if request.method == 'POST':
        data = request.form
        cursor.execute("""
            UPDATE schedule_results SET
                schedule_date=%s,
                passenger_name=%s,
                passenger_phone=%s,
                pickup_time=%s,
                pickup_location=%s,
                dropoff_location=%s,
                luggage_count=%s,
                flight_number=%s,
                terminal=%s,
                assigned_driver_name=%s,
                note=%s
            WHERE id=%s
        """, (
            data['schedule_date'],
            data['passenger_name'],
            data['passenger_phone'],
            data['pickup_time'],
            data['pickup_location'],
            data['dropoff_location'],
            int(data['luggage_count']) if data['luggage_count'] else 0,
            data['flight_number'],
            data['terminal'],
            data['assigned_driver_name'],
            data['note'],
            order_id
        ))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('edit_orders'))

    cursor.close()
    conn.close()
    return render_template('edit_order.html', order=order, drivers=drivers)




if __name__ == '__main__':
    app.run(debug=True)
