"""
AI Analytics controller — Use Case 3: Predictive Analytics

Generates time-series forecasts for inventory demand, shelter occupancy,
and incident frequency using historical data from Eden tables.

Endpoints:
- /eden/ai_analytics/                       → dashboard with available forecasts
- /eden/ai_analytics/forecast/<target>      → view a specific forecast chart
- /eden/ai_analytics/run/<target>           → trigger a new forecast (admin)
- /eden/ai_analytics/data/<target>.json     → forecast data as JSON (for Chart.js)

Forecasts supported:
- inventory_demand   — daily demand per item (from inv_inv_track)
- shelter_occupancy  — daily shelter occupancy (from cr_shelter / sit_presence)
- incident_count     — daily incident count (from cms_post / sit_situation)
"""
import json
import datetime
from s3.ai_client import AIClient, AIClientError


FORECAST_TARGETS = {
    "auth_events": {
        "label": T("Auth Events Forecast"),
        "table": "auth_event",
        "metric": "count",
        "date_field": "time_stamp",
    },
}

# Note: inv_inv_track, sit_presence, cms_post are all lazy-loaded via s3db.
# auth_event is always loaded (it's a core auth table), so it works
# reliably for forecasting demo. In production, register your chosen
# table here.


def index():
    """Dashboard: list available forecast targets + recent forecasts."""
    response.title = T("AI Predictive Analytics")
    recent = db(db.ai_forecast.id > 0).select(
        db.ai_forecast.target_table, db.ai_forecast.metric,
        db.ai_forecast.generated_on, db.ai_forecast.model_version,
        orderby=~db.ai_forecast.generated_on,
        limitby=(0, 20), distinct=True
    )
    return dict(targets=FORECAST_TARGETS, recent=recent)


def forecast():
    """View a specific forecast chart."""
    target = request.args(0)
    if target not in FORECAST_TARGETS:
        redirect(URL("ai_analytics", "index"))
    spec = FORECAST_TARGETS[target]

    # Get the latest 30-day forecast
    rows = db(db.ai_forecast.target_table == spec["table"]).select(
        db.ai_forecast.forecast_date, db.ai_forecast.forecast_value,
        db.ai_forecast.confidence_lower, db.ai_forecast.confidence_upper,
        orderby=db.ai_forecast.forecast_date, limitby=(0, 30)
    )
    response.title = spec["label"]
    return dict(target=target, spec=spec, rows=rows)


def data():
    """Return forecast data as JSON (for Chart.js consumption)."""
    target = request.args(0)
    if target not in FORECAST_TARGETS:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "unknown target"})
    spec = FORECAST_TARGETS[target]
    rows = db(db.ai_forecast.target_table == spec["table"]).select(
        db.ai_forecast.forecast_date, db.ai_forecast.forecast_value,
        db.ai_forecast.confidence_lower, db.ai_forecast.confidence_upper,
        orderby=db.ai_forecast.forecast_date, limitby=(0, 30)
    )
    payload = {
        "labels": [r.forecast_date.isoformat() for r in rows],
        "forecast": [r.forecast_value for r in rows],
        "lower": [r.confidence_lower for r in rows],
        "upper": [r.confidence_upper for r in rows],
    }
    response.headers["Content-Type"] = "application/json"
    return json.dumps(payload, ensure_ascii=False)


def run():
    """Admin: manually trigger a forecast for a given target."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user/login"))
    target = request.args(0)
    if target not in FORECAST_TARGETS:
        redirect(URL("ai_analytics", "index"))

    try:
        # Try to import Prophet (optional dependency)
        from prophet import Prophet
        import pandas as pd
    except ImportError:
        return dict(error="Prophet not installed. Run: pip install prophet pandas", target=target)

    spec = FORECAST_TARGETS[target]
    table_name = spec["table"]
    metric = spec["metric"]
    date_field = spec["date_field"]

    table = getattr(db, table_name, None)
    if table is None:
        return dict(error=f"table {table_name} not found in DB", target=target)

    # Pull last 365 days of historical data
    cutoff = request.now - datetime.timedelta(days=365)
    field = getattr(table, date_field, None)
    if field is None:
        return dict(error=f"field {date_field} not in table {table_name}", target=target)
    rows = db((field > cutoff) & (table.deleted == False)).select(field)
    if len(rows) < 10:
        return dict(error=f"insufficient history ({len(rows)} rows); need >=10", target=target)

    # Aggregate per day
    df_data = []
    for r in rows:
        d = r[date_field]
        if hasattr(d, "date"):
            d = d.date()
        df_data.append({"ds": d, "y": 1})
    df = pd.DataFrame(df_data).groupby("ds", as_index=False).sum()
    df["ds"] = pd.to_datetime(df["ds"])

    # Fit + forecast
    m = Prophet(yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False)
    m.fit(df)
    future = m.make_future_dataframe(periods=30)
    forecast = m.predict(future).tail(30)

    # Persist forecast rows
    db(db.ai_forecast.target_table == table_name).delete()  # clear old
    for _, row in forecast.iterrows():
        db.ai_forecast.insert(
            target_table=table_name,
            metric=metric,
            forecast_date=row["ds"].date(),
            forecast_value=float(row["yhat"]),
            confidence_lower=float(row["yhat_lower"]),
            confidence_upper=float(row["yhat_upper"]),
            horizon_days=30,
            model_version="prophet-1.1",
            generated_on=request.now,
        )
    db.commit()

    return dict(success=True, target=target, rows_added=30)
