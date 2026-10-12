from decimal import Decimal
import pytest
from hypothesis import given, strategies as st
from src.tax_engine import (
    Money,
    TaxContext,
    PAYETax,
    InvalidIncomeError,
    TaxPlanner,
)

def test_money_disallows_float():
    with pytest.raises(TypeError):
        Money(100.50)

def test_paye_resident_boundaries():
    paye = PAYETax()
    # Edge 1: <= 335,000
    assert paye.calculate(TaxContext(Money("335000"))).tax_due == Money("0")
    # Edge 2: 335,001
    assert paye.calculate(TaxContext(Money("335001"))).tax_due == Money("0.20")
    # Edge 3: 410,000
    assert paye.calculate(TaxContext(Money("410000"))).tax_due == Money("15000.00")
    # Edge 4: 485,000
    assert paye.calculate(TaxContext(Money("485000"))).tax_due == Money("33750.00")
    # Edge 5: 10,000,000
    assert paye.calculate(TaxContext(Money("10000000"))).tax_due == Money("2888250.00")
    # Edge 6: 10,000,001
    assert paye.calculate(TaxContext(Money("10000001"))).tax_due == Money("2888250.40")

def test_negative_income_raises():
    paye = PAYETax()
    with pytest.raises(InvalidIncomeError):
        paye.calculate(TaxContext(Money("-1000")))

@given(st.integers(min_value=0, max_value=50_000_000))
def test_paye_properties(val):
    paye = PAYETax()
    res = paye.calculate(TaxContext(Money(val)))
    assert res.tax_due >= Money("0")
    assert res.tax_due <= Money(val)

def test_tax_planner_comparison():
    planner = TaxPlanner()
    result = planner.compare_salary_vs_dividend(Money("10000000"))
    # Confirm both take home values are calculated and positive
    assert result["salary_scenario"]["take_home"] > Money("0")
    assert result["dividend_scenario"]["take_home"] > Money("0")