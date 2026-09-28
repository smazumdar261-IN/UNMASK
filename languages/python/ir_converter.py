"""Python AST to Common IR bidirectional converter.

Per Section 16 of the Master Specification:
Bridges Python AST and the Common Intermediate Representation (IR),
allowing language-neutral analysis and deobfuscation passes to operate
directly on Python code.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Union

from core.ir import (
    IRAssignment,
    IRBinaryOperation,
    IRBlock,
    IRBranch,
    IRBreak,
    IRCall,
    IRConstant,
    IRContinue,
    IRDictLiteral,
    IRExceptionHandler,
    IRExpression,
    IRExpressionStatement,
    IRFunction,
    IRImport,
    IRIndexAccess,
    IRListLiteral,
    IRLoop,
    IRMemberAccess,
    IRModule,
    IRNode,
    IRPass,
    IRRaise,
    IRReturn,
    IRStatement,
    IRString,
    IRTryExcept,
    IRUnaryOperation,
    IRVariable,
)
from core.provenance import SourceLocation


_BIN_OPS_AST_TO_STR = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
    ast.Pow: "**",
    ast.LShift: "<<",
    ast.RShift: ">>",
    ast.BitOr: "|",
    ast.BitXor: "^",
    ast.BitAnd: "&",
    ast.MatMult: "@",
}

_BIN_OPS_STR_TO_AST = {v: k for k, v in _BIN_OPS_AST_TO_STR.items()}

_UNARY_OPS_AST_TO_STR = {
    ast.Invert: "~",
    ast.Not: "not",
    ast.UAdd: "+",
    ast.USub: "-",
}

_UNARY_OPS_STR_TO_AST = {v: k for k, v in _UNARY_OPS_AST_TO_STR.items()}

_CMP_OPS_AST_TO_STR = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Is: "is",
    ast.IsNot: "is not",
    ast.In: "in",
    ast.NotIn: "not in",
}

_CMP_OPS_STR_TO_AST = {v: k for k, v in _CMP_OPS_AST_TO_STR.items()}


class PythonIRConverter:
    """Converts between Python standard library AST and Common IR."""

    @classmethod
    def to_ir(cls, tree: ast.Module) -> IRModule:
        """Converts an ast.Module into a Common IRModule."""
        body_stmts: List[IRStatement] = []
        for stmt in tree.body:
            converted = cls._convert_statement_to_ir(stmt)
            if converted:
                if isinstance(converted, list):
                    body_stmts.extend(converted)
                else:
                    body_stmts.append(converted)

        loc = cls._get_location(tree)
        return IRModule(name="<python>", language="python", body=body_stmts, location=loc)

    @classmethod
    def _convert_statement_to_ir(cls, stmt: ast.stmt) -> Optional[Union[IRStatement, List[IRStatement]]]:
        loc = cls._get_location(stmt)

        if isinstance(stmt, ast.FunctionDef):
            params = [a.arg for a in stmt.args.args]
            ret_type = ast.unparse(stmt.returns) if stmt.returns else None
            body: List[IRStatement] = []
            for s in stmt.body:
                cs = cls._convert_statement_to_ir(s)
                if cs:
                    if isinstance(cs, list):
                        body.extend(cs)
                    else:
                        body.append(cs)
            return IRFunction(
                name=stmt.name,
                parameters=params,
                body=body,
                return_type=ret_type,
                location=loc,
            )

        if isinstance(stmt, ast.Assign):
            results: List[IRStatement] = []
            val = cls._convert_expression_to_ir(stmt.value)
            for target in stmt.targets:
                ir_target = cls._convert_expression_to_ir(target)
                results.append(IRAssignment(target=ir_target, value=val, location=loc))
            return results if len(results) > 1 else results[0]

        if isinstance(stmt, ast.AugAssign):
            op_cls = type(stmt.op)
            op_str = _BIN_OPS_AST_TO_STR.get(op_cls, "+")
            target = cls._convert_expression_to_ir(stmt.target)
            val = cls._convert_expression_to_ir(stmt.value)
            bin_val = IRBinaryOperation(op=op_str, left=target, right=val, location=loc)
            return IRAssignment(target=target, value=bin_val, location=loc)

        if isinstance(stmt, ast.AnnAssign):
            target = cls._convert_expression_to_ir(stmt.target)
            val = cls._convert_expression_to_ir(stmt.value) if stmt.value else IRConstant(value=None)
            return IRAssignment(target=target, value=val, location=loc)

        if isinstance(stmt, ast.Expr):
            expr = cls._convert_expression_to_ir(stmt.value)
            return IRExpressionStatement(expression=expr, location=loc)

        if isinstance(stmt, ast.If):
            cond = cls._convert_expression_to_ir(stmt.test)
            body = []
            for s in stmt.body:
                cs = cls._convert_statement_to_ir(s)
                if cs:
                    if isinstance(cs, list):
                        body.extend(cs)
                    else:
                        body.append(cs)
            orelse = []
            for s in stmt.orelse:
                cs = cls._convert_statement_to_ir(s)
                if cs:
                    if isinstance(cs, list):
                        orelse.extend(cs)
                    else:
                        orelse.append(cs)
            return IRBranch(condition=cond, body=body, orelse=orelse, location=loc)

        if isinstance(stmt, ast.While):
            cond = cls._convert_expression_to_ir(stmt.test)
            body = []
            for s in stmt.body:
                cs = cls._convert_statement_to_ir(s)
                if cs:
                    if isinstance(cs, list):
                        body.extend(cs)
                    else:
                        body.append(cs)
            orelse = []
            for s in stmt.orelse:
                cs = cls._convert_statement_to_ir(s)
                if cs:
                    if isinstance(cs, list):
                        orelse.extend(cs)
                    else:
                        orelse.append(cs)
            return IRLoop(condition=cond, body=body, orelse=orelse, is_for=False, location=loc)

        if isinstance(stmt, ast.For):
            target = cls._convert_expression_to_ir(stmt.target)
            iter_expr = cls._convert_expression_to_ir(stmt.iter)
            body = []
            for s in stmt.body:
                cs = cls._convert_statement_to_ir(s)
                if cs:
                    if isinstance(cs, list):
                        body.extend(cs)
                    else:
                        body.append(cs)
            orelse = []
            for s in stmt.orelse:
                cs = cls._convert_statement_to_ir(s)
                if cs:
                    if isinstance(cs, list):
                        orelse.extend(cs)
                    else:
                        orelse.append(cs)
            return IRLoop(
                condition=None,
                body=body,
                orelse=orelse,
                is_for=True,
                iterator=iter_expr,
                target=target,
                location=loc,
            )

        if isinstance(stmt, ast.Return):
            val = cls._convert_expression_to_ir(stmt.value) if stmt.value else None
            return IRReturn(value=val, location=loc)

        if isinstance(stmt, ast.Break):
            return IRBreak(location=loc)

        if isinstance(stmt, ast.Continue):
            return IRContinue(location=loc)

        if isinstance(stmt, ast.Pass):
            return IRPass(location=loc)

        if isinstance(stmt, ast.Raise):
            exc = cls._convert_expression_to_ir(stmt.exc) if stmt.exc else None
            return IRRaise(exception=exc, location=loc)

        if isinstance(stmt, ast.Try):
            body = []
            for s in stmt.body:
                cs = cls._convert_statement_to_ir(s)
                if cs:
                    if isinstance(cs, list):
                        body.extend(cs)
                    else:
                        body.append(cs)
            handlers = []
            for h in stmt.handlers:
                exc_type = ast.unparse(h.type) if h.type else None
                h_body = []
                for s in h.body:
                    cs = cls._convert_statement_to_ir(s)
                    if cs:
                        if isinstance(cs, list):
                            h_body.extend(cs)
                        else:
                            h_body.append(cs)
                handlers.append(
                    IRExceptionHandler(
                        exception_type=exc_type,
                        variable_name=h.name,
                        body=h_body,
                        location=cls._get_location(h),
                    )
                )
            orelse = []
            for s in stmt.orelse:
                cs = cls._convert_statement_to_ir(s)
                if cs:
                    if isinstance(cs, list):
                        orelse.extend(cs)
                    else:
                        orelse.append(cs)
            finalbody = []
            for s in stmt.finalbody:
                cs = cls._convert_statement_to_ir(s)
                if cs:
                    if isinstance(cs, list):
                        finalbody.extend(cs)
                    else:
                        finalbody.append(cs)
            return IRTryExcept(
                body=body,
                handlers=handlers,
                orelse=orelse,
                finalbody=finalbody,
                location=loc,
            )

        if isinstance(stmt, ast.Import):
            if stmt.names:
                alias = stmt.names[0]
                return IRImport(module_name=alias.name, alias=alias.asname, location=loc)

        if isinstance(stmt, ast.ImportFrom):
            imported = {alias.name: alias.asname for alias in stmt.names}
            return IRImport(module_name=stmt.module or "", imported_names=imported, location=loc)

        # Fallback for unhandled statement
        return IRExpressionStatement(
            expression=IRConstant(value=f"unhandled: {type(stmt).__name__}"),
            location=loc,
        )

    @classmethod
    def _convert_expression_to_ir(cls, expr: Optional[ast.expr]) -> IRExpression:
        if expr is None:
            return IRConstant(value=None)

        loc = cls._get_location(expr)

        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, str):
                return IRString(value=expr.value, location=loc)
            return IRConstant(value=expr.value, location=loc)

        if isinstance(expr, ast.Name):
            return IRVariable(name=expr.id, location=loc)

        if isinstance(expr, ast.Attribute):
            target = cls._convert_expression_to_ir(expr.value)
            return IRMemberAccess(target=target, member=expr.attr, location=loc)

        if isinstance(expr, ast.Subscript):
            target = cls._convert_expression_to_ir(expr.value)
            idx = cls._convert_expression_to_ir(expr.slice)
            return IRIndexAccess(target=target, index=idx, location=loc)

        if isinstance(expr, ast.BinOp):
            op_cls = type(expr.op)
            op_str = _BIN_OPS_AST_TO_STR.get(op_cls, "+")
            left = cls._convert_expression_to_ir(expr.left)
            right = cls._convert_expression_to_ir(expr.right)
            return IRBinaryOperation(op=op_str, left=left, right=right, location=loc)

        if isinstance(expr, ast.UnaryOp):
            op_cls = type(expr.op)
            op_str = _UNARY_OPS_AST_TO_STR.get(op_cls, "-")
            operand = cls._convert_expression_to_ir(expr.operand)
            return IRUnaryOperation(op=op_str, operand=operand, location=loc)

        if isinstance(expr, ast.Compare):
            left = cls._convert_expression_to_ir(expr.left)
            current = left
            for op, comparator in zip(expr.ops, expr.comparators):
                op_str = _CMP_OPS_AST_TO_STR.get(type(op), "==")
                right = cls._convert_expression_to_ir(comparator)
                current = IRBinaryOperation(op=op_str, left=current, right=right, location=loc)
            return current

        if isinstance(expr, ast.BoolOp):
            op_str = "and" if isinstance(expr.op, ast.And) else "or"
            res = cls._convert_expression_to_ir(expr.values[0])
            for val in expr.values[1:]:
                res = IRBinaryOperation(
                    op=op_str,
                    left=res,
                    right=cls._convert_expression_to_ir(val),
                    location=loc,
                )
            return res

        if isinstance(expr, ast.Call):
            callee = cls._convert_expression_to_ir(expr.func)
            args = [cls._convert_expression_to_ir(a) for a in expr.args]
            kwargs = {k.arg: cls._convert_expression_to_ir(k.value) for k in expr.keywords if k.arg}
            return IRCall(callee=callee, args=args, kwargs=kwargs, location=loc)

        if isinstance(expr, (ast.List, ast.Tuple)):
            elements = [cls._convert_expression_to_ir(e) for e in expr.elts]
            lit = IRListLiteral(elements=elements, location=loc)
            if isinstance(expr, ast.Tuple):
                lit.metadata["is_tuple"] = True
            return lit

        if isinstance(expr, ast.Dict):
            keys = [cls._convert_expression_to_ir(k) for k in expr.keys if k]
            vals = [cls._convert_expression_to_ir(v) for v in expr.values]
            return IRDictLiteral(keys=keys, values=vals, location=loc)

        return IRConstant(value=ast.unparse(expr) if hasattr(ast, "unparse") else None, location=loc)

    @classmethod
    def from_ir(cls, ir_module: IRModule) -> ast.Module:
        """Converts a Common IRModule back into an ast.Module."""
        py_stmts: List[ast.stmt] = []
        for s in ir_module.body:
            converted = cls._convert_ir_to_stmt(s)
            if converted:
                py_stmts.append(converted)

        mod = ast.Module(body=py_stmts, type_ignores=[])
        ast.fix_missing_locations(mod)
        return mod

    @classmethod
    def _convert_ir_to_stmt(cls, stmt: IRStatement) -> Optional[ast.stmt]:
        if isinstance(stmt, IRFunction):
            args = ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg=p) for p in stmt.parameters],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            )
            body = [cls._convert_ir_to_stmt(s) for s in stmt.body]
            body = [s for s in body if s is not None]
            if not body:
                body = [ast.Pass()]
            return ast.FunctionDef(
                name=stmt.name,
                args=args,
                body=body,
                decorator_list=[],
                returns=ast.Name(id=stmt.return_type, ctx=ast.Load()) if stmt.return_type else None,
            )

        if isinstance(stmt, IRAssignment):
            target = cls._convert_ir_to_expr(stmt.target, is_store=True)
            val = cls._convert_ir_to_expr(stmt.value)
            return ast.Assign(targets=[target], value=val)

        if isinstance(stmt, IRExpressionStatement):
            expr = cls._convert_ir_to_expr(stmt.expression)
            return ast.Expr(value=expr)

        if isinstance(stmt, IRBranch):
            cond = cls._convert_ir_to_expr(stmt.condition)
            body = [cls._convert_ir_to_stmt(s) for s in stmt.body]
            body = [s for s in body if s is not None] or [ast.Pass()]
            orelse = [cls._convert_ir_to_stmt(s) for s in stmt.orelse]
            orelse = [s for s in orelse if s is not None]
            return ast.If(test=cond, body=body, orelse=orelse)

        if isinstance(stmt, IRLoop):
            body = [cls._convert_ir_to_stmt(s) for s in stmt.body]
            body = [s for s in body if s is not None] or [ast.Pass()]
            orelse = [cls._convert_ir_to_stmt(s) for s in stmt.orelse]
            orelse = [s for s in orelse if s is not None]
            if stmt.is_for:
                target = cls._convert_ir_to_expr(stmt.target, is_store=True) if stmt.target else ast.Name(id="_", ctx=ast.Store())
                iter_expr = cls._convert_ir_to_expr(stmt.iterator) if stmt.iterator else ast.List(elts=[], ctx=ast.Load())
                return ast.For(target=target, iter=iter_expr, body=body, orelse=orelse)
            else:
                cond = cls._convert_ir_to_expr(stmt.condition) if stmt.condition else ast.Constant(value=True)
                return ast.While(test=cond, body=body, orelse=orelse)

        if isinstance(stmt, IRReturn):
            val = cls._convert_ir_to_expr(stmt.value) if stmt.value else None
            return ast.Return(value=val)

        if isinstance(stmt, IRBreak):
            return ast.Break()

        if isinstance(stmt, IRContinue):
            return ast.Continue()

        if isinstance(stmt, IRPass):
            return ast.Pass()

        if isinstance(stmt, IRRaise):
            exc = cls._convert_ir_to_expr(stmt.exception) if stmt.exception else None
            return ast.Raise(exc=exc, cause=None)

        if isinstance(stmt, IRTryExcept):
            body = [cls._convert_ir_to_stmt(s) for s in stmt.body]
            body = [s for s in body if s is not None] or [ast.Pass()]
            handlers = []
            for h in stmt.handlers:
                h_body = [cls._convert_ir_to_stmt(s) for s in h.body]
                h_body = [s for s in h_body if s is not None] or [ast.Pass()]
                h_type = ast.Name(id=h.exception_type, ctx=ast.Load()) if h.exception_type else None
                handlers.append(ast.ExceptHandler(type=h_type, name=h.variable_name, body=h_body))
            orelse = [cls._convert_ir_to_stmt(s) for s in stmt.orelse]
            orelse = [s for s in orelse if s is not None]
            finalbody = [cls._convert_ir_to_stmt(s) for s in stmt.finalbody]
            finalbody = [s for s in finalbody if s is not None]
            return ast.Try(body=body, handlers=handlers, orelse=orelse, finalbody=finalbody)

        if isinstance(stmt, IRImport):
            if stmt.imported_names:
                aliases = [
                    ast.alias(name=orig, asname=alias)
                    for orig, alias in stmt.imported_names.items()
                ]
                return ast.ImportFrom(module=stmt.module_name, names=aliases, level=0)
            else:
                return ast.Import(names=[ast.alias(name=stmt.module_name, asname=stmt.alias)])

        return None

    @classmethod
    def _convert_ir_to_expr(cls, expr: Optional[IRExpression], is_store: bool = False) -> ast.expr:
        ctx = ast.Store() if is_store else ast.Load()

        if expr is None:
            return ast.Constant(value=None)

        if isinstance(expr, IRConstant):
            return ast.Constant(value=expr.value)

        if isinstance(expr, IRVariable):
            return ast.Name(id=expr.name, ctx=ctx)

        if isinstance(expr, IRMemberAccess):
            target = cls._convert_ir_to_expr(expr.target)
            return ast.Attribute(value=target, attr=expr.member, ctx=ctx)

        if isinstance(expr, IRIndexAccess):
            target = cls._convert_ir_to_expr(expr.target)
            idx = cls._convert_ir_to_expr(expr.index)
            return ast.Subscript(value=target, slice=idx, ctx=ctx)

        if isinstance(expr, IRBinaryOperation):
            left = cls._convert_ir_to_expr(expr.left)
            right = cls._convert_ir_to_expr(expr.right)
            if expr.op in _BIN_OPS_STR_TO_AST:
                op_cls = _BIN_OPS_STR_TO_AST[expr.op]
                return ast.BinOp(left=left, op=op_cls(), right=right)
            elif expr.op in _CMP_OPS_STR_TO_AST:
                op_cls = _CMP_OPS_STR_TO_AST[expr.op]
                return ast.Compare(left=left, ops=[op_cls()], comparators=[right])
            elif expr.op == "and":
                return ast.BoolOp(op=ast.And(), values=[left, right])
            elif expr.op == "or":
                return ast.BoolOp(op=ast.Or(), values=[left, right])
            return ast.BinOp(left=left, op=ast.Add(), right=right)

        if isinstance(expr, IRUnaryOperation):
            operand = cls._convert_ir_to_expr(expr.operand)
            op_cls = _UNARY_OPS_STR_TO_AST.get(expr.op, ast.USub)
            return ast.UnaryOp(op=op_cls(), operand=operand)

        if isinstance(expr, IRCall):
            func = cls._convert_ir_to_expr(expr.callee)
            args = [cls._convert_ir_to_expr(a) for a in expr.args]
            keywords = [
                ast.keyword(arg=k, value=cls._convert_ir_to_expr(v))
                for k, v in expr.kwargs.items()
            ]
            return ast.Call(func=func, args=args, keywords=keywords)

        if isinstance(expr, IRListLiteral):
            elts = [cls._convert_ir_to_expr(e) for e in expr.elements]
            if expr.metadata.get("is_tuple"):
                return ast.Tuple(elts=elts, ctx=ctx)
            return ast.List(elts=elts, ctx=ctx)

        if isinstance(expr, IRDictLiteral):
            keys = [cls._convert_ir_to_expr(k) for k in expr.keys]
            vals = [cls._convert_ir_to_expr(v) for v in expr.values]
            return ast.Dict(keys=keys, values=vals)

        return ast.Constant(value=None)

    @classmethod
    def _get_location(cls, node: Any) -> SourceLocation:
        lineno = getattr(node, "lineno", None)
        col = getattr(node, "col_offset", None)
        end_lineno = getattr(node, "end_lineno", None)
        end_col = getattr(node, "end_col_offset", None)
        return SourceLocation(
            filename=None,
            start_line=lineno,
            start_col=col,
            end_line=end_lineno,
            end_col=end_col,
        )
