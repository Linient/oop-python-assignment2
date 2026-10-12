"""
src/tax_engine.py
Uganda Tax Engine modeling URA tax schedules using strict OOP and decimal.Decimal.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional



class TaxError(Exception):
    """Base exception for tax engine errors."""
    pass


class InvalidIncomeError(TaxError):
    """Raised when income or input amounts are negative."""
    pass


class Money:
    """
    Immutable value object representing monetary values in UGX.
    Backed strictly by decimal.Decimal to avoid float inaccuracies.
    """
    __slots__ = ("_amount",)

    def __init__(self, amount: Any):
        if isinstance(amount, float):
            raise TypeError("Float is prohibited in Money. Pass Decimal, int, or numeric str.")
        dec = Decimal(str(amount))
        object.__setattr__(self, "_amount", dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    @property
    def amount(self) -> Decimal:
        return self._amount

    def __add__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self._amount + other._amount)

    def __sub__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self._amount - other._amount)

    def __mul__(self, factor: Any) -> "Money":
        factor_dec = Decimal(str(factor))
        return Money(self._amount * factor_dec)

    def __lt__(self, other: "Money") -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self._amount < other._amount

    def __le__(self, other: "Money") -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self._amount <= other._amount

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return False
        return self._amount == other._amount

    def __repr__(self) -> str:
        return f"Money({self._amount} UGX)"


@dataclass(frozen=True)
class TaxContext:
    """Carries input data for any tax calculation."""
    gross_income: Money
    is_resident: bool = True
    allowances: Money = field(default_factory=lambda: Money("0"))
    deductions: Money = field(default_factory=lambda: Money("0"))
    metadata: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class TaxResult:
    """Contains calculation results."""
    tax_name: str
    taxable_amount: Money
    tax_due: Money


class Tax(ABC):
    """Abstract base class for all taxes."""
    @abstractmethod
    def calculate(self, ctx: TaxContext) -> TaxResult:
        """Computes tax based on context."""
        pass


class PAYETax(Tax):
    """Uganda PAYE Calculator implementing progressive monthly bands."""
    def calculate(self, ctx: TaxContext) -> TaxResult:
        chargeable = ctx.gross_income + ctx.allowances - ctx.deductions
        if chargeable < Money("0"):
            raise InvalidIncomeError("Chargeable income cannot be negative.")

        val = chargeable.amount
        tax = Decimal("0")

        if ctx.is_resident:
            if val <= Decimal("335000"):
                tax = Decimal("0")
            elif val <= Decimal("410000"):
                tax = (val - Decimal("335000")) * Decimal("0.20")
            elif val <= Decimal("485000"):
                tax = Decimal("15000") + (val - Decimal("410000")) * Decimal("0.25")
            else:
                tax = Decimal("33750") + (val - Decimal("485000")) * Decimal("0.30")
                if val > Decimal("10000000"):
                    tax += (val - Decimal("10000000")) * Decimal("0.10")
        else:
            if val <= Decimal("410000"):
                tax = val * Decimal("0.10")
            elif val <= Decimal("485000"):
                tax = Decimal("41000") + (val - Decimal("410000")) * Decimal("0.20")
            else:
                tax = Decimal("56000") + (val - Decimal("485000")) * Decimal("0.30")
                if val > Decimal("10000000"):
                    tax += (val - Decimal("10000000")) * Decimal("0.10")

        return TaxResult("PAYE", chargeable, Money(tax))


class PayrollPipeline:
    """Calculates employee NSSF, configurable LST, PAYE, and net pay."""
    def __init__(self, paye_tax: Optional[PAYETax] = None):
        self.paye = paye_tax or PAYETax()

    def run(self, gross: Money, lst: Money = Money("0"), is_resident: bool = True) -> Dict[str, Money]:
        if gross < Money("0"):
            raise InvalidIncomeError("Gross income cannot be negative.")

        nssf_employee = gross * Decimal("0.05")
        nssf_employer = gross * Decimal("0.10")

        ctx = TaxContext(gross_income=gross, is_resident=is_resident, deductions=lst)
        paye_res = self.paye.calculate(ctx)

        net_pay = gross - nssf_employee - lst - paye_res.tax_due
        return {
            "gross": gross,
            "nssf_employee": nssf_employee,
            "nssf_employer": nssf_employer,
            "local_service_tax": lst,
            "paye": paye_res.tax_due,
            "net_pay": net_pay,
        }


class VATCalculator(Tax):
    """Computes VAT at standard rate (18%), zero-rated (0%), or exempt."""
    STANDARD_RATE = Decimal("0.18")

    def calculate_invoice(self, net_amount: Money, category: str = "standard") -> Money:
        cat = category.lower()
        if cat == "standard":
            return net_amount * self.STANDARD_RATE
        elif cat in ("zero_rated", "exempt"):
            return Money("0")
        else:
            raise TaxError(f"Unknown VAT category: {category}")

    def calculate(self, ctx: TaxContext) -> TaxResult:
        vat_due = self.calculate_invoice(ctx.gross_income)
        return TaxResult("VAT", ctx.gross_income, vat_due)


class CorporateIncomeTax(Tax):
    """Calculates 30% resident corporate income tax."""
    CIT_RATE = Decimal("0.30")

    def calculate(self, ctx: TaxContext) -> TaxResult:
        chargeable = ctx.gross_income - ctx.deductions
        if chargeable < Money("0"):
            return TaxResult("CIT", Money("0"), Money("0"))
        return TaxResult("CIT", chargeable, chargeable * self.CIT_RATE)


class TaxPlanner:
    """
    Compares two extraction scenarios for a business owner:
    1. Taking earnings as a Salary (subject to PAYE).
    2. Taking earnings as Corporate Profit & Dividends (CIT 30% + Withholding Tax 15%).
    """
    def __init__(self, paye_engine: Optional[PAYETax] = None):
        self.paye = paye_engine or PAYETax()

    def compare_salary_vs_dividend(self, profit_before_tax: Money) -> Dict[str, Any]:
        """
        Runs both scenarios and returns the difference in total tax paid.
        """
        # --- Scenario A: Entire amount paid out as Salary ---
        salary_ctx = TaxContext(gross_income=profit_before_tax, is_resident=True)
        salary_result = self.paye.calculate(salary_ctx)
        salary_tax = salary_result.tax_due
        salary_take_home = profit_before_tax - salary_tax

        # --- Scenario B: Retained in company, CIT applied, then 15% dividend WHT ---
        # 1. 30% Corporate Income Tax
        cit_tax = profit_before_tax * Decimal("0.30")
        profit_after_cit = profit_before_tax - cit_tax
        # 2. 15% Dividend Withholding Tax on remaining profit
        dividend_wht = profit_after_cit * Decimal("0.15")
        dividend_total_tax = cit_tax + dividend_wht
        dividend_take_home = profit_before_tax - dividend_total_tax

        # Difference in take home pay
        tax_saved = salary_tax - dividend_total_tax

        return {
            "initial_amount": profit_before_tax,
            "salary_scenario": {
                "tax_paid": salary_tax,
                "take_home": salary_take_home
            },
            "dividend_scenario": {
                "cit_paid": cit_tax,
                "wht_paid": dividend_wht,
                "total_tax_paid": dividend_total_tax,
                "take_home": dividend_take_home
            },
            "tax_saved_with_dividend": tax_saved
        }


