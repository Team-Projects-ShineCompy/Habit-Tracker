import json
from datetime import date, timedelta, datetime

from database import get_db, get_user_habits


# ==========================================
# SHARED HELPER
# ==========================================

def is_scheduled(habit, check_date):
    """habit တစ်ခုက ရွေးထားတဲ့ check_date (date object) မှာ scheduled ရှိမရှိ ပြန်ပေး (True/False)."""
    year = check_date.year
    month = check_date.month
    weekday = check_date.isoweekday()  # 1=Mon ... 7=Sun
    week_num = (check_date.day - 1) // 7 + 1

    pattern = habit.get('repeat_pattern')
    if not pattern:
        return False
    if isinstance(pattern, str):
        try:
            pattern = json.loads(pattern)
        except Exception:
            return False

    rtype = habit.get('repeat_type', pattern.get('type', ''))

    if rtype == 'weekly':
        years = pattern.get('years')
        months = pattern.get('months', list(range(1, 13)))
        weekdays = pattern.get('weekdays', list(range(1, 8)))
        year_matches = not years or year in years
        return year_matches and (not months or month in months) and (not weekdays or weekday in weekdays)

    elif rtype == 'custom':
        dates = pattern.get('dates')
        if dates:
            return check_date.isoformat() in dates
        week_key = f'week{week_num}'
        week_schedules = pattern.get('weeks', {}).get(week_key, [])
        return any(entry.get('weekday') == weekday for entry in week_schedules)

    return False


def _get_logs_map(user_id, habits):
    """habit_id (int) -> {date_str: status} nested dict ကို DB ကနေ တစ်ခါတည်းဆွဲထုတ်ပေးတဲ့ internal helper."""
    conn, db_type = get_db()
    cursor = conn.cursor()
    habit_ids = [h['id'] for h in habits]
    logs_map = {}

    if habit_ids:
        if db_type == "postgres":
            cursor.execute(
                "SELECT habit_id, log_date::text as log_date, status, completed "
                "FROM habit_log WHERE habit_id = ANY(%s);",
                (habit_ids,)
            )
            rows = cursor.fetchall()
        else:
            placeholders = ','.join(['?'] * len(habit_ids))
            cursor.execute(
                f"SELECT habit_id, log_date, status, completed FROM habit_log "
                f"WHERE habit_id IN ({placeholders});",
                habit_ids
            )
            rows = [dict(r) for r in cursor.fetchall()]

        for r in rows:
            h_id = int(r['habit_id'])
            d_str = str(r['log_date'])
            st = r.get('status') or ('complete' if r.get('completed') else 'ready')
            logs_map.setdefault(h_id, {})[d_str] = st

    cursor.close()
    conn.close()
    return logs_map


def _is_completed(logs_map, habit_id, date_str):
    st = logs_map.get(int(habit_id), {}).get(date_str)
    return st in ('complete', 'done')


def get_user_statistics(user_id):
    """Streak (current/longest) + 30-day overall completion rate."""
    habits = get_user_habits(user_id)
    if not habits:
        return {
            "completion_rate": 0,
            "current_streak": 0,
            "longest_streak": 0,
            "total_completed": 0
        }

    today = date.today()
    logs_map = _get_logs_map(user_id, habits)

    # --- Completion Rate: past 30 days ---
    total_scheduled = 0
    total_completed = 0
    for i in range(30):
        check_date = today - timedelta(days=i)
        date_str = check_date.isoformat()
        for habit in habits:
            if is_scheduled(habit, check_date):
                total_scheduled += 1
                if _is_completed(logs_map, habit['id'], date_str):
                    total_completed += 1

    completion_rate = round((total_completed / total_scheduled) * 100) if total_scheduled > 0 else 0

    # --- Streak Calculation: past 90 days ---
    current_streak = 0
    longest_streak = 0
    temp_streak = 0
    streak_broken = False

    for i in range(90):
        check_date = today - timedelta(days=i)
        date_str = check_date.isoformat()
        scheduled_today = [h for h in habits if is_scheduled(h, check_date)]
        if not scheduled_today:
            continue  # habit ဘာမှ schedule မရှိတဲ့ရက် — streak ကို မဖြတ်
        all_done = all(_is_completed(logs_map, h['id'], date_str) for h in scheduled_today)
        if all_done:
            temp_streak += 1
            if not streak_broken:
                current_streak += 1
        else:
            streak_broken = True
            if temp_streak > longest_streak:
                longest_streak = temp_streak
            temp_streak = 0

    if temp_streak > longest_streak:
        longest_streak = temp_streak

    return {
        "completion_rate": completion_rate,
        "current_streak": current_streak,
        "longest_streak": max(longest_streak, current_streak),
        "total_completed": total_completed
    }



def get_daily_completion_rates(user_id, days=30):
    """
    တစ်လစာ ရက်တစ်ရက်ချင်းစီရဲ့ completion % ကို dict အနေနဲ့ ပြန်ပေး

    Return e.g.:
        {
            "2026-08-01": 66.6,
            "2026-08-02": 100.0,
            "2026-08-03": 50.0,
        }
    """
    habits = get_user_habits(user_id)
    if not habits or days <= 0:
        return {}

    logs_map = _get_logs_map(user_id, habits)
    today = date.today()
    daily_rates = {}

    for i in range(days):
        check_date = today - timedelta(days=i)
        date_str = check_date.isoformat()
        scheduled_today = [h for h in habits if is_scheduled(h, check_date)]
        if not scheduled_today:
            continue

        completed_count = sum(
            1 for h in scheduled_today
            if _is_completed(logs_map, h['id'], date_str)
        )
        daily_rates[date_str] = round((completed_count / len(scheduled_today)) * 100, 1)

    return daily_rates



def get_per_habit_breakdown(user_id, days=30):
    """
    Habit တစ်ခုချင်းစီအတွက် — habit_name, total_time_min (complete ဖြစ်ခဲ့တဲ့ session တွေရဲ့
    အချိန်ပေါင်း), completion_rate ကို ပြန်ပေး.

    Return e.g.:
        {
            "Reading": {"total_time_min": 90.0, "completion_rate": 66.7},
            "Meditation": {"total_time_min": 45.0, "completion_rate": 50.0},
        }
    """
    habits = get_user_habits(user_id)
    if not habits or days <= 0:
        return {}

    logs_map = _get_logs_map(user_id, habits)
    today = date.today()
    result = {}

    for h in habits:
        try:
            duration_min = (
                datetime.strptime(h['end_time'], "%H:%M") -
                datetime.strptime(h['start_time'], "%H:%M")
            ).total_seconds() / 60
        except (ValueError, TypeError):
            duration_min = 0

        scheduled_count = 0
        completed_count = 0

        for i in range(days):
            check_date = today - timedelta(days=i)
            if is_scheduled(h, check_date):
                scheduled_count += 1
                if _is_completed(logs_map, h['id'], check_date.isoformat()):
                    completed_count += 1

        result[h['habit_name']] = {
            "total_time_min": round(duration_min * completed_count, 1),
            "completion_rate": round((completed_count / scheduled_count) * 100, 1) if scheduled_count else 0
        }

    return result

def get_daily_completion_rates_for_month(user_id, year, month):
    """
    Given calendar month (year, month) အတွက် ရက်တစ်ရက်ချင်းစီရဲ့ completion % ကို ပြန်ပေး.
    Habit တစ်ခုမှ schedule မရှိတဲ့ရက်ကို skip လုပ်တယ်.
    """
    habits = get_user_habits(user_id)
    if not habits:
        return {}

    logs_map = _get_logs_map(user_id, habits)

    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    days_in_month = (next_month_first - date(year, month, 1)).days

    daily_rates = {}
    for day in range(1, days_in_month + 1):
        check_date = date(year, month, day)
        date_str = check_date.isoformat()
        scheduled_today = [h for h in habits if is_scheduled(h, check_date)]
        if not scheduled_today:
            continue

        completed_count = sum(
            1 for h in scheduled_today
            if _is_completed(logs_map, h['id'], date_str)
        )
        daily_rates[date_str] = round((completed_count / len(scheduled_today)) * 100, 1)

    return daily_rates


def get_per_habit_breakdown_for_month(user_id, year, month):
    """Given calendar month အတွက် habit တစ်ခုချင်းစီရဲ့ total_time_min + completion_rate."""
    habits = get_user_habits(user_id)
    if not habits:
        return {}

    logs_map = _get_logs_map(user_id, habits)

    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    days_in_month = (next_month_first - date(year, month, 1)).days

    result = {}
    for h in habits:
        try:
            duration_min = (
                datetime.strptime(h['end_time'], "%H:%M") -
                datetime.strptime(h['start_time'], "%H:%M")
            ).total_seconds() / 60
        except (ValueError, TypeError):
            duration_min = 0

        scheduled_count = 0
        completed_count = 0

        for day in range(1, days_in_month + 1):
            check_date = date(year, month, day)
            if is_scheduled(h, check_date):
                scheduled_count += 1
                if _is_completed(logs_map, h['id'], check_date.isoformat()):
                    completed_count += 1

        if scheduled_count == 0:
            continue

        result[h['habit_name']] = {
            "total_time_min": round(duration_min * completed_count, 1),
            "completion_rate": round((completed_count / scheduled_count) * 100, 1)
        }

    return result
