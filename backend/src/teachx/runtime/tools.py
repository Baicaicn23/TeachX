from __future__ import annotations

import ast
import operator
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar


class ToolError(ValueError):
    pass


@dataclass(slots=True)
class ToolResult:
    content: str
    success: bool = True
    metadata: dict[str, Any] | None = None


class BaseTool(ABC):
    """A model-callable unit with metadata and one execution method."""

    name: ClassVar[str]
    description: ClassVar[str]
    parameters: ClassVar[dict[str, Any]]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate a basic arithmetic expression safely."
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Arithmetic expression using +, -, *, /, and parentheses.",
            }
        },
        "required": ["expression"],
        "additionalProperties": False,
    }

    _binary_operators: ClassVar[dict[type[ast.operator], Any]] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _unary_operators: ClassVar[dict[type[ast.unaryop], Any]] = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        expression = str(kwargs.get("expression") or "").strip()
        if not expression:
            raise ToolError("expression is required")
        try:
            tree = ast.parse(expression, mode="eval")
            value = self._evaluate(tree.body)
        except (SyntaxError, TypeError, ZeroDivisionError, ToolError) as exc:
            raise ToolError(f"invalid expression: {exc}") from exc
        return ToolResult(content=str(value), metadata={"expression": expression})

    def _evaluate(self, node: ast.AST) -> int | float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self._binary_operators:
            return self._binary_operators[type(node.op)](
                self._evaluate(node.left),
                self._evaluate(node.right),
            )
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._unary_operators:
            return self._unary_operators[type(node.op)](self._evaluate(node.operand))
        raise ToolError(f"unsupported syntax: {type(node).__name__}")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def schemas(self, enabled: list[str] | None = None) -> list[dict[str, Any]]:
        names = enabled if enabled is not None else list(self._tools)
        return [self._tools[name].schema() for name in names if name in self._tools]

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(content=f"Unknown tool: {name}", success=False)
        try:
            return await tool.execute(**arguments)
        except Exception as exc:  # one bad tool must not kill the whole turn
            return ToolResult(content=f"Tool {name} failed: {exc}", success=False)


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    return registry
