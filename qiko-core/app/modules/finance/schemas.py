"""Pydantic response models for the finance vertical.

Finance endpoints return camelCase JSON to match the legacy Excel-agent contract used by the
creator dashboard. Field names therefore mirror the JSON keys directly; only Python-reserved words
use aliases (``from_`` -> ``from``).

Top-level response fields are required because every route sets them; nested object fields keep
defaults so missing leaf values are coerced to zero/empty rather than causing a validation 500.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FinanceUploadResponse(BaseModel):
    fileName: str
    sourceName: str
    size: int
    namespace: str
    totalRows: int
    indexed: bool
    recordsStored: int


class FinanceFileRef(BaseModel):
    id: str = ""
    label: str
    namespace: str
    rowCount: int
    uploadedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FinanceFilesResponse(BaseModel):
    id: str
    files: list[FinanceFileRef]
    totalFiles: int
    totalRows: int


class FinanceDeleteResponse(BaseModel):
    success: bool
    deleted: list[str]
    deletedCount: int
    message: str


class FinanceChatResponse(BaseModel):
    reply: str
    intent: str
    sourcesUsed: list[str]
    rowsRetrieved: int
    summariesUsed: int


class FinanceHistoryMessage(BaseModel):
    role: str
    content: str
    timestamp: int


class FinanceHistoryResponse(BaseModel):
    id: str
    count: int
    history: list[FinanceHistoryMessage]


class FinanceClearHistoryResponse(BaseModel):
    success: bool
    id: str
    message: str


class FinanceDateRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(default="", alias="from")
    to: str = ""
    label: str = ""


class FinanceExpenseBreakdown(BaseModel):
    net: float = 0.0
    vat: float = 0.0


class FinanceSummaryOut(BaseModel):
    propertyCount: int = 0
    vendorCount: int = 0
    totalIncome: float = 0.0
    totalExpenses: float = 0.0
    netProfit: float = 0.0
    outstanding: float = 0.0
    expenseBreakdown: FinanceExpenseBreakdown = Field(default_factory=FinanceExpenseBreakdown)

    totalIncomeUnitCount: int = 0
    totalIncomeAveragePerProperty: float = 0.0
    totalIncomeTopProperty: str = ""
    totalIncomeTopPropertyRef: str = ""
    totalIncomeTopPropertyIncome: float = 0.0

    totalExpensesNet: float = 0.0
    totalExpensesVat: float = 0.0
    totalExpensesPropertyCount: int = 0
    totalExpensesInvoiceCount: int = 0
    totalExpensesAveragePerProperty: float = 0.0
    totalExpensesTopVendor: str = ""
    totalExpensesTopVendorAmount: float = 0.0
    totalExpensesTopCategory: str = ""
    totalExpensesTopCategoryAmount: float = 0.0

    netProfitMarginPercent: float = 0.0
    netProfitAverageMargin: float = 0.0
    netProfitTopProperty: str = ""
    netProfitTopPropertyRef: str = ""
    netProfitTopPropertyProfit: float = 0.0
    netProfitLowestPerformanceProperty: str = ""
    netProfitLowestPerformancePropertyRef: str = ""
    netProfitLowestPerformancePropertyProfit: float = 0.0
    netProfitCostToIncomeRatio: float = 0.0
    netProfitPropertyCount: int = 0

    outstandingPropertyCount: int = 0
    outstandingPositiveTotal: float = 0.0
    outstandingNegativeTotal: float = 0.0
    outstandingTopProperty: str = ""
    outstandingTopPropertyRef: str = ""
    outstandingTopPropertyOutstanding: float = 0.0
    outstandingAveragePerProperty: float = 0.0
    outstandingAsPercentOfIncome: float = 0.0
    outstandingIncomeReceivableCount: int = 0

    highPerforming: int = 0
    averagePerforming: int = 0
    underPerforming: int = 0
    highRisk: int = 0
    mediumRisk: int = 0
    lowRisk: int = 0
    totalUnits: int = 0
    totalInvoices: int = 0
    averageIncomePerProperty: float = 0.0
    averageExpensePerProperty: float = 0.0
    topProperty: str = ""
    topPropertyRef: str = ""
    worstProperty: str = ""
    worstPropertyRef: str = ""


class FinanceExpenseCategory(BaseModel):
    category: str = ""
    amount: float = 0.0


class FinanceTopVendor(BaseModel):
    vendorName: str = ""
    amount: float = 0.0


class FinanceMonthlyTrend(BaseModel):
    month: str = ""
    income: float = 0.0
    expenses: float = 0.0
    netProfit: float = 0.0


class FinanceUnitExpense(BaseModel):
    propertyRef: str = ""
    propertyName: str = ""
    unitRef: str = ""
    unitDescription: str = ""
    heading: str = ""
    expenditureDescription: str = ""
    supplierName: str = ""
    supplierRef: str = ""
    fixFloRef: str = ""
    nett: float = 0.0
    vat: float = 0.0
    gross: float = 0.0
    settled: str = ""
    invoiceDate: str = ""
    periodFrom: str = ""
    periodTo: str = ""


class FinanceUnitLedger(BaseModel):
    unitRef: str = ""
    unitDescription: str = ""
    propertyRef: str = ""
    propertyName: str = ""
    income: float = 0.0
    outstanding: float = 0.0
    totalGross: float = 0.0
    totalNett: float = 0.0
    totalVat: float = 0.0
    netProfit: float = 0.0
    invoiceCount: int = 0
    vendorCount: int = 0
    topVendor: str = ""
    expenses: list[FinanceUnitExpense] = Field(default_factory=list)


class FinancePropertyOut(BaseModel):
    propertyId: str = ""
    propertyRef: str = ""
    name: str = ""
    income: float = 0.0
    expenses: float = 0.0
    netProfit: float = 0.0
    marginPercent: float = 0.0
    outstanding: float = 0.0
    costToIncomeRatio: float = 0.0
    riskScore: int = 0
    riskLevel: str = ""
    profitabilityClass: str = ""
    invoiceCount: int = 0
    vendorCount: int = 0
    unitCount: int = 0
    expenseCategories: list[FinanceExpenseCategory] = Field(default_factory=list)
    topVendors: list[FinanceTopVendor] = Field(default_factory=list)
    unitLedger: list[FinanceUnitLedger] = Field(default_factory=list)
    monthlyTrends: list[FinanceMonthlyTrend] = Field(default_factory=list)


class FinanceChartIncomeExpense(BaseModel):
    propertyId: str = ""
    propertyRef: str = ""
    propertyName: str = ""
    income: float = 0.0
    expenses: float = 0.0
    netProfit: float = 0.0
    marginPercent: float = 0.0
    outstanding: float = 0.0
    costToIncomeRatio: float = 0.0
    riskScore: int = 0
    riskLevel: str = ""
    profitabilityClass: str = ""


class FinanceChartClassification(BaseModel):
    label: str = ""
    count: int = 0
    value: int = 0


class FinanceChartVendor(BaseModel):
    vendorId: str = ""
    vendorName: str = ""
    amount: float = 0.0
    sharePercent: float = 0.0
    propertyCount: int = 0
    invoiceCount: int = 0


class FinanceChartCategory(BaseModel):
    categoryId: str = ""
    categoryName: str = ""
    amount: float = 0.0
    sharePercent: float = 0.0
    invoiceCount: int = 0


class FinanceChartRisk(BaseModel):
    propertyId: str = ""
    propertyRef: str = ""
    propertyName: str = ""
    riskScore: int = 0
    riskLevel: str = ""


class FinanceChartRanking(BaseModel):
    rank: int = 0
    propertyId: str = ""
    propertyRef: str = ""
    propertyName: str = ""
    income: float = 0.0
    expenses: float = 0.0
    netProfit: float = 0.0
    marginPercent: float = 0.0
    riskScore: int = 0
    riskLevel: str = ""


class FinanceChartsOut(BaseModel):
    incomeVsExpensesByProperty: list[FinanceChartIncomeExpense] = Field(default_factory=list)
    profitabilityClassification: list[FinanceChartClassification] = Field(default_factory=list)
    topVendorsBySpend: list[FinanceChartVendor] = Field(default_factory=list)
    expenseCategories: list[FinanceChartCategory] = Field(default_factory=list)
    riskScoreByProperty: list[FinanceChartRisk] = Field(default_factory=list)
    propertyProfitabilityRanking: list[FinanceChartRanking] = Field(default_factory=list)
    monthlyTrends: list[FinanceMonthlyTrend] = Field(default_factory=list)


class FinanceTrendSectionOut(BaseModel):
    section: str = ""
    insightCount: int = 0
    insights: list[dict[str, Any]] = Field(default_factory=list)


class FinanceInsightsOut(BaseModel):
    propertyInsights: dict[str, Any] = Field(default_factory=dict)
    vendorInsights: dict[str, Any] = Field(default_factory=dict)
    financialSummary: dict[str, Any] = Field(default_factory=dict)
    riskAndCashFlow: dict[str, Any] = Field(default_factory=dict)


class FinanceAnalyticsResponse(BaseModel):
    status: str
    currency: str
    dateRange: FinanceDateRange
    summary: FinanceSummaryOut
    properties: list[FinancePropertyOut]
    charts: FinanceChartsOut
    insights: FinanceInsightsOut
    trends: list[FinanceTrendSectionOut]
    files: list[FinanceFileRef]
    totalFiles: int
    totalRows: int
