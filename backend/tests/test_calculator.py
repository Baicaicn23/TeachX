import pytest

from teachx.runtime.tools import CalculatorTool, ToolError


@pytest.mark.asyncio
async def test_calculator_evaluates_arithmetic() -> None:
    result = await CalculatorTool().execute(expression="(12 + 8) * 3")
    assert result.content == "60"


@pytest.mark.asyncio
async def test_calculator_rejects_code_execution() -> None:
    with pytest.raises(ToolError):
        await CalculatorTool().execute(expression="__import__('os').system('whoami')")
