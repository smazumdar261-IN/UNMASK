"""Go AST to Common IR bidirectional converter.

Per Section 15 and Section 16 of the Master Specification (Phase 9: Go):
Bridges Go AST and the Common Intermediate Representation (IR),
allowing analysis passes and CFG engines to operate on Go constructs independently of syntax.
"""

from __future__ import annotations

from typing import Any, List, Optional

from core.ir import (
    IRAssignment,
    IRBinaryOperation,
    IRBranch,
    IRCall,
    IRConstant,
    IRExpression,
    IRFunction,
    IRLoop,
    IRModule,
    IRNode,
    IRReturn,
    IRStatement,
    IRUnaryOperation,
    IRVariable,
)
from languages.go.ast_nodes import (
    GoAssignmentStatement,
    GoBinaryExpression,
    GoBlock,
    GoCallExpression,
    GoConstSpec,
    GoExpression,
    GoExpressionStatement,
    GoField,
    GoFile,
    GoForStatement,
    GoFunctionDecl,
    GoIdentifier,
    GoIfStatement,
    GoLiteral,
    GoReturnStatement,
    GoSelectorExpression,
    GoStatement,
    GoUnaryExpression,
    GoVarSpec,
)


class GoIRConverter:
    """Converts between Go AST and Common IR."""

    @classmethod
    def to_ir(cls, file_node: GoFile) -> IRModule:
        """Converts a GoFile AST into a Common IRModule."""
        ir_stmts: List[IRStatement] = []

        for decl in file_node.decls:
            if isinstance(decl, GoFunctionDecl):
                ir_fn = cls._convert_func_to_ir(decl)
                ir_stmts.append(ir_fn)
            elif isinstance(decl, (GoConstSpec, GoVarSpec)):
                for name, val in zip(decl.names, decl.values):
                    ir_stmts.append(
                        IRAssignment(
                            target=IRVariable(name=name, location=decl.location),
                            value=cls._convert_expression_to_ir(val),
                            location=decl.location,
                        )
                    )

        return IRModule(name=file_node.package, language="go", body=ir_stmts, location=file_node.location)

    @classmethod
    def _convert_func_to_ir(cls, fn: GoFunctionDecl) -> IRFunction:
        params = [p.name for p in fn.params]
        ret_type = fn.results[0].type_name if fn.results else None
        body_stmts: List[IRStatement] = []

        if fn.body:
            for s in fn.body.statements:
                converted = cls._convert_statement_to_ir(s)
                if converted:
                    body_stmts.append(converted)

        return IRFunction(
            name=fn.name,
            parameters=params,
            body=body_stmts,
            return_type=ret_type,
            location=fn.location,
        )

    @classmethod
    def _convert_statement_to_ir(cls, stmt: GoStatement) -> Optional[IRStatement]:
        if isinstance(stmt, GoAssignmentStatement):
            if stmt.left and stmt.right:
                target_name = stmt.left[0].name if isinstance(stmt.left[0], GoIdentifier) else "_"
                val = cls._convert_expression_to_ir(stmt.right[0])
                return IRAssignment(target=IRVariable(name=target_name), value=val, location=stmt.location)

        if isinstance(stmt, GoIfStatement):
            cond = cls._convert_expression_to_ir(stmt.condition)
            body: List[IRStatement] = []
            for s in stmt.body.statements:
                cs = cls._convert_statement_to_ir(s)
                if cs:
                    body.append(cs)

            orelse: List[IRStatement] = []
            if stmt.else_branch:
                if isinstance(stmt.else_branch, GoBlock):
                    for s in stmt.else_branch.statements:
                        cs = cls._convert_statement_to_ir(s)
                        if cs:
                            orelse.append(cs)
                elif isinstance(stmt.else_branch, GoIfStatement):
                    cs = cls._convert_statement_to_ir(stmt.else_branch)
                    if cs:
                        orelse.append(cs)

            return IRBranch(condition=cond, body=body, orelse=orelse, location=stmt.location)

        if isinstance(stmt, GoForStatement):
            cond = cls._convert_expression_to_ir(stmt.condition) if stmt.condition else IRConstant(value=True, type_name="bool")
            body: List[IRStatement] = []
            for s in stmt.body.statements:
                cs = cls._convert_statement_to_ir(s)
                if cs:
                    body.append(cs)
            return IRLoop(condition=cond, body=body, location=stmt.location)

        if isinstance(stmt, GoReturnStatement):
            val = cls._convert_expression_to_ir(stmt.results[0]) if stmt.results else None
            return IRReturn(value=val, location=stmt.location)

        if isinstance(stmt, GoExpressionStatement):
            expr = stmt.expression
            converted_expr = cls._convert_expression_to_ir(expr)
            if isinstance(converted_expr, IRCall):
                return IRAssignment(target=IRVariable(name="_"), value=converted_expr, location=stmt.location)
            return None

        return None

    @classmethod
    def _convert_expression_to_ir(cls, expr: Optional[GoExpression]) -> IRExpression:
        if expr is None:
            return IRConstant(value=None, type_name="nil")

        if isinstance(expr, GoLiteral):
            return IRConstant(value=expr.value, type_name=expr.type_name, location=expr.location)

        if isinstance(expr, GoIdentifier):
            return IRVariable(name=expr.name, location=expr.location)

        if isinstance(expr, GoBinaryExpression):
            return IRBinaryOperation(
                op=expr.operator,
                left=cls._convert_expression_to_ir(expr.left),
                right=cls._convert_expression_to_ir(expr.right),
                location=expr.location,
            )

        if isinstance(expr, GoUnaryExpression):
            return IRUnaryOperation(
                op=expr.operator,
                operand=cls._convert_expression_to_ir(expr.operand),
                location=expr.location,
            )

        if isinstance(expr, GoCallExpression):
            callee_ir = cls._convert_expression_to_ir(expr.callee)
            args_ir = [cls._convert_expression_to_ir(a) for a in expr.args]
            return IRCall(callee=callee_ir, args=args_ir, location=expr.location)

        if isinstance(expr, GoSelectorExpression):
            full_name = f"{cls._format_selector(expr.expression)}.{expr.name}"
            return IRVariable(name=full_name, location=expr.location)

        return IRConstant(value=None, location=expr.location)

    @classmethod
    def _format_selector(cls, expr: GoExpression) -> str:
        if isinstance(expr, GoIdentifier):
            return expr.name
        if isinstance(expr, GoSelectorExpression):
            return f"{cls._format_selector(expr.expression)}.{expr.name}"
        return "expr"

    @classmethod
    def from_ir(cls, ir_module: IRModule) -> GoFile:
        """Converts a Common IRModule back into a GoFile AST."""
        decls: List[Any] = []

        for stmt in ir_module.body:
            if isinstance(stmt, IRFunction):
                params = [GoField(name=p, type_name="any") for p in stmt.parameters]
                results = [GoField(name="", type_name=stmt.return_type)] if stmt.return_type else []
                body_stmts = [cls._convert_ir_to_statement(s) for s in stmt.body]
                fn_decl = GoFunctionDecl(
                    name=stmt.name,
                    params=params,
                    results=results,
                    body=GoBlock(statements=body_stmts),
                )
                decls.append(fn_decl)
            elif isinstance(stmt, IRAssignment):
                decls.append(
                    GoVarSpec(
                        names=[stmt.target.name],
                        values=[cls._convert_ir_to_expression(stmt.value)],
                    )
                )

        pkg_name = ir_module.name if ir_module.name and ir_module.name not in ("<go>", "<module>") else "main"
        return GoFile(package=pkg_name, imports=[], decls=decls)

    @classmethod
    def _convert_ir_to_statement(cls, stmt: IRStatement) -> GoStatement:
        from core.ir import IRExpressionStatement, IRMemberAccess
        if isinstance(stmt, IRExpressionStatement):
            return GoExpressionStatement(expression=cls._convert_ir_to_expression(stmt.expression))
        if isinstance(stmt, IRAssignment):
            val_expr = cls._convert_ir_to_expression(stmt.value)
            target_name = stmt.target.name if isinstance(stmt.target, IRVariable) else "_"
            if target_name == "_":
                return GoExpressionStatement(expression=val_expr)
            return GoAssignmentStatement(
                left=[GoIdentifier(name=target_name)],
                operator=":=",
                right=[val_expr],
            )
        if isinstance(stmt, IRReturn):
            vals = [cls._convert_ir_to_expression(stmt.value)] if stmt.value else []
            return GoReturnStatement(results=vals)
        if isinstance(stmt, IRBranch):
            cond = cls._convert_ir_to_expression(stmt.condition)
            then_body = GoBlock(statements=[cls._convert_ir_to_statement(s) for s in stmt.body])
            else_body = GoBlock(statements=[cls._convert_ir_to_statement(s) for s in stmt.orelse]) if stmt.orelse else None
            return GoIfStatement(condition=cond, body=then_body, else_branch=else_body)
        if isinstance(stmt, IRLoop):
            cond = cls._convert_ir_to_expression(stmt.condition) if stmt.condition else GoLiteral(value=True, raw="true", type_name="bool")
            loop_body = GoBlock(statements=[cls._convert_ir_to_statement(s) for s in stmt.body])
            return GoForStatement(condition=cond, body=loop_body)
        return GoExpressionStatement(expression=GoLiteral(value=None, raw="nil", type_name="nil"))

    @classmethod
    def _convert_ir_to_expression(cls, expr: Optional[IRExpression]) -> GoExpression:
        from core.ir import IRMemberAccess
        if expr is None:
            return GoLiteral(value=None, raw="nil", type_name="nil")
        if isinstance(expr, IRMemberAccess):
            target = cls._convert_ir_to_expression(expr.target)
            return GoSelectorExpression(expression=target, name=expr.member)
        if isinstance(expr, IRConstant):
            raw = repr(expr.value) if expr.value is not None else "nil"
            tname = expr.type_name or "string"
            return GoLiteral(value=expr.value, raw=raw, type_name=tname)
        if isinstance(expr, IRVariable):
            if "." in expr.name:
                parts = expr.name.split(".")
                curr: GoExpression = GoIdentifier(name=parts[0])
                for part in parts[1:]:
                    curr = GoSelectorExpression(expression=curr, name=part)
                return curr
            return GoIdentifier(name=expr.name)
        if isinstance(expr, IRBinaryOperation):
            return GoBinaryExpression(
                operator=expr.op,
                left=cls._convert_ir_to_expression(expr.left),
                right=cls._convert_ir_to_expression(expr.right),
            )
        if isinstance(expr, IRUnaryOperation):
            return GoUnaryExpression(
                operator=expr.op,
                operand=cls._convert_ir_to_expression(expr.operand),
            )
        if isinstance(expr, IRCall):
            callee = cls._convert_ir_to_expression(expr.callee)
            args = [cls._convert_ir_to_expression(a) for a in expr.args]
            return GoCallExpression(callee=callee, args=args)
        return GoLiteral(value=None, raw="nil", type_name="nil")
