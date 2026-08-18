"""Compute the property-portfolio analytics response from parsed income/expense rows.

A faithful Python port of qiko-mcp-parser src/analyzer.ts computeAnalytics/buildProperty/
buildCharts/buildInsights/buildTrends. Only the *computation* is ported -- no Pinecone/eval infra.

The public GET /finance/{agent_id}/analytics shape (see ELApi.ts ELUserAnalyticsResponse):
    {
      status, files[], totalFiles, totalRows, currency, dateRange{from,to,label},
      summary { propertyCount, vendorCount, totalIncome, totalExpenses, netProfit, outstanding,
                expenseBreakdown{net,vat} },
      properties[ ELUserProperty ],   # propertyId,name,income,expenses,netProfit,marginPercent,
                                       # outstanding,costToIncomeRatio,riskScore,riskLevel,
                                       # profitabilityClass,expenseCategories[],topVendors[],unitLedger[]
      charts { incomeVsExpensesByProperty, profitabilityClassification, topVendorsBySpend,
               expenseCategories, riskScoreByProperty, propertyProfitabilityRanking },
      insights { propertyInsights, vendorInsights, financialSummary, riskAndCashFlow },
      trends [ Property Performance, Arrears & Collections, Maintenance/Expenses, Unit-Level ]
    }

RISK / PROFITABILITY FORMULAS (ported verbatim from analyzer.ts, documented here as required):
 - costToIncomeRatio = (grossExpenses / income) * 100      (0 when income <= 0)
 - riskScore         = round(costToIncomeRatio * 2.5)      (0 when costToIncomeRatio <= 0);
                       higher cost-to-income => higher risk. NOTE: this heuristic is driven purely
                       by cost-to-income; it does NOT currently fold in the arrears/outstanding
                       ratio. Arrears are surfaced separately in the "Arrears & Collections"
                       trends section. Kept identical to the legacy service so the migrated
                       dashboard shows the same numbers.
 - riskLevel         = low (<=15) | medium (<=30) | high (>30)
 - profitabilityClass= high_performing (margin>=75) | average_performing (>=50) | under_performing
"""
from __future__ import annotations

from app.modules.finance.models import DEFAULT_CURRENCY, ExpenseRow, IncomeRow

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _round2(n: float) -> float:
    return round(n * 100) / 100


def _fmt(value: float, currency: str) -> str:
    symbol = {"GBP": "\u00a3", "USD": "$", "EUR": "\u20ac"}.get(currency, f"{currency} ")
    formatted = f"{abs(value):,.2f}"
    return f"-{symbol}{formatted}" if value < 0 else f"{symbol}{formatted}"


def _friendly_name(desc: str) -> str:
    import re

    if not desc:
        return ""
    stripped = re.sub(r",\s*[A-Za-z]{1,3}\d+\s*[A-Za-z0-9]{0,4}$", "", desc).strip()
    return stripped.rstrip(",").strip()


def _property_name_from_unit_desc(unit_desc: str) -> str:
    import re

    if not unit_desc:
        return ""
    s = unit_desc.strip()
    m = re.match(r"^(flat|apartment|apt|unit|room|studio)\b[^,]*,\s*(.+)$", s, re.IGNORECASE)
    if m:
        s = m.group(2).strip()
    return _friendly_name(s)


def _prop_id(rank: int) -> str:
    return f"PROP-{rank:03d}"


def _month_label(frm: str, to: str) -> str:
    fp, tp = frm.split("-"), to.split("-")
    if len(fp) < 2 or len(tp) < 2:
        return f"{frm} \u2014 {to}"
    fm = _MONTHS[int(fp[1]) - 1] if fp[1].isdigit() and 1 <= int(fp[1]) <= 12 else ""
    tm = _MONTHS[int(tp[1]) - 1] if tp[1].isdigit() and 1 <= int(tp[1]) <= 12 else ""
    return f"{fm} {fp[0]} \u2014 {tm} {tp[0]}"


def _risk_score(cost_to_income: float) -> int:
    if cost_to_income <= 0:
        return 0
    return round(cost_to_income * 2.5)


def _risk_level(score: int) -> str:
    if score <= 15:
        return "low"
    if score <= 30:
        return "medium"
    return "high"


def _profitability_class(margin: float) -> str:
    if margin >= 75:
        return "high_performing"
    if margin >= 50:
        return "average_performing"
    return "under_performing"


def _profitability_label(cls: str) -> str:
    return " ".join(w.capitalize() for w in cls.split("_"))


def _monthly_trends(expenses: list[ExpenseRow], incomes: list[IncomeRow]) -> list[dict]:
    inc_by_month: dict[str, float] = {}
    for i in incomes:
        if i.tran_date:
            inc_by_month[i.tran_date[:7]] = inc_by_month.get(i.tran_date[:7], 0.0) + i.amount

    exp_by_month: dict[str, float] = {}
    for e in expenses:
        d = e.period_to or e.exp_date
        if d:
            exp_by_month[d[:7]] = exp_by_month.get(d[:7], 0.0) + e.gross

    months = sorted(set(inc_by_month) | set(exp_by_month))
    return [{
        "month": m,
        "income": _round2(inc_by_month.get(m, 0.0)),
        "expenses": _round2(exp_by_month.get(m, 0.0)),
        "netProfit": _round2(inc_by_month.get(m, 0.0) - exp_by_month.get(m, 0.0)),
    } for m in months]


def _build_property(ref: str, desc: str, expenses: list[ExpenseRow], incomes: list[IncomeRow]) -> dict:
    income = _round2(sum(i.amount for i in incomes))
    expenses_total = _round2(sum(e.gross for e in expenses))
    net_profit = _round2(income - expenses_total)
    outstanding = _round2(sum(i.income_receivable for i in incomes))
    margin = _round2((net_profit / income) * 100) if income != 0 else 0.0
    cost_to_income = _round2((expenses_total / income) * 100) if income != 0 else 0.0
    risk_score = _risk_score(cost_to_income)

    by_heading: dict[str, list[ExpenseRow]] = {}
    for e in expenses:
        by_heading.setdefault(e.heading or "Other", []).append(e)
    expense_categories = sorted(
        ({"category": cat, "amount": _round2(sum(e.gross for e in rows))} for cat, rows in by_heading.items()),
        key=lambda c: c["amount"], reverse=True)

    by_vendor: dict[str, list[ExpenseRow]] = {}
    for e in expenses:
        if e.vendor:
            by_vendor.setdefault(e.vendor, []).append(e)
    top_vendors = sorted(
        ({"vendorName": name, "amount": _round2(sum(e.gross for e in rows))} for name, rows in by_vendor.items()),
        key=lambda v: v["amount"], reverse=True)[:5]

    unit_ledger = _build_unit_ledger(ref, _friendly_name(desc), expenses, incomes)

    return {
        "propertyId": "", "propertyRef": ref, "name": _friendly_name(desc),
        "income": income, "expenses": expenses_total, "netProfit": net_profit,
        "marginPercent": margin, "outstanding": outstanding, "costToIncomeRatio": cost_to_income,
        "riskScore": risk_score, "riskLevel": _risk_level(risk_score),
        "profitabilityClass": _profitability_class(margin),
        "invoiceCount": len(expenses), "vendorCount": len(by_vendor), "unitCount": len(unit_ledger),
        "expenseCategories": expense_categories, "topVendors": top_vendors, "unitLedger": unit_ledger,
        "monthlyTrends": _monthly_trends(expenses, incomes),
    }


def _build_unit_ledger(property_ref: str, property_name: str, expenses: list[ExpenseRow], incomes: list[IncomeRow]) -> list[dict]:
    unit_income: dict[str, dict] = {}
    for i in incomes:
        ref = i.unit_ref or i.property_ref
        if not ref:
            continue
        acc = unit_income.setdefault(ref, {"income": 0.0, "outstanding": 0.0})
        acc["income"] += i.amount
        acc["outstanding"] += i.income_receivable

    unit_expense: dict[str, dict] = {}
    for e in expenses:
        if not e.unit_ref:
            continue
        acc = unit_expense.setdefault(e.unit_ref, {"desc": e.unit_desc, "rows": []})
        if not acc["desc"] and e.unit_desc:
            acc["desc"] = e.unit_desc
        acc["rows"].append(e)

    by_vendor: dict[str, list[ExpenseRow]] = {}
    for e in expenses:
        if e.vendor:
            by_vendor.setdefault(e.vendor, []).append(e)

    ledger: list[dict] = []
    for ref in set(unit_income) | set(unit_expense):
        inc = unit_income.get(ref, {"income": 0.0, "outstanding": 0.0})
        exp = unit_expense.get(ref, {"desc": "", "rows": []})
        rows: list[ExpenseRow] = exp["rows"]
        ledger.append({
            "unitRef": ref, "unitDescription": exp["desc"],
            "propertyRef": property_ref, "propertyName": property_name,
            "income": _round2(inc["income"]), "outstanding": _round2(inc["outstanding"]),
            "totalGross": _round2(sum(e.gross for e in rows)),
            "totalNett": _round2(sum(e.nett for e in rows)),
            "totalVat": _round2(sum(e.vat for e in rows)),
            "netProfit": _round2(inc["income"] - sum(e.gross for e in rows)),
            "invoiceCount": len(rows),
            "vendorCount": len({e.vendor for e in rows if e.vendor}),
            "topVendor": max(((e.vendor, e.gross) for e in rows if e.vendor), key=lambda x: x[1], default=["", 0.0])[0],
            "expenses": [{
                "propertyRef": property_ref, "propertyName": property_name,
                "unitRef": ref, "unitDescription": exp["desc"],
                "heading": e.heading, "expenditureDescription": e.expenditure_desc,
                "nett": _round2(e.nett), "vat": _round2(e.vat), "gross": _round2(e.gross),
                "settled": e.settled, "invoiceDate": e.exp_date, "periodFrom": e.period_from,
                "periodTo": e.period_to, "fixFloRef": e.fixflo_ref, "supplierRef": e.supplier_ref,
                "supplierName": e.vendor,
            } for e in rows],
        })
    return ledger


def _public_property(p: dict) -> dict:
    """The ELUserProperty view returned in the analytics `properties[]` array."""
    return {
        "propertyId": p["propertyId"], "propertyRef": p["propertyRef"], "name": p["name"],
        "income": p["income"], "expenses": p["expenses"], "netProfit": p["netProfit"],
        "marginPercent": p["marginPercent"], "outstanding": p["outstanding"],
        "costToIncomeRatio": p["costToIncomeRatio"], "riskScore": p["riskScore"],
        "riskLevel": p["riskLevel"], "profitabilityClass": p["profitabilityClass"],
        "invoiceCount": p["invoiceCount"], "vendorCount": p["vendorCount"], "unitCount": p["unitCount"],
        "expenseCategories": p["expenseCategories"], "topVendors": p["topVendors"],
        "unitLedger": p["unitLedger"], "monthlyTrends": p["monthlyTrends"],
    }


def compute_analytics(expenses: list[ExpenseRow], incomes: list[IncomeRow], *,
                      frm: str | None = None, to: str | None = None,
                      currency: str = DEFAULT_CURRENCY) -> dict:
    def in_range(iso: str) -> bool:
        if not iso:
            return True
        if frm and iso < frm:
            return False
        if to and iso > to:
            return False
        return True

    def _exp_date(e: ExpenseRow) -> str:
        return e.period_to or e.exp_date

    f_exp = [e for e in expenses if in_range(_exp_date(e))]
    f_inc = [i for i in incomes if in_range(i.tran_date)]

    all_dates = sorted([_exp_date(e) for e in f_exp if _exp_date(e)] + [i.tran_date for i in f_inc if i.tran_date])
    date_from = frm or (all_dates[0] if all_dates else None)
    date_to = to or (all_dates[-1] if all_dates else None)

    ref_to_desc: dict[str, str] = {}
    all_refs: set[str] = set()
    for e in f_exp:
        if not e.property_ref:
            continue
        all_refs.add(e.property_ref)
        if e.property_ref not in ref_to_desc and e.property_desc:
            ref_to_desc[e.property_ref] = e.property_desc
    for i in f_inc:
        if not i.property_ref:
            continue
        all_refs.add(i.property_ref)
        if i.property_ref not in ref_to_desc:
            name = _property_name_from_unit_desc(i.unit_desc)
            if name:
                ref_to_desc[i.property_ref] = name

    import re

    real_refs = [r for r in all_refs if not re.search(r"owner\s+expenditure", ref_to_desc.get(r, ""), re.IGNORECASE)]

    exp_by_prop: dict[str, list[ExpenseRow]] = {}
    for e in f_exp:
        if e.property_ref in real_refs:
            exp_by_prop.setdefault(e.property_ref, []).append(e)
    inc_by_prop: dict[str, list[IncomeRow]] = {}
    for i in f_inc:
        if i.property_ref in real_refs:
            inc_by_prop.setdefault(i.property_ref, []).append(i)

    total_income = _round2(sum(i.amount for i in f_inc))
    real_exp = [e for e in f_exp if e.property_ref in real_refs]
    total_expenses = _round2(sum(e.gross for e in real_exp))
    total_nett = _round2(sum(e.nett for e in real_exp))
    total_vat = _round2(sum(e.vat for e in real_exp))
    total_outstanding = _round2(sum(i.income_receivable for i in f_inc))
    net_profit = _round2(total_income - total_expenses)

    distinct_vendors = {e.vendor for e in real_exp if e.vendor}

    raw_props = [_build_property(r, ref_to_desc.get(r, ""), exp_by_prop.get(r, []), inc_by_prop.get(r, []))
                 for r in real_refs]
    raw_props.sort(key=lambda p: p["netProfit"], reverse=True)
    for idx, p in enumerate(raw_props):
        p["propertyId"] = _prop_id(idx + 1)

    risk_counts = {"low": 0, "medium": 0, "high": 0}
    for p in raw_props:
        risk_counts[p["riskLevel"]] += 1

    charts = _build_charts(raw_props, real_exp, total_expenses)
    charts["monthlyTrends"] = _monthly_trends(real_exp, f_inc)
    insights = _build_insights(raw_props, charts, total_income, total_expenses, net_profit,
                               total_outstanding, len(distinct_vendors), risk_counts)
    trends = _build_trends(raw_props, real_exp, total_income, total_outstanding)

    return {
        "status": "success",
        "currency": currency,
        "dateRange": {
            "from": date_from or "", "to": date_to or "",
            "label": _month_label(date_from, date_to) if date_from and date_to else "",
        },
        "summary": {
            "propertyCount": len(real_refs), "vendorCount": len(distinct_vendors),
            "totalIncome": total_income, "totalExpenses": total_expenses, "netProfit": net_profit,
            "outstanding": total_outstanding, "expenseBreakdown": {"net": total_nett, "vat": total_vat},
        },
        "properties": [_public_property(p) for p in raw_props],
        "charts": charts,
        "insights": insights,
        "trends": trends,
    }


def _build_charts(props: list[dict], all_exp: list[ExpenseRow], total_gross: float) -> dict:
    income_vs_expenses = [{
        "propertyId": p["propertyId"], "propertyRef": p["propertyRef"], "propertyName": p["name"],
        "income": p["income"], "expenses": p["expenses"], "netProfit": p["netProfit"],
        "marginPercent": p["marginPercent"], "outstanding": p["outstanding"],
        "costToIncomeRatio": p["costToIncomeRatio"], "riskScore": p["riskScore"],
        "riskLevel": p["riskLevel"], "profitabilityClass": p["profitabilityClass"],
    } for p in sorted(props, key=lambda p: p["income"], reverse=True)[:10]]

    by_class: dict[str, list[dict]] = {}
    for p in props:
        by_class.setdefault(p["profitabilityClass"], []).append(p)
    profitability_classification = [
        {"label": _profitability_label(cls), "count": len(items), "value": len(items)}
        for cls, items in sorted(by_class.items(), key=lambda kv: len(kv[1]), reverse=True)
    ]

    by_vendor: dict[str, list[ExpenseRow]] = {}
    for e in all_exp:
        if e.vendor:
            by_vendor.setdefault(e.vendor, []).append(e)
    top_vendors = []
    for idx, (name, rows) in enumerate(sorted(by_vendor.items(),
                                               key=lambda kv: sum(e.gross for e in kv[1]), reverse=True)[:8]):
        amount = _round2(sum(e.gross for e in rows))
        top_vendors.append({
            "vendorId": f"V-{idx + 1:03d}", "vendorName": name, "amount": amount,
            "sharePercent": _round2((amount / total_gross) * 100) if total_gross else 0.0,
            "propertyCount": len({e.property_ref for e in rows}), "invoiceCount": len(rows),
        })

    by_heading: dict[str, list[ExpenseRow]] = {}
    for e in all_exp:
        by_heading.setdefault(e.heading or "Other", []).append(e)
    expense_categories = []
    for idx, (name, rows) in enumerate(sorted(by_heading.items(),
                                              key=lambda kv: sum(e.gross for e in kv[1]), reverse=True)):
        amount = _round2(sum(e.gross for e in rows))
        expense_categories.append({
            "categoryId": f"EC-{idx + 1:03d}", "categoryName": name, "amount": amount,
            "sharePercent": _round2((amount / total_gross) * 100) if total_gross else 0.0,
            "invoiceCount": len(rows),
        })

    risk_by_property = [{
        "propertyId": p["propertyId"], "propertyRef": p["propertyRef"], "propertyName": p["name"],
        "riskScore": p["riskScore"], "riskLevel": p["riskLevel"],
    } for p in sorted(props, key=lambda p: p["riskScore"], reverse=True)[:10]]

    ranking = [{
        "rank": idx + 1, "propertyId": p["propertyId"], "propertyRef": p["propertyRef"],
        "propertyName": p["name"], "income": p["income"], "expenses": p["expenses"],
        "netProfit": p["netProfit"], "marginPercent": p["marginPercent"],
        "riskScore": p["riskScore"], "riskLevel": p["riskLevel"],
    } for idx, p in enumerate(sorted(props, key=lambda p: p["netProfit"], reverse=True)[:10])]

    return {
        "incomeVsExpensesByProperty": income_vs_expenses,
        "profitabilityClassification": profitability_classification,
        "topVendorsBySpend": top_vendors, "expenseCategories": expense_categories,
        "riskScoreByProperty": risk_by_property, "propertyProfitabilityRanking": ranking,
    }


def _prop_helper(p: dict | None) -> dict:
    if p is None:
        return {"propertyId": "", "propertyRef": "", "propertyName": "", "income": 0, "expenses": 0,
                "netProfit": 0, "marginPercent": 0, "outstanding": 0, "costToIncomeRatio": 0,
                "riskScore": 0, "riskLevel": "low", "profitabilityClass": "under_performing"}
    return {
        "propertyId": p["propertyId"], "propertyRef": p["propertyRef"], "propertyName": p["name"],
        "income": p["income"], "expenses": p["expenses"], "netProfit": p["netProfit"],
        "marginPercent": p["marginPercent"], "outstanding": p["outstanding"],
        "costToIncomeRatio": p["costToIncomeRatio"], "riskScore": p["riskScore"],
        "riskLevel": p["riskLevel"], "profitabilityClass": p["profitabilityClass"],
    }


def _build_insights(props: list[dict], charts: dict, total_income: float, total_expenses: float,
                    net_profit: float, outstanding: float, vendor_count: int, risk_counts: dict) -> dict:
    ranked = sorted(props, key=lambda p: p["netProfit"], reverse=True)
    top_performer = ranked[0] if ranked else None
    worst_performer = ranked[-1] if ranked else None

    by_cti = sorted(props, key=lambda p: p["costToIncomeRatio"], reverse=True)
    highest_cti = by_cti[0] if by_cti else None
    comparison_cti = by_cti[1] if len(by_cti) > 1 else None
    market_avg_cti = _round2(sum(p["costToIncomeRatio"] for p in by_cti) / len(by_cti)) if by_cti else 0.0

    by_income = sorted(props, key=lambda p: p["income"], reverse=True)
    top_vendors = charts["topVendorsBySpend"]
    top_vendor = top_vendors[0] if top_vendors else None

    overall_margin = _round2((net_profit / total_income) * 100) if total_income != 0 else 0.0
    total_units = sum(len(p["unitLedger"]) for p in props)
    avg_risk = _round2(sum(p["riskScore"] for p in props) / len(props)) if props else 0.0
    top_risk = max(props, key=lambda p: p["riskScore"]) if props else None

    return {
        "propertyInsights": {
            "topPerformer": _prop_helper(top_performer),
            "worstPerformer": _prop_helper(worst_performer),
            "highestCostToIncomeRatio": {
                "propertyId": highest_cti["propertyId"], "propertyRef": highest_cti["propertyRef"],
                "propertyName": highest_cti["name"], "costToIncomeRatio": highest_cti["costToIncomeRatio"],
                "income": highest_cti["income"], "expenses": highest_cti["expenses"],
                "riskScore": highest_cti["riskScore"], "riskLevel": highest_cti["riskLevel"],
                "comparisonProperty": {
                    "propertyId": comparison_cti["propertyId"], "propertyRef": comparison_cti["propertyRef"],
                    "propertyName": comparison_cti["name"], "costToIncomeRatio": comparison_cti["costToIncomeRatio"],
                } if comparison_cti else {"propertyId": "", "propertyRef": "", "propertyName": "",
                                          "costToIncomeRatio": 0},
                "marketAveragePercent": market_avg_cti,
            } if highest_cti else {"propertyId": "", "propertyName": "", "costToIncomeRatio": 0,
                                   "marketAveragePercent": 0},
            "topIncomeGenerators": [{
                "propertyId": p["propertyId"], "propertyRef": p["propertyRef"], "propertyName": p["name"],
                "income": p["income"], "expenses": p["expenses"], "netProfit": p["netProfit"],
                "marginPercent": p["marginPercent"],
            } for p in by_income[:3]],
        },
        "vendorInsights": {
            "topVendor": {
                "vendorId": top_vendor["vendorId"], "vendorName": top_vendor["vendorName"],
                "amount": top_vendor["amount"], "sharePercent": top_vendor["sharePercent"],
                "propertyCount": top_vendor["propertyCount"], "invoiceCount": top_vendor["invoiceCount"],
            } if top_vendor else {"vendorId": "", "vendorName": "", "amount": 0, "sharePercent": 0,
                                  "propertyCount": 0, "invoiceCount": 0},
            "vendorCount": vendor_count, "totalSpend": total_expenses,
            "averagePerVendor": _round2(total_expenses / vendor_count) if vendor_count else 0.0,
            "topVendors": [{"vendorName": v["vendorName"], "amount": v["amount"],
                            "sharePercent": v["sharePercent"]} for v in top_vendors[:5]],
        },
        "financialSummary": {
            "totalIncome": total_income, "totalExpenses": total_expenses, "netProfit": net_profit,
            "outstanding": outstanding, "marginPercent": overall_margin,
            "costToIncomeRatio": _round2((total_expenses / total_income) * 100) if total_income != 0 else 0.0,
            "propertyCount": len(props), "vendorCount": vendor_count, "unitCount": total_units,
            "invoiceCount": sum(p["invoiceCount"] for p in props),
        },
        "riskAndCashFlow": {
            "highRiskProperties": risk_counts["high"], "mediumRiskProperties": risk_counts["medium"],
            "lowRiskProperties": risk_counts["low"], "totalProperties": len(props),
            "outstandingReceivables": outstanding, "averageRiskScore": avg_risk,
            "topRiskProperty": {
                "propertyId": top_risk["propertyId"], "propertyRef": top_risk["propertyRef"],
                "propertyName": top_risk["name"], "riskScore": top_risk["riskScore"],
                "riskLevel": top_risk["riskLevel"], "costToIncomeRatio": top_risk["costToIncomeRatio"],
            } if top_risk else {"propertyId": "", "propertyRef": "", "propertyName": "", "riskScore": 0,
                                "riskLevel": "low", "costToIncomeRatio": 0},
            "highPerforming": sum(1 for p in props if p["profitabilityClass"] == "high_performing"),
            "averagePerforming": sum(1 for p in props if p["profitabilityClass"] == "average_performing"),
            "underPerforming": sum(1 for p in props if p["profitabilityClass"] == "under_performing"),
        },
    }


def _gbp(n: float) -> str:
    return f"\u00a3{n:,.2f}"


def _build_trends(props: list[dict], all_exp: list[ExpenseRow], total_income: float,
                  total_outstanding: float) -> list[dict]:
    by_income = sorted(props, key=lambda p: p["income"], reverse=True)
    top_prop = by_income[0] if by_income else None
    top_share = _round2((top_prop["income"] / total_income) * 100) if total_income > 0 and top_prop else 0.0
    lowest_margin = sorted(props, key=lambda p: p["marginPercent"])[0] if props else None
    top5 = by_income[:5]
    top5_income = _round2(sum(p["income"] for p in top5))
    top5_share = _round2((top5_income / total_income) * 100) if total_income > 0 else 0.0

    property_performance = {
        "section": "Property Performance", "insightCount": 3, "insights": [
            {"title": "Top Performer",
             "insightText": (f"{top_prop['name']} generates the highest net income at "
                             f"{_gbp(top_prop['netProfit'])}, contributing {top_share}% of total portfolio income"
                             if top_prop else "No property data available"),
             "metricValue": top_prop["netProfit"] if top_prop else 0,
             "metricFormatted": _gbp(top_prop["netProfit"]) if top_prop else "\u00a30.00",
             "propertyRef": top_prop["propertyRef"] if top_prop else "",
             "propertyName": top_prop["name"] if top_prop else "",
             "direction": "stable", "severity": "positive"},
            {"title": "Lowest Margin",
             "insightText": (f"{lowest_margin['name']} has the lowest margin at "
                             f"{lowest_margin['marginPercent']}% \u2014 review expenses"
                             if lowest_margin else "No margin data available"),
             "metricValue": lowest_margin["marginPercent"] if lowest_margin else 0,
             "metricFormatted": f"{lowest_margin['marginPercent']}%" if lowest_margin else "0%",
             "propertyRef": lowest_margin["propertyRef"] if lowest_margin else "",
             "propertyName": lowest_margin["name"] if lowest_margin else "",
             "direction": "decrease", "severity": "warning"},
            {"title": "Concentration Risk",
             "insightText": (f"Top 5 properties account for {top5_share}% of total portfolio income, "
                             f"indicating {'high' if top5_share > 60 else 'moderate' if top5_share > 40 else 'low'}"
                             " concentration risk"),
             "metricValue": top5_share, "metricFormatted": f"{top5_share}%",
             "top5Properties": [{"propertyRef": p["propertyRef"], "name": p["name"], "income": p["income"]}
                                for p in top5],
             "direction": "stable", "severity": "info"},
        ],
    }

    with_arrears = [p for p in props if p["outstanding"] > 0]
    total_arrears = _round2(sum(max(0.0, p["outstanding"]) for p in props))
    arrears_pct = _round2((total_arrears / total_income) * 100) if total_income > 0 else 0.0
    top_arrears = sorted(with_arrears, key=lambda p: p["outstanding"], reverse=True)[0] if with_arrears else None
    if total_income > 0 and total_outstanding > 0:
        collection_rate = _round2(((total_income - total_outstanding) / total_income) * 100)
    else:
        collection_rate = 100.0 if total_income > 0 else 0.0
    below_threshold = sum(1 for p in props
                          if p["income"] > 0 and ((p["income"] - max(0.0, p["outstanding"])) / p["income"]) * 100 < 50)

    arrears_collections = {
        "section": "Arrears & Collections", "insightCount": 3, "insights": [
            {"title": "Total Arrears",
             "insightText": (f"Total tenant arrears stand at {_gbp(total_arrears)} across "
                             f"{len(with_arrears)} properties \u2014 {arrears_pct}% of annual demanded rent"),
             "metricValue": total_arrears, "metricFormatted": _gbp(total_arrears),
             "propertyCount": len(with_arrears), "percentOfIncome": arrears_pct,
             "direction": "stable", "severity": "warning" if total_arrears > 0 else "positive"},
            {"title": "Highest Arrears",
             "insightText": (f"{top_arrears['name']} has the highest individual arrears at "
                             f"{_gbp(top_arrears['outstanding'])} \u2014 recommend escalation to collections"
                             if top_arrears else "No arrears data available"),
             "metricValue": top_arrears["outstanding"] if top_arrears else 0,
             "metricFormatted": _gbp(top_arrears["outstanding"]) if top_arrears else "\u00a30.00",
             "propertyRef": top_arrears["propertyRef"] if top_arrears else "",
             "propertyName": top_arrears["name"] if top_arrears else "",
             "direction": "increase", "severity": "warning"},
            {"title": "Collection Rate",
             "insightText": (f"Collection rate is {collection_rate}% overall but {below_threshold} "
                             "properties fall below 50% threshold"),
             "metricValue": collection_rate, "metricFormatted": f"{collection_rate}%",
             "belowThresholdCount": below_threshold,
             "direction": "decrease" if collection_rate < 50 else "stable",
             "severity": "warning" if collection_rate < 50 else "positive"},
        ],
    }

    by_cat: dict[str, float] = {}
    for e in all_exp:
        by_cat[e.heading or "Other"] = by_cat.get(e.heading or "Other", 0.0) + e.gross
    total_expenses = _round2(sum(e.gross for e in all_exp))
    top_cat = max(by_cat.items(), key=lambda kv: kv[1]) if by_cat else None
    top_cat_amount = _round2(top_cat[1]) if top_cat else 0.0
    top_cat_share = _round2((top_cat_amount / total_expenses) * 100) if total_expenses > 0 else 0.0

    by_vendor: dict[str, float] = {}
    for e in all_exp:
        if e.vendor:
            by_vendor[e.vendor] = by_vendor.get(e.vendor, 0.0) + e.gross
    top_vendor = max(by_vendor.items(), key=lambda kv: kv[1]) if by_vendor else None
    top_vendor_amount = _round2(top_vendor[1]) if top_vendor else 0.0
    top_vendor_share = _round2((top_vendor_amount / total_expenses) * 100) if total_expenses > 0 else 0.0
    high_cost = [p for p in props if p["costToIncomeRatio"] > 15]

    maintenance = {
        "section": "Maintenance / Expenses", "insightCount": 3, "insights": [
            {"title": "Top Expense Category",
             "insightText": (f"{top_cat[0]} is the largest expense category at {top_cat_share}% of total "
                             f"spend ({_gbp(top_cat_amount)})" if top_cat else "No expense data available"),
             "metricValue": top_cat_amount, "metricFormatted": _gbp(top_cat_amount),
             "categoryName": top_cat[0] if top_cat else "", "sharePercent": top_cat_share,
             "direction": "stable", "severity": "info"},
            {"title": "Vendor Concentration",
             "insightText": (f"{top_vendor[0]} accounts for {top_vendor_share}% of total maintenance spend "
                             f"\u2014 {'high concentration risk' if top_vendor_share > 50 else 'within acceptable range'}"
                             if top_vendor else "No vendor data available"),
             "metricValue": top_vendor_amount, "metricFormatted": _gbp(top_vendor_amount),
             "vendorName": top_vendor[0] if top_vendor else "", "sharePercent": top_vendor_share,
             "direction": "stable", "severity": "warning" if top_vendor_share > 50 else "info"},
            {"title": "High Cost Properties",
             "insightText": (f"{len(high_cost)} {'property has' if len(high_cost) == 1 else 'properties have'} "
                             f"high cost-to-income ratio ({', '.join(p['name'] for p in high_cost) or 'none'}) "
                             "\u2014 review maintenance contracts"),
             "metricValue": len(high_cost), "metricFormatted": str(len(high_cost)),
             "affectedProperties": [{"propertyRef": p["propertyRef"], "name": p["name"],
                                     "costToIncomeRatio": p["costToIncomeRatio"], "riskScore": p["riskScore"]}
                                    for p in high_cost],
             "direction": "increase" if high_cost else "stable",
             "severity": "warning" if high_cost else "positive"},
        ],
    }

    all_units = []
    for prop in props:
        for unit in prop["unitLedger"]:
            all_units.append({"unitRef": unit["unitRef"], "unitDescription": unit["unitDescription"],
                              "propertyName": prop["name"], "totalGross": unit["totalGross"],
                              "invoiceCount": len(unit["expenses"])})
    top_unit = sorted(all_units, key=lambda u: u["totalGross"], reverse=True)[0] if all_units else None
    recurring = [u for u in all_units if u["invoiceCount"] >= 3]
    avg_unit = _round2(sum(u["totalGross"] for u in all_units) / len(all_units)) if all_units else 0.0
    above_avg = [u for u in all_units if u["totalGross"] > avg_unit * 2]

    unit_trends = {
        "section": "Unit-Level Trends", "insightCount": 3, "insights": [
            {"title": "Highest Maintenance Unit",
             "insightText": (f"{top_unit['unitDescription']} ({top_unit['propertyName']}) has the highest "
                             f"maintenance spend at {_gbp(top_unit['totalGross'])} across "
                             f"{top_unit['invoiceCount']} invoices" if top_unit else "No unit data available"),
             "metricValue": top_unit["totalGross"] if top_unit else 0,
             "metricFormatted": _gbp(top_unit["totalGross"]) if top_unit else "\u00a30.00",
             "unitRef": top_unit["unitRef"] if top_unit else "",
             "unitDescription": top_unit["unitDescription"] if top_unit else "",
             "propertyName": top_unit["propertyName"] if top_unit else "",
             "direction": "stable", "severity": "info"},
            {"title": "Recurring Issues",
             "insightText": (f"{len(recurring)} units have 3+ maintenance invoices \u2014 may indicate "
                             "recurring issues requiring capital investment"),
             "metricValue": len(recurring), "metricFormatted": str(len(recurring)),
             "direction": "increase" if recurring else "stable", "severity": "info"},
            {"title": "Above Average Spend",
             "insightText": (f"{len(above_avg)} units have maintenance spend more than 2x the average "
                             f"({_gbp(avg_unit)}) \u2014 review for systemic issues"),
             "metricValue": len(above_avg), "metricFormatted": str(len(above_avg)),
             "averagePerUnit": _gbp(avg_unit),
             "direction": "increase" if above_avg else "stable",
             "severity": "warning" if above_avg else "positive"},
        ],
    }

    return [property_performance, arrears_collections, maintenance, unit_trends]
